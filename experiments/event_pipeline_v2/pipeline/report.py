"""Publish aggregate sample evidence and choose flags using validation only."""
import argparse
import copy
import json
from pathlib import Path

from .common import write_json, require


def report(run, sample_manifest, output, selected_config):
    run = Path(run)
    require(json.loads((run / "completed.json").read_text())["status"] == "success",
            "run has not completed")
    rows = json.loads((run / "comparison.json").read_text())
    sample = json.loads(Path(sample_manifest).read_text())
    config = json.loads((run / "config.resolved.json").read_text())
    environment = json.loads((run / "environment.json").read_text())
    winner = max(rows, key=lambda r: (r["validation"]["map_at_7_all"],
                                    -sum(r["feature_groups"].values())))
    selected = copy.deepcopy(config)
    selected["feature_groups"] = winner["feature_groups"]
    selected["run"].update(name="validation_selected", ablation=False)
    write_json(selected_config, selected)
    write_json(run / "selection.json", dict(variant=winner["variant"],
               criterion="highest validation MAP@7_all; ties favor fewer enabled groups",
               validation_map_at_7_all=winner["validation"]["map_at_7_all"],
               feature_groups=winner["feature_groups"], test_used_for_selection=False))
    clean = copy.deepcopy(config)
    clean["data"].update(train_csv_or_zip="data/customer_sample/train_ver2.csv",
                         work_dir="artifacts/sample-10k-seed42", prediction_roster_csv_or_zip=None)
    lines = ["# Santander sample ablation", "",
             "Measured on 18/10/2026 (Vietnam time); temporal development backtest.", "",
             f"Fixed-ID sample: **{sample['selected_customers']:,} customers, {sample['rows']:,} snapshots**, "
             "all 17 months retained, SplitMix64 smallest hashes, seed 42. "
             "The sample is drawn across the full ID population, including late entrants.", "",
             "Source: `gs://uit-thien-santander-ds/raw/train_ver2.csv`, generation `1789365289268389`.",
             f"Raw SHA256: `{sample['source_sha256']}`.",
             f"Sample SHA256: `{sample['sample_sha256']}`.",
             f"Selected ID set SHA256: `{sample['selected_ids_sha256']}`.", "",
             "## B0–B6 results", "",
             "| Variant | Val MAP all | Val MAP buyers | Test MAP all | Test MAP buyers | Test Recall buyers | Eligible val/test | Seconds | Peak RSS MiB |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for i, row in enumerate(rows):
        v, t, r = row["validation"], row["test"], row["resources"]
        lines.append(f"| B{i} {row['variant']} | {v['map_at_7_all']:.6f} | {v['map_at_7_buyers']:.6f} | "
                     f"{t['map_at_7_all']:.6f} | {t['map_at_7_buyers']:.6f} | {t['recall_at_7_buyers']:.6f} | "
                     f"{v['n_all']:,}/{t['n_all']:,} | {r['wall_seconds']:.2f} | {r['peak_process_rss_mb']:.1f} |")
    feature_resources = json.loads((run / "feature_build_resources.json").read_text())
    last_forecast = json.loads((run / rows[-1]["variant"] / "forecast_audit.json").read_text())
    t, v = rows[0]["test"], rows[0]["validation"]
    require(len({r["validation"]["n_all"] for r in rows}) == 1 and
            len({r["test"]["n_all"] for r in rows}) == 1, "cohorts differ across variants")
    require(last_forecast["ownership_violations"] == 0, "ownership audit failed")
    lines += ["", "All variants share sample, eligible cohort, origins, seed, caps and model parameters.",
              f"Validation buyers: {v['n_buyers']:,}/{v['n_all']:,} ({v['buyer_prevalence']:.4%}); "
              f"test buyers: {t['n_buyers']:,}/{t['n_all']:,} ({t['buyer_prevalence']:.4%}).",
              f"Recommendation coverage (test): {t['recommendation_coverage']:.4%}.",
              f"Forecast: {last_forecast['n_predictions']:,} predictions, "
              f"{last_forecast['n_fallback']} ownership-unverified fallbacks, "
              f"{last_forecast['ownership_violations']} owned-product violations.", "",
              f"Shared feature construction: {feature_resources['wall_seconds']:.2f} seconds, "
              f"{feature_resources['peak_process_rss_mb']:.1f} MiB peak sampled process RSS.",
              "Variant seconds include evaluation-model fit and validation/test scoring. "
              "Shared feature construction and final forecast refit are separate. RSS is process-wide "
              "sampled every 0.1s, includes native allocations and shared data, and is not incremental "
              "per-group memory. These are local Windows measurements, not cloud billing estimates.", "",
              "## Validation selection", "",
              f"Selected **{winner['variant']}** using highest validation MAP@7_all; ties favor fewer groups. "
              "Test metrics were not used for selection. No hyperparameter tuning was performed.",
              "The ablation run's forecast belongs to all_enabled. A separate run using "
              "`configs/selected.local.json` creates the validation-selected forecast and retains "
              "a separate evaluation_model and forecast_model.", "",
              "## Reproduce", "", "From `experiments/event_pipeline_v2/`:", "", "```bash",
              "python -m pipeline.sample --source data/train_ver2.csv --out data/customer_sample/train_ver2.csv --customers 10000 --seed 42",
              "# Save the sanitized config below as configs/config.local.json; adjust local paths.",
              "OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m pipeline.run_pipeline --config configs/config.local.json",
              "python -m pipeline.report --run artifacts/sample-10k-seed42/runs/RUN_ID --sample-manifest data/customer_sample/train_ver2.manifest.json --out docs/SAMPLE_BENCHMARK.md --selected-config configs/selected.local.json",
              "python -m pipeline.run_pipeline --config configs/selected.local.json", "```", "",
              "```json", json.dumps(clean, indent=2), "```", "", "Runtime versions:", "", "```json",
              json.dumps(environment, indent=2), "```", "",
              "Raw data, customer IDs, per-customer features/predictions and models are not versioned. "
              "Only aggregate results and sanitized settings are published here. Full-data notebook "
              "parity, cloud sample and full training status are tracked in VALIDATION.md.", ""]
    Path(output).write_text("\n".join(lines), encoding="utf-8")
    print(f"Selected {winner['variant']} from validation", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True)
    p.add_argument("--sample-manifest", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--selected-config", required=True)
    args = p.parse_args()
    report(args.run, args.sample_manifest, args.out, args.selected_config)


if __name__ == "__main__":
    main()
