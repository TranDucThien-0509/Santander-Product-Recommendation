"""python -m pipeline.run_pipeline --config configs/default.json"""

import argparse, copy, datetime, json, platform, re
from pathlib import Path
import importlib.metadata
from .common import load_config, validate_config, config_hash, require, write_json, GROUPS
from .profiling import Profile
from .mlflow_tracking import ExperimentTracker
from .ingest import ingest
from .features import build_features
from .train import train
from .evaluate import evaluate
from .predict import forecast


def run(c):
    validate_config(c)
    require(
        bool(re.fullmatch(r"[A-Za-z0-9_-]+", c["run"]["name"])),
        "run.name must be a simple directory name",
    )
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    root = (
        Path(c["data"]["work_dir"])
        / "runs"
        / f"{c['run']['name']}_{stamp}_{config_hash(c)[:8]}"
    )
    root.mkdir(parents=True)
    write_json(root / "config.resolved.json", c)
    versions = {
        p: importlib.metadata.version(p)
        for p in ["numpy", "pandas", "pyarrow", "scikit-learn", "psutil"]
    }
    versions["python"] = platform.python_version()
    if c.get("tracking", {}).get("enabled", False):
        versions["mlflow"] = importlib.metadata.version("mlflow")
    if c["model"]["backend"] == "xgboost":
        versions["xgboost"] = importlib.metadata.version("xgboost")
    write_json(root / "environment.json", versions)
    try:
        with ExperimentTracker(c, root) as tracking:
            _execute(c, root, tracking)
    except BaseException:
        (root / "completed.json").unlink(missing_ok=True)
        raise
    print(f"COMPLETE: {root}", flush=True)
    return root


def _execute(c, root, tracking):
    print("ingest", flush=True)
    cache = ingest(c)
    write_json(
        root / "input_manifest.json", json.loads((cache / "manifest.json").read_text())
    )
    with Profile() as feature_profile:
        feature_dir = build_features(cache, c, root)
    write_json(root / "feature_build_resources.json", feature_profile.result)
    tracking.parent.metrics("feature_build", feature_profile.result)
    variants = [(c["run"]["name"], c["feature_groups"])]
    if c["run"]["ablation"]:
        variants = [("baseline", {k: False for k in GROUPS})]
        variants += [
            ("baseline_plus_" + k, {j: j == k for j in GROUPS})
            for k, on in c["feature_groups"].items()
            if on
        ]
        if sum(c["feature_groups"].values()) > 1:
            variants.append(("all_enabled", c["feature_groups"]))
    results = []
    for name, flags in variants:
        cc = copy.deepcopy(c)
        cc["feature_groups"] = flags
        with tracking.variant(name, cc) as tracked:
            with Profile() as profile:
                folder = root / name
                folder.mkdir()
                print(f"train {name}", flush=True)
                package = train(
                    cache, feature_dir, c["split"]["train_origins"], cc,
                    folder / "evaluation_model",
                )
                val = evaluate(
                    package, cache, feature_dir, c["split"]["validation_origins"],
                    folder / "validation_metrics.json",
                )
                test = evaluate(
                    package, cache, feature_dir, c["split"]["test_origins"],
                    folder / "test_metrics.json",
                )
                results.append(
                    dict(variant=name, feature_groups=flags,
                         validation=val["aggregate"], test=test["aggregate"])
                )
            results[-1]["resources"] = profile.result
            tracked.metrics("ranker", profile.result)
            if not c["run"]["ablation"] or name == variants[-1][0]:
                # Test scores above always belong to the model fit only on train origins.
                # Refit is only for a final forecast after all evaluation outcomes are known.
                if c["run"]["refit_for_forecast"]:
                    origins = sum(
                        [
                            c["split"][k]
                            for k in ["train_origins", "validation_origins", "test_origins"]
                        ],
                        [],
                    )
                    package = train(
                        cache, feature_dir, origins, cc, folder / "forecast_model"
                    )
                prediction = forecast(package, cache, feature_dir, cc, folder)
                write_json(
                    folder / "forecast_audit.json",
                    dict(
                        **prediction,
                        forecast_origin=c["data"]["forecast_month"],
                        refit=c["run"]["refit_for_forecast"],
                        recommended_variant_selection="Use validation metrics; test is for final reporting only.",
                    ),
                )
    write_json(root / "comparison.json", results)
    write_json(
        root / "completed.json",
        dict(status="success", variants=[x["variant"] for x in results]),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    run(load_config(args.config))


if __name__ == "__main__":
    main()
