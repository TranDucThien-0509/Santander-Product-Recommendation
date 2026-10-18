"""Bounded-memory, disk-backed Customer 360 over a verified completed v2 run.

Build once; serve read-only. No model fitting or cloud publication is performed.
The separate Track A research/6-month benchmarks are not prerequisites for this
serving index and are not represented as having run on the full population.
"""
import argparse
import base64
from collections import deque
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import threading

import duckdb
import numpy as np
import pandas as pd

from pipeline.common import PRODUCTS, shift
from track_a.customer360 import CustomerStore, PRODUCT_NAMES, RULE_PERSONAS, POLICY_VERSION


INDEX_VERSION = 1
FEATURE_COLUMNS = ["age", "renta", "antiguedad", "canal_entrada", "segmento",
    "R", "F_event_months", "M_group_points", "M_group_uses_baseline", "rfm_no_event",
    "observed_pairs", "n_products", "predicted_acquisitions_1m", "clv_unavailable", "persona_id"]


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def decode_mask(mask):
    return None if mask is None else [p for j, p in enumerate(PRODUCTS) if int(mask) & (1 << j)]


def verify_source(source_run, raw_csv, expected_crc32c=None):
    root, raw = Path(source_run), Path(raw_csv)
    read = lambda name: json.loads((root / name).read_text(encoding="utf-8-sig"))
    config, manifest = read("config.resolved.json"), read("input_manifest.json")
    if read("completed.json").get("status") != "success":
        raise ValueError("A successfully completed source run is required")
    if manifest.get("products") != PRODUCTS or manifest["raw"]["size"] != raw.stat().st_size:
        raise ValueError("Raw size or product schema differs from the source run")
    months = sorted(p.stem for p in (root / "features").glob("????-??.parquet"))
    if not months or months != pd.period_range(config["data"]["history_start"], config["data"]["forecast_month"], freq="M").astype(str).tolist():
        raise ValueError("All consecutive source months are required")
    audits = read("point_in_time_audit.json")
    if sorted(a["origin"] for a in audits) != months:
        raise ValueError("Point-in-time audit must cover every scoring month")
    for entry in audits:
        for cutoff in [entry.get("m_max_label_month"), entry.get("clv", {}).get("max_label_month"), entry.get("affinity", {}).get("max_label_month")]:
            if cutoff is not None and cutoff > entry["origin"]:
                raise ValueError("Source features use future labels")
    paths = [root / name for name in ["config.resolved.json", "input_manifest.json", "point_in_time_audit.json", "completed.json"]]
    paths += [root / part / f"{m}.parquet" for part in ["features", "lifecycle"] for m in months]
    hashes = {str(p.relative_to(root)): file_hash(p) for p in paths}
    import google_crc32c
    crc, sha = google_crc32c.Checksum(), hashlib.sha256()
    with raw.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            crc.update(block)
            sha.update(block)
    checksum = base64.b64encode(crc.digest()).decode()
    if expected_crc32c and checksum != expected_crc32c:
        raise ValueError("Raw CRC32C differs from the verified cloud source")
    return config, months, dict(source_files_sha256=hashes, raw_sha256=sha.hexdigest(), raw_crc32c=checksum,
        expected_raw_crc32c=expected_crc32c, source_run=root.name)


def affinity_counts(connection, month):
    """Aggregate identical portfolios before 24x24 matrix arithmetic."""
    rows = connection.execute("""SELECT ((owned_mask & ~acquired_mask) | removed_mask) AS previous_mask,
        acquired_mask, count(*) FROM snapshots WHERE month=? AND acquired_mask IS NOT NULL
        GROUP BY 1,2""", [month]).fetchall()
    counts = np.zeros((24, 24)); exposure = counts.copy()
    numerator = np.zeros(24); denominator = numerator.copy()
    # Batches bound intermediate matrices even for unusually diverse portfolios.
    for start in range(0, len(rows), 4096):
        batch = rows[start:start+4096]
        old = np.asarray([[bool(a & (1 << j)) for j in range(24)] for a, _, _ in batch], dtype=float)
        opened = np.asarray([[bool(b & (1 << j)) for j in range(24)] for _, b, _ in batch], dtype=float)
        weights = np.asarray([n for _, _, n in batch], dtype=float)[:, None]
        counts += old.T @ (opened * weights)
        exposure += old.T @ ((1-old) * weights)
        numerator += (opened * weights).sum(axis=0)
        denominator += ((1-old) * weights).sum(axis=0)
    return counts, exposure, numerator, denominator


