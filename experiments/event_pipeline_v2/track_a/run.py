"""Run Track A supplements against a completed, verified v2 sample run.

python -m track_a.run --run-dir /path/run --cache-dir /path/cache --out /path/new-output
"""
import argparse
import datetime
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import numpy as np
import pandas as pd
from pipeline.common import PRODUCTS, FEATURE_VERSIONS, write_json
from pipeline.mlflow_tracking import sanitize
from .data import Panel, export_events
from .eda import raw_eda, lifecycle_export
from .clv import benchmark
from .segmentation import persona_cluster, rfm_benchmark
from .affinity import audit_affinity
from .storage import digest, write_manifest

RENAMES = {"R": "rfm_recency_months", "F_event_months": "rfm_frequency_event_months",
           "M_group_points": "portfolio_propensity_points", "cluster_id": "persona_cluster_id",
           "persona_id": "persona_rule_id"}
DEFINITIONS = {
    "customer_id": "Santander ncodpers; join key only, never a model input",
    "as_of_month": "Month of the observed ownership snapshot; no future target fields",
    "rfm_recency_months": "Months since last observed consecutive-complete-snapshot 0-to-1 acquisition; null before any event",
    "rfm_frequency_event_months": "Cumulative number of observed months with at least one acquisition, not total product count",
    "portfolio_propensity_points": "100 times historical exact-portfolio next-month event rate, using only completed past labels; pooled fallback",
    "predicted_acquisitions_1m": "Point-in-time Poisson boosting prediction of next-month product count; proxy, not money",
    "persona_rule_id": "Frozen P1-P6 rule labels; UNKNOWN if insufficient valid history or rules unavailable",
    "persona_cluster_id": "Nominal C1-Ck multiblock KMeans cluster, transform and centers frozen at persona_cluster_fit_month",
    "presence_lifecycle": "Original panel-presence lifecycle from v2, including prior gap and relationship age",
    "lifecycle": "Track A activity/death enrichment: indfall=S -> Churned; current inactive -> At-risk except New/Win-back",
    "cross_sell_eligible": "Observed snapshot, known indfall=N and activity=1; missing status is ineligible",
    "n_products": "Sum of all 24 complete ownership flags at as-of month",
    "rfm_quantile_333": "Frozen fit-month R/F/current-portfolio quantiles; duplicate edges collapse; no-event R has own bucket",
    "rfm_kmeans_6": "Frozen fit-month six-center KMeans on R/F/current-portfolio and no-event indicator",
    "rfm_rule_based": "Fixed R <=1/<=3/>3; F 0/1/>=2; current products <=2/<=4/>4; missing R separate",
}


def feature_spec(frame, panel, fit_month):
    schema = []
    for col, dtype in frame.dtypes.items():
        role = "entity" if col == "customer_id" else "event_time" if col == "as_of_month" else "feature"
        definition = DEFINITIONS.get(col)
        if definition is None:
            definition = "Current 0/1 ownership flag; incomplete portfolios excluded" if col in PRODUCTS else (
                "Past-only smoothed temporal ownership-to-acquisition score for " + col[len("affinity_"):] if col.startswith("affinity_") else
                "Source field/quality metadata defined in event_pipeline_v2/docs/FEATURE_CATALOG.md and Track A feature spec")
        schema.append(dict(name=col, dtype=str(dtype), nullable=bool(frame[col].isna().any()), role=role, definition=definition))
    return dict(feature_view="santander_track_a_customer_month_v1", version="1.0.0",
        entity_keys=["customer_id"], event_time="as_of_month", available_time="source snapshot publication time",
        physical_time_type="YYYY-MM period; resolve to actual publication timestamp before production ingestion",
        naming="snake_case; source-to-canonical map below", source_to_canonical=RENAMES,
        refresh="monthly and on corrected upstream snapshots", ttl="45 days maximum, invalidate on next snapshot",
        point_in_time_join="latest available snapshot <= scoring timestamp, not expired; never forward-fill across panel absence",
        schema=schema, source_versions=FEATURE_VERSIONS, persona_cluster_fit_month=fit_month,
        offline_only=["long-horizon labels", "evaluation outcomes"], data_owner="Track A DS",
        quality_checks=["unique customer_id/as_of_month", "nonnegative F", "ownership in {0,1}",
            "missing R iff no observed event", "CLV train label cutoff <= origin", "product order locked to PRODUCTS"],
        limitations=["template feature store handoff; no production registry deployed", "Kaggle research data only"],
        source_history_end=panel.months[-1])


