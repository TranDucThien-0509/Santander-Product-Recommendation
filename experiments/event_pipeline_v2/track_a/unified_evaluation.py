"""One point-in-time cohort for Track A prioritization and product recommendation.

Run from event_pipeline_v2: python -m track_a.unified_evaluation --help
Only aggregate outputs are written. The serving database is opened read-only.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil

import duckdb
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.metrics import adjusted_rand_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from pipeline.common import PRODUCTS, FEATURE_VERSIONS, shift, write_json
from .unified_metrics import customer_metrics, mask_matrix, ProductMetrics, wilson


VERSION = "track-a-unified-v1"
RFM_COLUMNS = ["R", "F_event_months", "n_products", "rfm_no_event"]
METHODS = {
    "historical_population": "Tỷ lệ mở thêm lịch sử chung",
    "rfm_portfolio_propensity": "RFM: propensity danh mục",
    "rfm_rule_based": "RFM: ngưỡng quy tắc",
    "rfm_quantile_333": "RFM: phân vị 3 mức",
    "rfm_kmeans_6": "RFM: K-means 6 cụm",
    "lifecycle_presence": "Lifecycle: hiện diện trong panel",
    "lifecycle_activity": "Lifecycle: bổ sung activity/death",
    "persona_rules": "Persona: luật P1–P6",
    "clv_poisson_1m": "CLV: Poisson boosting 1 tháng",
    "affinity_max": "Affinity: điểm sản phẩm cao nhất",
}


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024*1024), b""):
            result.update(block)
    return result.hexdigest()


class FrozenRFM:
    def __init__(self, frame, fit_month):
        self.fit_month = fit_month
        self.transform = make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler())
        x = self.transform.fit_transform(frame[RFM_COLUMNS])
        with threadpool_limits(limits=1):
            self.model = KMeans(n_clusters=6, n_init=10, random_state=42).fit(x)
        self.edges = {c: np.unique(frame[c].dropna().quantile([1/3, 2/3]).dropna().to_numpy()) for c in RFM_COLUMNS[:3]}

    def labels(self, frame):
        with threadpool_limits(limits=1):
            clusters = self.model.predict(self.transform.transform(frame[RFM_COLUMNS]))
        quantiles = [np.where(frame[c].isna(), -1, np.searchsorted(self.edges[c], frame[c], side="right")) for c in RFM_COLUMNS[:3]]
        rules = [np.where(frame.R.isna(), -1, np.select([frame.R.le(1), frame.R.le(3)], [0, 1], default=2)),
            np.select([frame.F_event_months.eq(0), frame.F_event_months.eq(1)], [0, 1], default=2),
            np.select([frame.n_products.le(2), frame.n_products.le(4)], [0, 1], default=2)]
        combine = lambda bins: np.asarray(["_".join(map(str, values)) for values in zip(*bins)])
        return {"rfm_kmeans_6": (clusters+1).astype(str), "rfm_quantile_333": combine(quantiles),
            "rfm_rule_based": combine(rules)}

    def spec(self):
        return dict(fit_month=self.fit_month, columns=RFM_COLUMNS, n_clusters=6, n_init=10, random_state=42,
            fit_population="all observed complete source snapshots in fit month, no outcome labels",
            quantile_edges={key: value.tolist() for key,value in self.edges.items()},
            imputer_medians=[None if not np.isfinite(value) else float(value) for value in self.transform[0].statistics_],
            imputer_empty_feature_policy="keep_empty_features=True; all-missing fit columns have no observed median",
            scaler_mean=self.transform[1].mean_.tolist(),
            scaler_scale=self.transform[1].scale_.tolist(), centers=self.model.cluster_centers_.tolist(),
            rule_r=[1,3], rule_f=[0,1], rule_products=[2,4], missing_R="separate -1 bucket; KMeans imputation plus no-event flag")


class PastGroupRates:
    def __init__(self, prior=100.):
        if prior < 0:
            raise ValueError("Group prior must be nonnegative")
        self.prior = prior
        self.counts = defaultdict(lambda: [0,0])

    def predict(self, labels, baseline):
        values = {}
        for label in np.unique(labels):
            n, events = self.counts[str(label)]
            values[label] = (events + self.prior*baseline)/(n+self.prior) if n+self.prior else baseline
        return np.asarray([values[label] for label in labels]), np.asarray([self.counts[str(label)][0] == 0 for label in labels])

    def update(self, labels, outcomes):
        frame = pd.DataFrame(dict(group=np.asarray(labels).astype(str), event=np.asarray(outcomes)>0))
        for label, row in frame.groupby("group", sort=False).event.agg(["size","sum"]).iterrows():
            self.counts[label][0] += int(row["size"])
            self.counts[label][1] += int(row["sum"])


def load_cohort(connection, origin):
    """The sole cohort/label join, reused by every method without per-method filtering."""
    next_month = shift(origin, 1)
    complete = connection.execute("SELECT count(*) FROM snapshots WHERE month=? AND is_observed AND product_complete", [origin]).fetchone()[0]
    frame = connection.execute("""SELECT t.customer_id,t.R,t.F_event_months,t.n_products,t.rfm_no_event,
        t.M_group_points,t.M_group_uses_baseline,t.predicted_acquisitions_1m,t.clv_unavailable,t.persona_id,
        t.presence_lifecycle,t.lifecycle,t.owned_mask,u.acquired_mask,
        bit_count(u.acquired_mask)::INTEGER acquisitions,
        u.owned_mask & ~t.owned_mask AS independently_acquired_mask
        FROM snapshots t JOIN snapshots u ON t.customer_id=u.customer_id AND u.month=?
        WHERE t.month=? AND t.is_observed AND u.is_observed AND t.product_complete AND u.product_complete
        AND t.owned_mask IS NOT NULL AND u.acquired_mask IS NOT NULL ORDER BY t.customer_id""", [next_month,origin]).df()
    if frame.empty or not frame.customer_id.is_unique:
        raise ValueError("Evaluation needs unique customer IDs and nonempty consecutive complete pairs")
    if not frame.acquired_mask.equals(frame.independently_acquired_mask):
        raise ValueError("Index event masks differ from independently joined ownership transitions")
    ids_hash = hashlib.sha256(frame.customer_id.to_numpy(dtype="<i8").tobytes()).hexdigest()
    return frame.drop(columns="independently_acquired_mask"), dict(origin=origin,target_month=next_month,
        origin_complete_n=int(complete),n_all=len(frame),excluded_next_n=int(complete)-len(frame),
        pair_coverage=len(frame)/complete,cohort_ids_sha256=ids_hash)


def affinity_parameters(connection, origin):
    row = connection.execute("SELECT conditional_json,popularity_json FROM affinity WHERE month=?",[origin]).fetchall()
    if len(row) != 1:
        raise ValueError("Exactly one causal affinity matrix is required for the origin")
    conditional, popularity = [np.asarray(json.loads(value), dtype=float) for value in row[0]]
    if conditional.shape != (24,24) or popularity.shape != (24,) or not np.isfinite(conditional).all() or not np.isfinite(popularity).all():
        raise ValueError("Affinity product order/shape or finite-value contract failed")
    if (conditional < 0).any() or (conditional > 1+1e-10).any() or (popularity < 0).any() or (popularity > 1).any():
        raise ValueError("Invalid conditional rates in the stored affinity matrix")
    return conditional, popularity


def evaluate_products(connection, frame, origin, batch_size=32768):
    conditional, popularity = affinity_parameters(connection, origin)
    maximum = np.zeros(len(frame))
    affinity, population = ProductMetrics(), ProductMetrics()
    for start in range(0,len(frame),batch_size):
        stop = min(start+batch_size,len(frame))
        batch = frame.iloc[start:stop]
        ownership = mask_matrix(batch.owned_mask.to_numpy()).astype(float)
        with threadpool_limits(limits=1):
            score = .5*(ownership @ conditional / np.maximum(ownership.sum(axis=1,keepdims=True),1))+.5*popularity
        score[ownership == 1] = 0
        maximum[start:stop] = score.max(axis=1)
        args = batch.owned_mask.to_numpy(),batch.acquired_mask.to_numpy()
        affinity.update(score,*args)
        population.update(np.broadcast_to(popularity,score.shape),*args)
    return maximum, {"affinity_temporal_v2":affinity.result(),"past_opportunity_popularity":population.result()}


def group_statistics(frame, labels, origin, method, probabilities):
    values = pd.DataFrame(dict(group=labels,event=frame.acquisitions.to_numpy()>0,
        products=frame.acquisitions.to_numpy(),prediction=probabilities))
    baseline = values.event.mean()
    result = []
    for label, part in values.groupby("group",sort=True):
        n, events = len(part),int(part.event.sum())
        lo, hi = wilson(events,n)
        result.append(dict(origin=origin,target_month=shift(origin,1),method=method,group=str(label),n=n,
            events=events,product_acquisitions=int(part.products.sum()),acquisition_rate=events/n,
            rate_ci95_low=lo,rate_ci95_high=hi,cohort_acquisition_rate=float(baseline),
            acquisition_rate_lift=(events/n)/baseline if baseline else None,
            past_only_predicted_rate=float(part.prediction.mean())))
    return result


def group_stability(previous, frame, labels, rates, origin, method, min_support):
    current = pd.Series(np.asarray(labels).astype(str),index=frame.customer_id.to_numpy())
    now = pd.DataFrame(rates).set_index("group")
    result = None
    if previous is not None:
        old_origin,old,old_rates = previous
        common = old.index.intersection(current.index)
        supported = now.index.intersection(old_rates.index)
        supported = supported[(now.loc[supported,"n"].to_numpy()>=min_support) & (old_rates.loc[supported,"n"].to_numpy()>=min_support)]
        current_rates,old_values = now.loc[supported,"acquisition_rate"],old_rates.loc[supported,"acquisition_rate"]
        correlation = current_rates.corr(old_values,method="spearman") if len(supported)>=2 and current_rates.nunique()>1 and old_values.nunique()>1 else None
        result = dict(method=method,source_month=old_origin,target_month=origin,common_n=len(common),
            common_coverage=len(common)/len(old),same_label_rate=float((old.loc[common]==current.loc[common]).mean()) if len(common) else None,
            membership_ARI=float(adjusted_rand_score(old.loc[common],current.loc[common])) if len(common) else None,
            supported_rate_groups=len(supported),rate_rank_spearman=None if correlation is None or pd.isna(correlation) else float(correlation),
            min_group_support=min_support)
    return result,(origin,current,now)


def validate_source(connection, source):
    metadata = json.loads(connection.execute("SELECT value FROM metadata").fetchone()[0])
    if metadata.get("status") != "success" or metadata.get("index_version") != 1:
        raise ValueError("A completed compatible index is required")
    if source.name != metadata["source_run"]:
        raise ValueError("Index and completed source run do not match")
    for name in ["config.resolved.json","input_manifest.json","point_in_time_audit.json","completed.json"]:
        expected = metadata["provenance"].get("source_files_sha256",{}).get(name)
        if not expected or digest(source/name) != expected:
            raise ValueError("Source provenance hash mismatch: "+name)
    config = json.loads((source/"config.resolved.json").read_text(encoding="utf-8-sig"))
    if json.loads((source/"completed.json").read_text()).get("status") != "success":
        raise ValueError("Source pipeline did not complete successfully")
    if json.loads((source/"input_manifest.json").read_text()).get("products") != PRODUCTS:
        raise ValueError("Source product order differs from the metric label order")
    if metadata["months"] != pd.period_range(metadata["months"][0],metadata["months"][-1],freq="M").astype(str).tolist():
        raise ValueError("Indexed source months must be consecutive")
    audit = json.loads((source/"point_in_time_audit.json").read_text())
    if sorted(entry["origin"] for entry in audit) != metadata["months"]:
        raise ValueError("Source audit does not cover the indexed months")
    for entry in audit:
        for cutoff in [entry.get("m_max_label_month"),entry.get("clv",{}).get("max_label_month"),entry.get("affinity",{}).get("max_label_month")]:
            if cutoff and cutoff>entry["origin"]:
                raise ValueError("Future outcomes entered origin features")
    if metadata["affinity"]["method"] != FEATURE_VERSIONS["affinity"]:
        raise ValueError("Affinity version differs from current v2 definition")
    return metadata,config


def run(index, source_run, out, origins, fit_month="2015-11", group_prior=100., min_support=100):
    index, source, out = Path(index).resolve(),Path(source_run).resolve(),Path(out).resolve()
    if out.exists():
        raise FileExistsError("Use a new output directory; prior benchmark evidence is immutable")
    implementation = {path.name:path.read_bytes() for path in [Path(__file__),Path(__file__).with_name("unified_metrics.py")]}
    connection = duckdb.connect(str(index),read_only=True,config={"memory_limit":"256MB","threads":"1"})
    try:
        metadata,config = validate_source(connection,source)
        months = metadata["months"]
        origins = sorted(set(origins))
        if not origins or any(m<=fit_month or m not in months or shift(m,1) not in months for m in origins):
            raise ValueError("Origins must be after the frozen RFM fit month and have observed next-month labels")
        fit = connection.execute("SELECT R,F_event_months,n_products,rfm_no_event FROM snapshots WHERE month=? AND is_observed AND product_complete",[fit_month]).df()
        if len(fit)<6:
            raise ValueError("Insufficient RFM fit snapshots")
        print(f"Fitting frozen RFM definitions at {fit_month}: {len(fit):,} full-cohort snapshots",flush=True)
        frozen = FrozenRFM(fit,fit_month)
        del fit
        group_history = defaultdict(lambda:PastGroupRates(group_prior))
        previous = {}
        customer_rows,product_rows,group_rows,stability_rows,audits = [],[],[],[],[]
        history_n = history_events = history_products = 0
        for origin in [m for m in months if m<=origins[-1]]:
            if shift(origin,1) not in months:
                continue
            frame,audit = load_cohort(connection,origin)
            counts = frame.acquisitions.to_numpy()
            baseline = history_events/history_n if history_n else 0.
            mean_count = history_products/history_n if history_n else 0.
            grouped = {"lifecycle_presence":frame.presence_lifecycle.fillna("UNKNOWN").to_numpy(dtype=str),
                "lifecycle_activity":frame.lifecycle.fillna("UNKNOWN").to_numpy(dtype=str),
                "persona_rules":frame.persona_id.fillna("UNKNOWN").to_numpy(dtype=str)}
            if origin>=fit_month:
                grouped.update(frozen.labels(frame))
            if origin in origins:
                print(f"Evaluating {origin} -> {shift(origin,1)}: {len(frame):,} pairs, {(counts>0).sum():,} buyers",flush=True)
                affinity_score,product_scores = evaluate_products(connection,frame,origin)
                m = frame.M_group_points.to_numpy(dtype=float)/100
                m_missing = ~np.isfinite(m)
                if ((m[~m_missing]<0)|(m[~m_missing]>1)).any():
                    raise ValueError("RFM propensity is outside the documented 0–100 scale")
                m = np.where(m_missing,baseline,m)
                clv = frame.predicted_acquisitions_1m.to_numpy(dtype=float)
                invalid_clv = ~np.isfinite(clv)|(clv<0)
                clv = np.where(invalid_clv,mean_count,clv)
                candidates = {"historical_population":(np.full(len(frame),baseline),np.full(len(frame),baseline),None,0),
                    "rfm_portfolio_propensity":(m,m,None,int((m_missing|frame.M_group_uses_baseline.fillna(0).eq(1).to_numpy()).sum())),
                    "clv_poisson_1m":(clv,-np.expm1(-clv),clv,int((invalid_clv|frame.clv_unavailable.fillna(1).eq(1).to_numpy()).sum())),
                    "affinity_max":(affinity_score,None,None,0)}
                grouped_predictions = {}
                for method,labels in grouped.items():
                    probability,unseen = group_history[method].predict(labels,baseline)
                    candidates[method] = probability,probability,None,int(unseen.sum())
                    grouped_predictions[method] = probability
                for method,(score,probability,count_prediction,fallback_n) in candidates.items():
                    customer_rows.append(dict(origin=origin,target_month=shift(origin,1),method=method,
                        cohort_ids_sha256=audit["cohort_ids_sha256"],fallback_n=fallback_n,
                        native_score_coverage=1-fallback_n/len(frame),
                        **customer_metrics(score,counts,event_probability=probability,predicted_count=count_prediction)))
                for method,metrics in product_scores.items():
                    product_rows.append(dict(origin=origin,target_month=shift(origin,1),method=method,
                        evaluation_mode="recomputed",cohort_ids_sha256=audit["cohort_ids_sha256"],**metrics))
                for method,labels in grouped.items():
                    rates = group_statistics(frame,labels,origin,method,grouped_predictions[method])
                    group_rows.extend(rates)
                    stability,previous[method] = group_stability(previous.get(method),frame,labels,rates,origin,method,min_support)
                    if stability:
                        stability_rows.append(stability)
                audits.append(dict(**audit,n_buyers=int((counts>0).sum()),product_acquisitions=int(counts.sum()),
                    history_label_end=origin,history_pairs_n=history_n,rfm_fit_month=fit_month))
            else:
                print(f"Historical calibration {origin} -> {shift(origin,1)}: {len(frame):,} pairs",flush=True)
            # The outcome at origin+1 becomes available to the NEXT scoring month only.
            for method,labels in grouped.items():
                group_history[method].update(labels,counts)
            history_n += len(frame)
            history_events += int((counts>0).sum())
            history_products += int(counts.sum())
        tables = dict(customer_metrics_by_month=pd.DataFrame(customer_rows),product_metrics_by_month=pd.DataFrame(product_rows),
            group_rates_by_month=pd.DataFrame(group_rows),group_stability_by_month=pd.DataFrame(stability_rows),cohort_audit=pd.DataFrame(audits))
        for origin in origins:
            rows = tables["customer_metrics_by_month"].query("origin==@origin")
            if rows.n_all.nunique()!=1 or rows.n_buyers.nunique()!=1 or rows.cohort_ids_sha256.nunique()!=1:
                raise AssertionError("Methods did not use the identical cohort")
        test_origins = config["split"]["test_origins"]
        reference_path = source/source.name.split("_2026")[0]/"test_metrics.json"
        if not reference_path.exists():
            options = list(source.glob("*/test_metrics.json"))
            reference_path = options[0] if len(options)==1 else None
        if reference_path:
            reference = json.loads(reference_path.read_text())
            for item in reference["by_origin"]:
                origin = item["origin"]
                if origin not in origins:
                    continue
                own = tables["cohort_audit"].query("origin==@origin").iloc[0]
                if int(own.n_all)!=item["n_all"] or int(own.n_buyers)!=item["n_buyers"]:
                    raise ValueError("Saved evaluation ranker report uses a different cohort")
                product_rows.append(dict(origin=origin,target_month=shift(origin,1),method="saved_v2_evaluation_ranker",
                    evaluation_mode="imported completed test report; counts checked, predictions not rerun",
                    cohort_ids_sha256=own.cohort_ids_sha256,**{k:item[k] for k in ["n_all","n_buyers","buyer_prevalence","map_at_7_all","map_at_7_buyers","recall_at_7_buyers","recommendation_coverage"]},
                    map_at_7_all_ceiling=item["buyer_prevalence"]))
            tables["product_metrics_by_month"] = pd.DataFrame(product_rows)
        mean_columns = ["AP","AUC","lift10_buyers","capture10_buyers","capture10_products","lift10_products","Brier","MAE_count","RMSE_count","count_calibration_ratio"]
        tables["customer_metrics_monthly_mean"] = tables["customer_metrics_by_month"].groupby("method",sort=False)[mean_columns].mean().reset_index()
        out.mkdir(parents=True)
        (out/"implementation").mkdir()
        for name,content in implementation.items():
            (out/"implementation"/name).write_bytes(content)
        for name,table in tables.items():
            table.to_csv(out/(name+".csv"),index=False)
        manifest = dict(version=VERSION,created_utc=datetime.now(timezone.utc).isoformat(),source_run=metadata["source_run"],scope=metadata["scope"],
            origins=origins,source_test_origins=test_origins,history_first_origin=months[0],rfm_fit=frozen.spec(),
            source_feature_versions=FEATURE_VERSIONS,group_probability_prior=group_prior,
            rank_stability_min_support=min_support,methods=METHODS,python=platform.python_version(),
            dataset_index_sha256=digest(index),source_provenance=metadata["provenance"],
            implementation_sha256={name:hashlib.sha256(content).hexdigest() for name,content in implementation.items()},
            ranker_reference=None if reference_path is None else dict(path=reference_path.name,sha256=digest(reference_path)),
            protocol=dict(cohort="observed complete consecutive origin/target pair; no status/history-based per-method exclusion",
                target_event="at least one verified 0-to-1 product opening at t+1",target_count="number of verified product openings at t+1",
                point_in_time="scores and group-frequency calibration use only labels ending <= origin; RFM definitions frozen at fit_month",
                population_baseline="all completed prior customer-month pairs",selection="exact top 10% mass with equal fractional weights across cutoff ties",
                group_probability="(past events + prior * pooled past event rate)/(past group pairs + prior)",
                CLV_event_probability="1-exp(-predicted_acquisitions_1m); Poisson-link assumption, not an independently calibrated classifier",
                affinity_customer_score="maximum current unowned-product affinity; new explicit adapter for customer prioritization, not a calibrated probability; Brier unavailable",
                Brier="event probabilities only; affinity Brier left empty",averaging="equal mean of monthly metrics, never called pooled",
                product_ranking="24 products, mask current ownership, top 7 with fixed product-order ties",
                temporal_scope="development rolling backtest; existing research already used these months; no untouched holdout or causal campaign uplift"))
        write_json(out/"evaluation_manifest.json",manifest)
        from .unified_report import render_report
        render_report(out,tables,manifest)
        print(f"Unified evaluation COMPLETE: {out}",flush=True)
        return manifest
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index",required=True,type=Path)
    parser.add_argument("--source-run",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--origins",nargs="+",default=["2015-12","2016-01","2016-02","2016-03","2016-04"])
    parser.add_argument("--rfm-fit-month",default="2015-11")
    parser.add_argument("--group-prior",type=float,default=100.)
    parser.add_argument("--min-stability-support",type=int,default=100)
    parser.add_argument("--publish-dir",type=Path,help="Optional new directory for aggregate CSV/PNG/Markdown/HTML only")
    args = parser.parse_args()
    if args.publish_dir and args.publish_dir.exists():
        parser.error("Publish directory already exists; use a new directory")
    run(args.index,args.source_run,args.out,args.origins,args.rfm_fit_month,args.group_prior,args.min_stability_support)
    if args.publish_dir:
        args.publish_dir.mkdir(parents=True)
        for path in args.out.iterdir():
            if path.suffix in [".csv",".png",".md",".html"]:
                shutil.copyfile(path,args.publish_dir/path.name)


if __name__ == "__main__":
    main()