def finish_index(connection, months, source_name, scope, provenance=None, affinity_window=3, affinity_prior=1000.):
    """Finish derived metadata; shared by the builder and synthetic contracts."""
    summary = []
    connection.execute("CREATE TABLE affinity(month VARCHAR, conditional_json VARCHAR, popularity_json VARCHAR)")
    recent = deque(maxlen=affinity_window)
    for month in months:
        observed, pairs, customers, products = connection.execute("""SELECT count(*) FILTER(WHERE is_observed),
            count(acquired_mask), count(*) FILTER(WHERE acquired_mask>0), coalesce(sum(bit_count(acquired_mask)),0)
            FROM snapshots WHERE month=?""", [month]).fetchone()
        available = bool(pairs)
        summary.append(dict(month=month, previous_month=shift(month, -1), observed_customers=observed,
            available=available, eligible_pairs=pairs if shift(month, -1) in months else None,
            unverified_customers=observed-pairs, customers_opened=customers if available else None,
            product_openings=products if available else None,
            note="Lượt mở là thay đổi 0→1 giữa hai snapshot tháng liên tiếp đầy đủ; có thể gồm mở lại sản phẩm."
                if available else "Không có cặp snapshot đầy đủ để xác định lượt mở trong tháng."
                if shift(month, -1) in months else "Chưa có snapshot tháng liền trước để xác định lượt mở."))
        recent.append(affinity_counts(connection, month))
        counts, exposure, num, den = [sum((a[j] for a in recent), np.zeros((24, 24) if j < 2 else 24)) for j in range(4)]
        pop = np.divide(num, den, out=np.zeros(24), where=den > 0)
        conditional = (counts + affinity_prior * pop[None, :]) / (exposure + affinity_prior)
        np.fill_diagonal(conditional, 0)
        connection.execute("INSERT INTO affinity VALUES (?,?,?)", [month, json.dumps(conditional.tolist()), json.dumps(pop.tolist())])
        print(f"Index summaries/affinity {month}: {observed:,} observed, {customers:,} acquisition customers", flush=True)
    known = connection.execute("SELECT count(*) FROM snapshots WHERE month=?", [months[-1]]).fetchone()[0]
    metadata = dict(index_version=INDEX_VERSION, status="success", months=months, latest_month=months[-1],
        customer_count=known, source_run=source_name, scope=scope, policy_version=POLICY_VERSION,
        monthly_acquisitions=summary, provenance=provenance or {},
        affinity=dict(method="temporal-ownership-smoothed-24-v1", window_months=affinity_window,
            prior=affinity_prior, max_label_month="each scoring month", recomputed_for_serving=True))
    connection.execute("CREATE TABLE metadata(value VARCHAR)")
    connection.execute("INSERT INTO metadata VALUES (?)", [json.dumps(metadata, ensure_ascii=False)])
    connection.execute("CHECKPOINT")
    return metadata