def make_plots(out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    monthly = pd.read_csv(out / "monthly_snapshots.csv")
    clv = pd.read_csv(out / "clv_6m_benchmark.csv")
    persona = pd.read_csv(out / "persona_cluster_profiles.csv")
    rfm = pd.read_csv(out / "rfm_membership_stability.csv")
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    axes[0, 0].plot(monthly.month, monthly.snapshots, marker="o", markersize=3)
    axes[0, 0].tick_params(axis="x", rotation=70, labelsize=7)
    axes[0, 0].set_title("Observed sample snapshots by month")
    axes[0, 1].barh(clv.method, clv.RMSE)
    axes[0, 1].set_title("6-month acquisitions RMSE (lower is better)")
    axes[1, 0].bar(persona.persona, persona["share"] * 100)
    axes[1, 0].set_title("Persona cluster share, latest snapshot (%)")
    for method, rows in rfm.groupby("method"):
        axes[1, 1].plot(rows.target_month, rows.adjusted_rand, marker="o", label=method)
    axes[1, 1].tick_params(axis="x", rotation=60, labelsize=7)
    axes[1, 1].legend(fontsize=7)
    axes[1, 1].set_title("RFM membership stability (common-customer ARI)")
    fig.savefig(out / "track_a_overview.png", dpi=140)
    plt.close(fig)


def report(out, summary):
    eda = summary["eda"]
    missing = eda["missing_share"]
    lines = ["# Track A — bằng chứng bổ sung trên sample cố định 10k\n",
        "Đây là research development backtest, không phải holdout độc lập, kết quả toàn bộ full data hay measured marketing uplift.\n",
        "## EDA — 8 finding có số đo\n",
        f"1. Có {eda['rows']:,} snapshot, {eda['months']} tháng ({eda['first_month']}–{eda['last_month']}); không phải giao dịch/invoice.",
        f"2. Renta thiếu {missing.get('renta', 0):.2%}; không coi renta là revenue hoặc giá trị giao dịch.",
        f"3. Age thiếu {missing.get('age', 0):.2%} ở raw; cleaning tuổi ngoài 0–110 thực hiện trong ingest v2, giữ khách trẻ.",
        f"4. Cardinality canal_entrada: {eda['cardinality'].get('canal_entrada', 0)}; cần xử lý category chưa thấy khi scoring.",
        f"5. Cardinality segmento: {eda['cardinality'].get('segmento', 0)} và pais_residencia: {eda['cardinality'].get('pais_residencia', 0)}.",
        f"6. Trung bình {eda['mean_owned_products']:.3f} sản phẩm trên snapshot có đủ 24 cờ; bảng phân bố giữ riêng incomplete snapshot.",
        f"7. Trung bình {eda['mean_absence_or_incomplete_rate']:.2%} cohort complete hiện tại vắng/không đủ sản phẩm ở tháng kế. Đây không chứng minh rời ngân hàng.",
        f"8. Có {summary['events']['acquisition_rows']:,} product-level acquisitions được xác minh bằng hai tháng liền kề; khách mới/gap return không tự tạo event.\n",
        "Xem raw_column_audit.csv (có cod_prov/indrel_1mes), monthly_snapshots.csv, segment_product_trend.csv, portfolio_distribution.csv và panel_presence.csv.\n",
        "## CLV 6 tháng\n",
        "| Method | Fit status | RMSE | MAE | Capture10 |\n|---|---|---:|---:|---:|\n" +
        "\n".join(f"| {r['method']} | {r['fit_status']} | {r['RMSE']:.6f} | {r['MAE']:.6f} | {r['capture10'] if r['capture10'] is not None else 'NA'} |" for r in summary["clv"]),
        "\nBG/NBD đếm repeat event-month sau first observed event; Gamma-Gamma thử giá trị proxy là số sản phẩm/event-month. Khách không đủ history dùng fallback mean, tỷ trọng ghi riêng trong clv_probabilistic_fit_status.csv. Fit thất bại không được diễn giải là model đã fit.",
        f"\nTrain labels tối đa {summary['clv_audit']['max_train_label_month']} ≤ cutoff {summary['clv_audit']['origin']}; nhãn đánh giá đến {summary['clv_audit']['label_end']}; coverage {summary['clv_audit']['label_coverage']:.2%}. Không chọn lại model trên backtest 6m. 12m chưa đủ lịch sử cho supervised train/validation/test có mốc thời gian hợp lệ.",
        "\nSai số theo RFM, NoObservedEvent/HasEvent và khách history <3 pair nằm trong clv_6m_segment_errors.csv.\n",
        "## RFM, affinity và persona\n",
        "Quantile/KMeans/rule được fit ở cùng cutoff và giữ nguyên ở tháng sau; báo actual groups, silhouette, membership ARI và stay rate. Predictive AP/Lift/Brier của nghiên cứu gốc giữ riêng trong research/track_a/docs/02_benchmarks.md, không trộn cohort.",
        f"\nPersona clustering dùng RFM + CLV + portfolio + affinity + demographics; chọn k={summary['persona']['k']} bằng fit-only silhouette sau ngưỡng min-share 1%. Xem persona_cluster_cards.md và các bảng bootstrap/temporal stability. P1–P6 rule và C1–Ck clustering là hai phương án có version riêng.",
        "\nAffinity 24×24 có count/support/confidence/lift. Benchmark next-month ở affinity_next_month_benchmark.csv; Apriori bộ ba và item2vec SGNS gốc có notebook 06 cùng benchmark/provenance trong research/track_a. Ma trận tháng cuối chỉ mô tả, không chấm lên nhãn quá khứ.\n",
        "## Lifecycle và bàn giao\n",
        "Giữ presence_lifecycle của v2 và thêm lifecycle dùng activity/death ở bảng export. indfall=S → Churned; observed inactive → At-risk trừ New/Win-back; thiếu activity/death không giả là known/eligible. Sự biến mất chỉ là panel absence.",
        "\nProcessed dataset và event partitions nằm private ở processed/. feature_store_spec.json mô tả entity, schema, naming, version, availability và TTL. Chỉ publish processed_manifest.json cùng các file được liệt kê, không đưa customer-level rows lên GitHub. Provider storage theo lựa chọn triển khai riêng; receipt xác minh cloud phải được ghi riêng. Upload GCS không được ghi thành AWS S3.\n",
        "## Giới hạn và trạng thái\n",
        "- Sample này gồm 10k ID cố định giữ toàn bộ tháng; không suy rộng full data.",
        "- Nhãn CLV dài hạn chỉ có khi đủ mọi cặp tương lai, nên có selection bias.",
        "- Event lặp lại, finite product catalog và thời gian tháng vi phạm một số giả định retail BG/NBD/Gamma-Gamma.",
        "- Cluster membership stability không phải causal uplift hay persona đã được business phê duyệt.",
        "- EDA cũ notebook 00 có hạn chế đã audit; 8 finding trên được tính lại từ sample, không chép suy luận cũ.",
        "- MLflow ghi aggregate metrics/artifacts; không log raw, events theo khách hay bảng processed lên tracking.\n",
        "![Track A overview](track_a_overview.png)\n"]
    (out / "TRACK_A_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def log_mlflow(out, summary, uri, artifact_location=None):
    from mlflow import MlflowClient
    client = MlflowClient(tracking_uri=uri)
    name = "santander-track-a"
    experiment = client.get_experiment_by_name(name)
    eid = experiment.experiment_id if experiment else client.create_experiment(name, artifact_location=artifact_location)
    parent = client.create_run(eid, tags={"mlflow.runName": out.name, "santander.role": "track_a_research",
        "evaluation.scope": "sample development research", "source.v2_run": summary["source_run"]})
    pid = parent.info.run_id
    try:
        for row in summary["clv"]:
            child = client.create_run(eid, tags={"mlflow.runName": "clv_6m_" + row["method"], "mlflow.parentRunId": pid,
                "fit.status": row["fit_status"], "evaluation.scope": "fixed-config 6m development backtest"})
            cid = child.info.run_id
            try:
                for key, value in row.items():
                    if type(value) in (int, float) and math.isfinite(value):
                        client.log_metric(cid, key, value)
                client.log_param(cid, "horizon_months", 6)
                client.log_param(cid, "max_train_label_month", summary["clv_audit"]["max_train_label_month"])
                client.log_param(cid, "origin", summary["clv_audit"]["origin"])
            except BaseException:
                client.set_terminated(cid, "FAILED")
                raise
            client.set_terminated(cid, "FINISHED")
        client.log_metric(pid, "persona.selected_k", summary["persona"]["k"])
        client.log_metric(pid, "persona.fit_silhouette", summary["persona"]["silhouette"])
        for path in sorted(out.iterdir()):
            if path.is_file() and path.suffix in (".csv", ".md", ".png"):
                client.log_artifact(pid, str(path))
        for name in ["clv_6m_audit.json", "persona_cluster_spec.json", "rfm_tiering_spec.json", "feature_store_spec.json", "environment.json", "run_provenance.json"]:
            client.log_dict(pid, sanitize(json.loads((out / name).read_text(encoding="utf-8"))), name)
    except BaseException:
        client.set_terminated(pid, "FAILED")
        raise
    client.set_terminated(pid, "FINISHED")
    return dict(experiment_id=eid, parent_run_id=pid)


def run(run_dir, cache_dir, out, fit_month="2015-11", tracking_uri=None, artifact_location=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    panel = Panel(run_dir, cache_dir)
    if fit_month not in panel.months:
        raise ValueError("Persona fit month outside source history")
    processed = out / "processed"
    processed.mkdir()
    print("Track A: raw EDA", flush=True)
    eda, flags = raw_eda(panel.config["data"]["train_csv_or_zip"], panel, out)
    print("Track A: verified event export", flush=True)
    events, event_files = export_events(panel, processed / "acquisition_events")
    lifecycle_counts, lifecycle = lifecycle_export(panel, flags, processed / "lifecycle_latest.parquet")
    print("Track A: RFM tiering and membership stability", flush=True)
    rfm = rfm_benchmark(panel, out, fit_month)
    print("Track A: causal 6m CLV benchmark", flush=True)
    clv, clv_audit = benchmark(panel, out)
    print("Track A: multiblock persona clustering", flush=True)
    frame, persona = persona_cluster(panel, out, fit_month)
    frame = frame.join(rfm)
    frame["presence_lifecycle"] = lifecycle.presence_lifecycle
    frame["lifecycle"] = lifecycle.lifecycle
    frame["cross_sell_eligible"] = lifecycle.cross_sell_eligible
    frame = frame.reset_index().rename(columns=RENAMES)
    frame.columns = [c.lower() for c in frame.columns]
    frame.to_parquet(processed / "customer_features_latest.parquet", index=False)
    spec = feature_spec(frame, panel, fit_month)
    write_json(out / "feature_store_spec.json", spec)
    write_json(processed / "feature_store_spec.json", spec)
    print("Track A: affinity matrices and next-month benchmark", flush=True)
    affinity = audit_affinity(panel, out)
    versions = {p: importlib.metadata.version(p) for p in ["numpy", "pandas", "scikit-learn", "lifetimes", "mlflow", "shap"]}
    versions["python"] = platform.python_version()
    write_json(out / "environment.json", versions)
    write_json(out / "run_provenance.json", dict(
        implementation_sha256={p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
        source_run=panel.root.name, source_config_sha256=digest(panel.root / "config.resolved.json"),
        source_cache_manifest_sha256=digest(panel.cache / "manifest.json"),
        source_point_in_time_audit_sha256=digest(panel.root / "point_in_time_audit.json"),
        raw_sha256=digest(panel.config["data"]["train_csv_or_zip"])))
    write_manifest(processed, event_files + [processed / "customer_features_latest.parquet", processed / "lifecycle_latest.parquet", processed / "feature_store_spec.json"])
    summary = dict(source_run=Path(run_dir).name, sample_scope="fixed customer IDs, all source months",
        eda=eda, events=events, lifecycle=lifecycle_counts, clv=clv, clv_audit=clv_audit, persona=persona, affinity=affinity)
    make_plots(out)
    report(out, summary)
    write_json(out / "summary.json", summary)
    if tracking_uri:
        summary["mlflow"] = log_mlflow(out, summary, tracking_uri, artifact_location)
    write_json(out / "completed.json", dict(status="success", created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        mlflow=summary.get("mlflow"), source_run=summary["source_run"]))
    print(f"Track A COMPLETE: {out}", flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--out", required=True, help="New directory; never overwrites a previous run")
    parser.add_argument("--fit-month", default="2015-11")
    parser.add_argument("--tracking-uri")
    parser.add_argument("--artifact-location")
    args = parser.parse_args()
    run(args.run_dir, args.cache_dir, args.out, args.fit_month, args.tracking_uri, args.artifact_location)


if __name__ == "__main__":
    main()
