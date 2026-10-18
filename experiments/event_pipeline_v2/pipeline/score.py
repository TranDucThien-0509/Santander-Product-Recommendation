"""Re-score a completed run without training; artifacts must be trusted."""

import argparse, json, pickle
from pathlib import Path
from .predict import forecast
from .common import load_config, require


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--features", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    c = load_config(args.config)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(args.model, "rb") as f:
        package = pickle.load(f)
    # A disabled feature must not silently be enabled by a previously trained model.
    from .common import features_for

    nums, cats = features_for(c["feature_groups"])
    require(
        package["columns"] == nums + cats,
        "Config feature groups differ from the fitted model",
    )
    audit = forecast(
        package, Path(c["data"]["work_dir"]) / "cache", Path(args.features), c, out
    )
    print(json.dumps(audit))


if __name__ == "__main__":
    main()