def build_index(source_run, raw_csv, destination, expected_crc32c=None):
    root, destination = Path(source_run), Path(destination)
    if destination.exists():
        raise FileExistsError("Use a new index path; completed indexes are immutable")
    print("Verifying completed source, monthly files and raw checksum...", flush=True)
    config, months, provenance = verify_source(root, raw_csv, expected_crc32c)
    destination.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(destination), config={"memory_limit":"512MB", "threads":"1", "preserve_insertion_order":"false"})
    try:
        print("Indexing raw status flags (streamed from CSV)...", flush=True)
        connection.execute(f"""CREATE TABLE flags AS SELECT CAST(trim(ncodpers) AS BIGINT) customer_id,
            substr(fecha_dato,1,7) AS month, trim(indfall) indfall, trim(ind_actividad_cliente) activity
            FROM read_csv({quote(Path(raw_csv).resolve())}, all_varchar=true, sample_size=20480,
                buffer_size=4194304, max_line_size=1048576)
            WHERE substr(fecha_dato,1,7) BETWEEN ? AND ?""", [months[0], months[-1]])
        if connection.execute("SELECT count(*) FROM (SELECT customer_id,month FROM flags GROUP BY 1,2 HAVING count(*)<>1)").fetchone()[0]:
            raise ValueError("Duplicate raw customer-month status")
        connection.execute("CREATE TABLE deceased AS SELECT customer_id, min(month) first_deceased FROM flags WHERE indfall='S' GROUP BY 1")
        nullable = " AND ".join(f'"{p}" IS NOT NULL' for p in PRODUCTS)
        mask = " + ".join(f'(CAST("{p}"=1 AS BIGINT) << {j})' for j, p in enumerate(PRODUCTS))
        for month in months:
            print(f"Packing source ownership/features {month}...", flush=True)
            fields = ",".join(FEATURE_COLUMNS)
            select = f"SELECT customer_id,month,{fields}, product_complete=1 AND ({nullable}) AS product_complete, CASE WHEN product_complete=1 AND ({nullable}) THEN ({mask}) END owned_mask FROM read_parquet({quote(root/'features'/f'{month}.parquet')})"
            connection.execute(("CREATE TABLE features AS " if month == months[0] else "INSERT INTO features ") + select)
        if connection.execute("SELECT count(*) FROM (SELECT customer_id,month FROM features GROUP BY 1,2 HAVING count(*)<>1)").fetchone()[0]:
            raise ValueError("Duplicate feature customer-month")
        mismatch = connection.execute("""SELECT count(*) FROM features f LEFT JOIN flags s USING(customer_id,month)
            WHERE s.customer_id IS NULL""").fetchone()[0]
        raw_count = connection.execute("SELECT count(*) FROM flags").fetchone()[0]
        feature_count = connection.execute("SELECT count(*) FROM features").fetchone()[0]
        if mismatch or raw_count != feature_count:
            raise ValueError("Raw and feature snapshot membership must match exactly")
        for month in months:
            print(f"Building point-in-time snapshots {month}...", flush=True)
            # Status flags apply only to the same observed snapshot. Historical
            # deceased gates use the first flag <= origin, never a future flag.
            connection.execute(f"""CREATE OR REPLACE TEMP TABLE current_base AS
                SELECT l.customer_id, l.month, l.is_observed, l.missing_months,
                    l.lifecycle presence_lifecycle, coalesce(f.product_complete,false) AND l.is_observed product_complete,
                    s.indfall, s.activity, coalesce(s.indfall IN ('S','N') AND s.activity IN ('0','1'),false) status_known,
                    coalesce(d.first_deceased<=l.month,false) historical_deceased,
                    CASE WHEN s.indfall='S' THEN 'Churned'
                        WHEN l.is_observed AND s.activity='0' AND l.lifecycle NOT IN ('New','Win-back') THEN 'At-risk'
                        ELSE l.lifecycle END lifecycle,
                    coalesce(l.is_observed AND f.product_complete AND s.indfall='N' AND s.activity='1'
                        AND NOT coalesce(d.first_deceased<=l.month,false),false) cross_sell_eligible,
                    f.* EXCLUDE(customer_id,month,product_complete),
                    CASE WHEN l.is_observed AND f.product_complete AND p.product_complete
                        THEN f.owned_mask & ~p.owned_mask END acquired_mask,
                    CASE WHEN l.is_observed AND f.product_complete AND p.product_complete
                        THEN p.owned_mask & ~f.owned_mask END removed_mask,
                    CASE WHEN l.is_observed AND f.product_complete AND f.clv_unavailable=0
                        AND isfinite(f.predicted_acquisitions_1m) AND f.predicted_acquisitions_1m>=0
                        THEN f.predicted_acquisitions_1m END clv_1m
                FROM read_parquet({quote(root/'lifecycle'/f'{month}.parquet')}) l
                LEFT JOIN features f ON f.customer_id=l.customer_id AND f.month={quote(month)}
                LEFT JOIN features p ON p.customer_id=l.customer_id AND p.month={quote(shift(month,-1))}
                LEFT JOIN flags s ON s.customer_id=l.customer_id AND s.month={quote(month)}
                LEFT JOIN deceased d ON d.customer_id=l.customer_id""")
            if connection.execute("SELECT count(*)-count(DISTINCT customer_id) FROM current_base").fetchone()[0]:
                raise ValueError("Duplicate lifecycle customer-month")
            if connection.execute("SELECT count(*) FROM current_base WHERE is_observed").fetchone()[0] != connection.execute("SELECT count(*) FROM features WHERE month=?",[month]).fetchone()[0]:
                raise ValueError("Observed lifecycle and feature membership differ")
            connection.execute("""CREATE OR REPLACE TEMP TABLE peers AS SELECT customer_id,
                (rank() OVER(ORDER BY clv_1m)+(count(*) OVER(PARTITION BY clv_1m)-1)/2.0-.5)
                /count(*) OVER()*100 clv_peer_percentile, count(*) OVER() clv_peer_n FROM current_base
                WHERE cross_sell_eligible AND clv_1m IS NOT NULL AND observed_pairs>=3""")
            peer_n = connection.execute("SELECT count(*) FROM peers").fetchone()[0]
            sql = "SELECT b.*,p.clv_peer_percentile,?::BIGINT clv_peer_n FROM current_base b LEFT JOIN peers p USING(customer_id) ORDER BY b.customer_id"
            connection.execute(("CREATE TABLE snapshots AS " if month == months[0] else "INSERT INTO snapshots ")+sql, [peer_n])
            connection.execute("CHECKPOINT")
        connection.execute("DROP TABLE flags; DROP TABLE features; DROP TABLE deceased")
        scope = "full source population, all source months" if not config.get("data",{}).get("sample_customers") else "source customer population, all source months"
        metadata = finish_index(connection, months, root.name, scope, provenance,
            config["meta_models"]["affinity_window_months"], config["meta_models"]["affinity_prior"])
        print(f"Customer index COMPLETE: {metadata['customer_count']:,} customers; {feature_count:,} observed snapshots", flush=True)
        return metadata
    finally:
        connection.close()


