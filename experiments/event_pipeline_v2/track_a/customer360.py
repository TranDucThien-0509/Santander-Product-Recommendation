"""Read-only, point-in-time customer profiles over a completed Track A run.

All predictions are existing one-month acquisition-count proxies. The care policy
is a transparent heuristic, not an estimated campaign uplift or monetary ROI.
"""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.common import PRODUCTS, shift
from pipeline.ingest import csv_source
from track_a.data import Panel


POLICY_VERSION = "customer-care-v1"
RULE_PERSONAS = {
    "P1": "Chưa ghi nhận mở thêm sản phẩm, danh mục ≤2 sản phẩm",
    "P2": "Chưa ghi nhận mở thêm sản phẩm, danh mục ≥3 sản phẩm",
    "P3": "Có 1 tháng ghi nhận mở thêm sản phẩm",
    "P4": "Có ≥2 tháng mở thêm sản phẩm, hiện còn ≤1 sản phẩm",
    "P5": "Có ≥2 tháng mở thêm sản phẩm, hiện có 2–4 sản phẩm",
    "P6": "Có ≥2 tháng mở thêm sản phẩm, hiện có ≥5 sản phẩm",
}
# Santander source column descriptions, retained alongside machine-readable codes.
PRODUCT_NAMES = dict(zip(PRODUCTS, [
    "Saving Account", "Guarantees", "Current Accounts", "Derivada Account",
    "Payroll Account", "Junior Account", "Más Particular Account",
    "Particular Account", "Particular Plus Account", "Short-term Deposits",
    "Medium-term Deposits", "Long-term Deposits", "e-account", "Funds",
    "Mortgage", "Pensions", "Loans", "Taxes", "Credit Card", "Securities",
    "Home Account", "Payroll", "Pensions (income)", "Direct Debit",
]))


def scalar(value):
    if value is None or pd.isna(value):
        return None
    return value.item() if isinstance(value, np.generic) else value


def care_policy(snapshot):
    """Gate first; rank only valid, active customers against same-month peers."""
    reasons = []
    if snapshot.get("deceased") is True or snapshot.get("historical_deceased"):
        action, label = "stop", "Dừng cross-sell tự động"
        reasons.append("Nguồn đã từng ghi nhận indfall=S tính đến tháng này; cần xác minh nghiệp vụ trước mọi tiếp cận.")
    elif not snapshot["is_observed"]:
        action, label = "verify", "Xác minh / tái kết nối"
        reasons.append("Khách vắng trong snapshot tháng này; chưa biết danh mục và trạng thái hiện tại.")
    elif not snapshot["product_complete"] or not snapshot["status_known"]:
        action, label = "verify", "Bổ sung dữ liệu trước khi quyết định"
        reasons.append("Thiếu danh mục đầy đủ hoặc trạng thái hoạt động / indfall chưa xác định.")
    elif not snapshot["cross_sell_eligible"]:
        action, label = "retain", "Xác minh nhu cầu / chăm sóc giữ chân"
        reasons.append("Nguồn ghi nhận khách không hoạt động; chưa đủ điều kiện cross-sell.")
    elif snapshot.get("clv_1m") is None or (snapshot.get("observed_pairs") or 0) < 3:
        action, label = "observe", "Theo dõi thêm, thử nghiệm quy mô nhỏ"
        reasons.append("Chưa có CLV-proxy hợp lệ hoặc có dưới 3 cặp tháng quan sát đầy đủ.")
    elif snapshot.get("clv_peer_percentile") is not None and snapshot["clv_peer_percentile"] >= 80:
        action, label = "test", "Ưu tiên thử nghiệm cross-sell"
        reasons.append("CLV-proxy nằm từ phân vị 80 trong nhóm đủ điều kiện cùng tháng.")
    else:
        action, label = "maintain", "Duy trì chăm sóc chi phí thấp"
        reasons.append("Dữ liệu đủ để theo dõi; chưa đạt ngưỡng ưu tiên thử nghiệm cross-sell.")
    return dict(action=action, label=label, reasons=reasons, policy_version=POLICY_VERSION,
                threshold_percentile=80, minimum_observed_pairs=3,
                basis="Heuristic ưu tiên chăm sóc, chưa tối ưu theo lợi nhuận hoặc uplift.",
                roi=None,
                next_step={
                    "verify": "Kiểm tra thông tin khách và dữ liệu tháng hiện tại trước khi tiếp cận.",
                    "stop": "Chuyển kiểm tra nghiệp vụ; không tạo đề xuất bán thêm.",
                    "retain": "Xác minh lý do không hoạt động và nhu cầu; chưa tự động bán thêm.",
                    "observe": "Thu thập thêm lịch sử; đo phản hồi trên thử nghiệm nhỏ có nhóm đối chứng.",
                    "test": "Chọn sản phẩm chưa sở hữu theo affinity, kiểm tra nhu cầu và thử nghiệm có nhóm đối chứng.",
                    "maintain": "Duy trì tương tác phù hợp, theo dõi thay đổi R/F và nhu cầu thực tế.",
                }[action])