class IndexedCustomerStore(CustomerStore):
    """API-compatible read-only store; each lookup fetches only one customer."""
    def __init__(self, path):
        self.connection = duckdb.connect(str(Path(path).resolve()), read_only=True,
            config={"memory_limit":"256MB", "threads":"1"})
        self.lock = threading.RLock()
        self.info = json.loads(self.connection.execute("SELECT value FROM metadata").fetchone()[0])
        if self.info.get("status") != "success" or self.info.get("index_version") != INDEX_VERSION:
            raise ValueError("A completed compatible customer index is required")
        self.months = self.info["months"]
        self.source_name, self.scope = self.info["source_run"], self.info["scope"]

    def close(self):
        self.connection.close()

    def records(self, sql, params=()):
        with self.lock:
            cursor = self.connection.execute(sql, params)
            names = [c[0] for c in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]

    def metadata(self):
        return {k:self.info[k] for k in ["months","latest_month","scope","source_run","customer_count","policy_version"]}

    @lru_cache(maxsize=128)
    def row(self, customer_id, month):
        rows = self.records("SELECT * FROM snapshots WHERE customer_id=? AND month=?", [int(customer_id),month])
        return rows[0] if rows else None

    def knows_customer(self, customer_id, month):
        return self.row(customer_id, month) is not None

    def snapshot(self, customer_id, month):
        r = self.row(customer_id, month)
        if r is None:
            return dict(month=month, known=False, is_observed=False, product_complete=False,
                lifecycle="Chưa xuất hiện", R=None,F=None,M=None,n_products=None,clv_1m=None,
                persona_rule=None,acquired=None,removed=None)
        complete = r["product_complete"]
        return dict(month=month,known=True,is_observed=r["is_observed"],product_complete=complete,
            lifecycle=r["lifecycle"],presence_lifecycle=r["presence_lifecycle"],missing_months=r["missing_months"],
            status_known=r["status_known"],deceased=None if r["indfall"] is None else r["indfall"]=="S",
            historical_deceased=r["historical_deceased"],activity=r["activity"],cross_sell_eligible=r["cross_sell_eligible"],
            R=r["R"] if complete else None,F=r["F_event_months"] if complete else None,
            M=r["M_group_points"] if complete else None,m_uses_baseline=r["M_group_uses_baseline"],
            rfm_no_event=r["rfm_no_event"],n_products=r["n_products"] if complete else None,
            observed_pairs=r["observed_pairs"],clv_1m=r["clv_1m"],clv_peer_percentile=r["clv_peer_percentile"],
            clv_peer_n=r["clv_peer_n"],persona_rule=r["persona_id"] if r["persona_id"] in RULE_PERSONAS else None,
            owned=decode_mask(r["owned_mask"]) if complete else [],
            acquired=decode_mask(r["acquired_mask"]),removed=decode_mask(r["removed_mask"]))

    @lru_cache(maxsize=24)
    def affinity(self, month):
        r = self.records("SELECT * FROM affinity WHERE month=?", [month])[0]
        return np.asarray(json.loads(r["conditional_json"])), np.asarray(json.loads(r["popularity_json"]))

    def feature_row(self, customer_id, month):
        r = dict(self.row(customer_id, month))
        own = np.asarray([bool((r["owned_mask"] or 0) & (1 << j)) for j in range(24)], dtype=float)
        conditional, pop = self.affinity(month)
        score = .5*(own @ conditional / max(own.sum(),1))+.5*pop
        for j,p in enumerate(PRODUCTS):
            r[p] = int(own[j])
            r["affinity_"+p] = 0. if own[j] else float(score[j])
        return r

    def search(self, query, month):
        if month not in self.months:
            raise ValueError("Tháng không nằm trong bộ dữ liệu")
        return self.records("""SELECT customer_id,lifecycle,is_observed FROM snapshots
            WHERE month=? AND starts_with(CAST(customer_id AS VARCHAR),?) ORDER BY customer_id LIMIT 30""", [month,query])

    def examples(self, month):
        result = []
        for label, condition in [("CLV-proxy cao","cross_sell_eligible AND clv_peer_percentile>=80"),
            ("Đang hoạt động","cross_sell_eligible AND clv_peer_percentile<80"),
            ("Vắng trong tháng","NOT is_observed AND NOT historical_deceased")]:
            rows = self.records(f"SELECT customer_id FROM snapshots WHERE month=? AND ({condition}) ORDER BY customer_id LIMIT 1", [month])
            if rows: result.append(dict(label=label,customer_id=rows[0]["customer_id"]))
        return result

    def acquisition_summary(self):
        return dict(months=self.info["monthly_acquisitions"], scope=self.scope,source_run=self.source_name)

    def acquisitions(self, month, query="", page=1, page_size=25):
        if month not in self.months:
            raise ValueError("Tháng không nằm trong bộ dữ liệu")
        if query and (not query.isascii() or not query.isdigit() or len(query)>12):
            raise ValueError("Mã khách lọc phải là chữ số, tối đa 12 ký tự")
        if type(page) is not int or page<1 or type(page_size) is not int or not 1<=page_size<=100:
            raise ValueError("Trang hoặc số dòng mỗi trang không hợp lệ")
        params = [month,query]
        where = "month=? AND acquired_mask>0 AND starts_with(CAST(customer_id AS VARCHAR),?)"
        counts = self.records(f"SELECT count(*) n, coalesce(sum(bit_count(acquired_mask)),0) products FROM snapshots WHERE {where}",params)[0]
        pages = max(1,(counts["n"]+page_size-1)//page_size)
        if page>pages: raise ValueError("Trang vượt quá số kết quả")
        rows = self.records(f"SELECT customer_id,acquired_mask,bit_count(acquired_mask) opening_count FROM snapshots WHERE {where} ORDER BY opening_count DESC,customer_id LIMIT ? OFFSET ?",params+[page_size,(page-1)*page_size])
        for r in rows:
            r["products"]=[dict(code=p,name=PRODUCT_NAMES[p]) for p in decode_mask(r.pop("acquired_mask"))]
        return dict(summary=next(s for s in self.info["monthly_acquisitions"] if s["month"]==month),rows=rows,
            query=query,page=page,page_size=page_size,total_customers=counts["n"],total_pages=pages,
            filtered_product_openings=counts["products"])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run",required=True)
    parser.add_argument("--raw-csv",required=True)
    parser.add_argument("--out",required=True)
    parser.add_argument("--raw-crc32c",help="Expected CRC32C from the raw source object receipt")
    args=parser.parse_args()
    build_index(args.source_run,args.raw_csv,args.out,args.raw_crc32c)


if __name__=="__main__":
    main()