def read_flags(raw_path, months, ids):
    parts = []
    def consume(src):
        for q in pd.read_csv(src, usecols=lambda c: c in {
            "fecha_dato", "ncodpers", "indfall", "ind_actividad_cliente"},
            dtype="string", chunksize=400_000):
            q["customer_id"] = pd.to_numeric(q.ncodpers, errors="raise").astype("int64")
            q["month"] = pd.to_datetime(q.fecha_dato, errors="raise").dt.strftime("%Y-%m")
            q = q.loc[q.month.isin(months) & q.customer_id.isin(ids)].copy()
            for col in ["indfall", "ind_actividad_cliente"]:
                q[col] = q[col].str.strip() if col in q else pd.NA
            parts.append(q[["customer_id", "month", "indfall", "ind_actividad_cliente"]])
    csv_source(raw_path, "train_ver2.csv", consume)
    flags = pd.concat(parts, ignore_index=True)
    if flags.duplicated(["customer_id", "month"]).any():
        raise ValueError("Duplicate raw status customer-month")
    return flags


class CustomerStore:
    """In-memory sample explorer over customer snapshots, without clustering."""
    def __init__(self, frames, lifecycles, flags, source_name, scope):
        self.frames, self.lifecycles = frames, lifecycles
        self.months = sorted(frames)
        self.flags = {m: z.set_index("customer_id") for m, z in flags.groupby("month")}
        self.source_name, self.scope = source_name, scope

    @classmethod
    def load(cls, source_run, cache_dir, track_a_run):
        source_run, track_a_run = Path(source_run), Path(track_a_run)
        # Panel validates raw fingerprint, cache match, successful completion and
        # that feature training labels do not exceed each scoring origin.
        panel = Panel(source_run, cache_dir)
        completed = json.loads((track_a_run / "completed.json").read_text())
        provenance = json.loads((track_a_run / "run_provenance.json").read_text())
        if completed.get("status") != "success" or completed.get("source_run") != source_run.name:
            raise ValueError("Track A artifacts must belong to this completed source run")
        for key, path in [
            ("source_config_sha256", source_run / "config.resolved.json"),
            ("source_cache_manifest_sha256", Path(cache_dir) / "manifest.json"),
            ("source_point_in_time_audit_sha256", source_run / "point_in_time_audit.json"),
            ("raw_sha256", Path(panel.config["data"]["train_csv_or_zip"])),
        ]:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != provenance.get(key):
                raise ValueError(f"Track A/source provenance mismatch: {key}")
        frames = {m: pd.read_parquet(source_run / "features" / f"{m}.parquet").set_index("customer_id")
                  for m in panel.months}
        lifecycle = {m: pd.read_parquet(source_run / "lifecycle" / f"{m}.parquet").set_index("customer_id")
                     for m in panel.months}
        ids = lifecycle[panel.months[-1]].index
        flags = read_flags(panel.config["data"]["train_csv_or_zip"], panel.months, ids)
        scope = json.loads((track_a_run / "summary.json").read_text())["sample_scope"]
        return cls(frames, lifecycle, flags, source_run.name, scope)

    @lru_cache(maxsize=18)
    def cohort(self, month):
        if month not in self.months:
            raise ValueError("Tháng không nằm trong bộ dữ liệu")
        f, life = self.frames[month], self.lifecycles[month]
        z = life.copy().rename(columns={"lifecycle": "presence_lifecycle"})
        flags = self.flags.get(month, pd.DataFrame(columns=["indfall", "ind_actividad_cliente"]))
        z = z.join(flags[["indfall", "ind_actividad_cliente"]])
        z["status_known"] = z.indfall.isin(["S", "N"]) & z.ind_actividad_cliente.isin(["0", "1"])
        dead, inactive = z.indfall.eq("S").fillna(False), z.ind_actividad_cliente.eq("0").fillna(False)
        z["lifecycle"] = z.presence_lifecycle
        z.loc[z.is_observed & inactive & ~z.lifecycle.isin(["New", "Win-back"]), "lifecycle"] = "At-risk"
        z.loc[dead, "lifecycle"] = "Churned"
        z["product_complete"] = f.product_complete.reindex(z.index).eq(1)
        past_deceased = set()
        for m, past in self.flags.items():
            if m <= month:
                past_deceased.update(past.index[past.indfall.eq("S").fillna(False)])
        z["historical_deceased"] = z.index.isin(past_deceased)
        z["cross_sell_eligible"] = z.is_observed & z.status_known & ~dead & ~inactive & z.product_complete & ~z.historical_deceased
        z["clv_1m"] = f.predicted_acquisitions_1m.reindex(z.index)
        valid_clv = np.isfinite(z.clv_1m) & z.clv_1m.ge(0) & f.clv_unavailable.reindex(z.index).eq(0)
        z.loc[~valid_clv | ~z.product_complete | ~z.is_observed, "clv_1m"] = np.nan
        pairs = f.observed_pairs.reindex(z.index)
        peer = z.cross_sell_eligible & z.clv_1m.notna() & pairs.ge(3)
        # Midrank: tied constant predictions must not all become top-priority.
        values = z.loc[peer, "clv_1m"]
        z["clv_peer_percentile"] = ((values.rank(method="average") - .5) / len(values) * 100)
        z["clv_peer_n"] = len(values)
        return z

    def metadata(self):
        return dict(months=self.months, latest_month=self.months[-1], scope=self.scope,
                    source_run=self.source_name, customer_count=len(self.lifecycles[self.months[-1]]),
                    policy_version=POLICY_VERSION)

    def search(self, query, month):
        cohort = self.cohort(month)
        ids = sorted(int(i) for i in cohort.index if str(i).startswith(query))[:30]
        return [dict(customer_id=i, lifecycle=str(cohort.loc[i, "lifecycle"]),
                     is_observed=bool(cohort.loc[i, "is_observed"])) for i in ids]

    def examples(self, month):
        z = self.cohort(month)
        masks = [("CLV-proxy cao", z.cross_sell_eligible & z.clv_peer_percentile.ge(80)),
                 ("Đang hoạt động", z.cross_sell_eligible & z.clv_peer_percentile.lt(80)),
                 ("Vắng trong tháng", ~z.is_observed & ~z.historical_deceased)]
        return [dict(label=label, customer_id=int(z.loc[mask].index[0])) for label, mask in masks if mask.any()]

    def snapshot(self, customer_id, month):
        z, f = self.cohort(month), self.frames[month]
        if customer_id not in z.index:
            return dict(month=month, known=False, is_observed=False, product_complete=False,
                        lifecycle="Chưa xuất hiện", R=None, F=None, M=None, n_products=None,
                        clv_1m=None, persona_rule=None, acquired=None, removed=None)
        life = z.loc[customer_id]
        observed = bool(life.is_observed)
        row = f.loc[customer_id] if observed and customer_id in f.index else pd.Series(dtype=object)
        complete = bool(life.product_complete)
        result = dict(month=month, known=True, is_observed=observed, product_complete=complete,
            lifecycle=str(life.lifecycle), presence_lifecycle=str(life.presence_lifecycle),
            missing_months=int(life.missing_months), status_known=bool(life.status_known),
            deceased=None if pd.isna(life.indfall) else life.indfall == "S",
            historical_deceased=bool(life.historical_deceased),
            activity=scalar(life.ind_actividad_cliente), cross_sell_eligible=bool(life.cross_sell_eligible),
            R=scalar(row.get("R")) if complete else None,
            F=scalar(row.get("F_event_months")) if complete else None,
            M=scalar(row.get("M_group_points")) if complete else None,
            m_uses_baseline=scalar(row.get("M_group_uses_baseline")),
            rfm_no_event=scalar(row.get("rfm_no_event")),
            n_products=scalar(row.get("n_products")) if complete else None,
            observed_pairs=scalar(row.get("observed_pairs")),
            clv_1m=scalar(life.clv_1m), clv_peer_percentile=scalar(life.clv_peer_percentile),
            clv_peer_n=int(life.clv_peer_n),
            persona_rule=scalar(row.get("persona_id")) if row.get("persona_id") in RULE_PERSONAS else None,
            acquired=None, removed=None, owned=[])
        if complete:
            result["owned"] = [p for p in PRODUCTS if row[p] == 1]
            previous = self.frames.get(shift(month, -1))
            if previous is not None and customer_id in previous.index and previous.loc[customer_id, "product_complete"] == 1:
                old = previous.loc[customer_id]
                result["acquired"] = [p for p in PRODUCTS if old[p] == 0 and row[p] == 1]
                result["removed"] = [p for p in PRODUCTS if old[p] == 1 and row[p] == 0]
        return result

    def profile(self, customer_id, month, window=6):
        if month not in self.months or not 1 <= window <= 24:
            raise ValueError("Tháng hoặc số tháng xem không hợp lệ")
        if customer_id not in self.lifecycles[month].index:
            raise KeyError("Khách chưa xuất hiện tính đến tháng đã chọn")
        months = [m for m in self.months if shift(month, 1-window) <= m <= month]
        timeline = [self.snapshot(customer_id, m) for m in months]
        current = timeline[-1]
        policy = care_policy(current)
        recommendations = []
        if current["cross_sell_eligible"] and (current["observed_pairs"] or 0) >= 3 and current["clv_1m"] is not None:
            row = self.frames[month].loc[customer_id]
            for p in PRODUCTS:
                score = scalar(row.get("affinity_" + p))
                if row[p] == 0 and score is not None and np.isfinite(score) and score > 0:
                    recommendations.append(dict(product=p, name=PRODUCT_NAMES[p], score=float(score)))
            recommendations.sort(key=lambda r: (-r["score"], r["product"]))
        customer_row = self.frames[month].loc[customer_id] if current["is_observed"] else pd.Series(dtype=object)
        customer_demographics = {name: scalar(customer_row.get(col)) for col, name in [
            ("age", "age"), ("renta", "income"), ("antiguedad", "tenure"),
            ("canal_entrada", "channel"), ("segmento", "segment")
        ]}
        for key in ["channel", "segment"]:
            if customer_demographics[key] in ["__MISSING__", "UNKNOWN", ""]:
                customer_demographics[key] = None
        gaps = sum(not r["is_observed"] or not r["product_complete"] for r in timeline)
        history_pairs = current["observed_pairs"]
        evidence = "Đủ điều kiện so sánh" if current["cross_sell_eligible"] and (history_pairs or 0) >= 3 and current["clv_1m"] is not None else "Cần bổ sung / xác minh"
        insights = []
        if current["historical_deceased"]:
            insights.append("Đã từng có cờ indfall=S trong dữ liệu đến tháng này. Kể cả khi tháng hiện tại vắng hoặc cờ đổi, cần xác minh thủ công; không tự động tái kết nối / bán thêm.")
        if not current["is_observed"]:
            insights.append(f"Khách đã vắng {current['missing_months']} tháng; không suy diễn RFM hay sở hữu hiện tại từ lần xuất hiện cũ.")
        elif current["product_complete"]:
            if current["rfm_no_event"] == 1:
                insights.append("Chưa ghi nhận mở thêm sản phẩm trong các cặp tháng quan sát hợp lệ. R để trống, không phải 0.")
            elif current["R"] is not None:
                insights.append(f"Lần gần nhất ghi nhận mở thêm sản phẩm cách {int(current['R'])} tháng; F={int(current['F'])} tháng có sự kiện trong lịch sử hợp lệ.")
            insights.append(f"Danh mục hiện có {int(current['n_products'])} sản phẩm; M là điểm propensity của nhóm danh mục, không phải tiền chi tiêu.")
        if len(timeline) > 1 and not gaps:
            delta = current["n_products"] - timeline[0]["n_products"]
            insights.append(f"Số sản phẩm thay đổi {delta:+.0f} giữa {months[0]} và {month}; đây là thay đổi quan sát, không phải dự báo.")
        if gaps:
            insights.append(f"Cửa sổ có {gaps} tháng vắng / thiếu danh mục / chưa xuất hiện; không gán sự kiện bằng 0 hoặc nối đường qua các tháng này.")
        if current["clv_1m"] is not None:
            insights.append(f"Dự báo tại {month} cho {shift(month, 1)}: {current['clv_1m']:.3f} sản phẩm mở thêm kỳ vọng; chưa có xác suất churn hay dự báo lợi nhuận.")
        return dict(customer_id=customer_id, as_of_month=month, window=window,
                    source_run=self.source_name, scope=self.scope,
                    current=current, timeline=timeline, policy=policy,
                    persona_description=RULE_PERSONAS.get(current["persona_rule"], "Chưa đủ điều kiện gán persona rule"),
                    customer_demographics=customer_demographics,
                    recommendations=recommendations[:5], product_names=PRODUCT_NAMES,
                    evidence=dict(label=evidence, observed_pairs=history_pairs, gap_months=gaps,
                                  meaning="Mức đầy đủ dữ liệu, không phải xác suất dự báo đúng."),
                    insights=insights, forecast_month=shift(month, 1),
                    limitations=["CLV là acquisition-count proxy 1 tháng, không phải CLV bằng tiền hoặc xác suất mua.",
                        "Affinity là điểm xếp hạng, không phải xác suất mua đã hiệu chỉnh.",
                        "Không có chi phí, biên lợi nhuận và uplift chiến dịch để kết luận ROI hay khách sẽ sinh lời.",
                        "Không dự báo 6 tháng bằng cách nhân CLV 1 tháng; chưa có mô hình tương lai cá nhân dài hạn được phục vụ ở đây.",
                        "Lịch sử panel bị giới hạn bên trái; F và sự kiện không đại diện toàn bộ đời khách."])
