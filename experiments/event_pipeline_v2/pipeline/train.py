from pathlib import Path
import pickle
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import HistGradientBoostingClassifier
from .common import (PRODUCTS, features_for, require, write_json, shift,
                     FEATURE_VERSIONS, GROUP_DEPENDENCIES)
from .features import pair


def event_training_data(cache, feature_dir, origins, c):
    nums, cats = features_for(c["feature_groups"])
    frames = []
    targets = []
    audit = []
    cap = c["model"]["max_train_event_rows"]
    rng = np.random.default_rng(c["model"]["seed"])
    # Bound memory before expanding all positive labels; equal per-origin cap.
    for origin in origins:
        ids, y, info = pair(cache, origin)
        row, col = np.nonzero(y)
        info.update(n_event_customers=int(y.any(axis=1).sum()), n_event_rows=len(row))
        audit.append(info)
        if len(row) > max(1, cap // len(origins)):
            chosen = rng.choice(len(row), max(1, cap // len(origins)), replace=False)
            row = row[chosen]
            col = col[chosen]
        info["event_rows_used"] = len(row)
        q = pd.read_parquet(feature_dir / f"{origin}.parquet").set_index("customer_id")
        frames.append(q.loc[ids[row], nums + cats])
        targets.append(col)
    require(
        bool(frames) and sum(map(len, frames)) > 0,
        "No acquisition events in training origins",
    )
    return pd.concat(frames, ignore_index=True), np.concatenate(targets), audit


def train(cache, feature_dir, origins, c, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    x, y, audit = event_training_data(cache, feature_dir, origins, c)
    nums, cats = features_for(c["feature_groups"])
    transform = ColumnTransformer(
        [
            (
                "numeric",
                Pipeline(
                    [
                        (
                            "imputer",
                            SimpleImputer(
                                strategy="median",
                                add_indicator=True,
                                keep_empty_features=True,
                            ),
                        )
                    ]
                ),
                nums,
            ),
            (
                "category",
                OneHotEncoder(
                    handle_unknown="ignore", sparse_output=False, dtype=np.float32
                ),
                cats,
            ),
        ],
        remainder="drop",
    )
    matrix = transform.fit_transform(x).astype("float32")
    classes, encoded = np.unique(y, return_inverse=True)
    require(
        len(classes) >= 2,
        "Need acquisition labels from at least two products to train a ranker",
    )
    opts = c["model"]
    if opts["backend"] == "xgboost":
        from xgboost import XGBClassifier

        model = XGBClassifier(
            objective="multi:softprob",
            num_class=len(classes),
            n_estimators=opts["n_estimators"],
            max_depth=opts["max_depth"],
            learning_rate=opts["learning_rate"],
            tree_method="hist",
            n_jobs=opts["n_jobs"],
            random_state=opts["seed"],
            eval_metric="mlogloss",
        )
    else:
        model = HistGradientBoostingClassifier(
            max_iter=opts["n_estimators"],
            max_depth=opts["max_depth"],
            learning_rate=opts["learning_rate"],
            min_samples_leaf=10,
            early_stopping=False,
            random_state=opts["seed"],
        )
    model.fit(matrix, encoded)
    package = dict(
        transform=transform,
        model=model,
        classes=classes,
        columns=nums + cats,
        products=PRODUCTS,
    )
    # Generated internally; never load pickle from untrusted sources.
    with (out / "model.pkl").open("wb") as f:
        pickle.dump(package, f)
    write_json(
        out / "feature_manifest.json",
        dict(
            feature_groups=c["feature_groups"],
            numeric_columns=nums,
            categorical_columns=cats,
            encoded_columns=transform.get_feature_names_out().tolist(),
            event_rows_used=len(x),
            product_classes_observed=[PRODUCTS[int(i)] for i in classes],
            origins=origins,
            fit_audit=audit,
            max_label_month=shift(max(origins), 1),
            product_order=PRODUCTS,
            feature_versions={k: FEATURE_VERSIONS[k] for k, on in c["feature_groups"].items() if on},
            dependencies={k: GROUP_DEPENDENCIES[k] for k, on in c["feature_groups"].items() if on},
            persona_provenance={k: c["meta_models"][k] for k in
                ["persona_rules_fit_origin", "persona_rules_label_month", "persona_rules_available_from"]}
                if c["feature_groups"]["persona"] else None,
            evaluation_scope="temporal development backtest; notebook research used these months",
            persona_method="fixed_rules_v1_not_a_newly_trained_tree",
        ),
    )
    return package


def predict_scores(package, q):
    score = np.zeros((len(q), len(PRODUCTS)), dtype="float64")
    for start in range(0, len(q), 20000):
        stop = min(start + 20000, len(q))
        x = (
            package["transform"]
            .transform(q.iloc[start:stop][package["columns"]])
            .astype("float32")
        )
        score[start:stop, package["classes"]] = package["model"].predict_proba(x)
    return score


def ranked_products(scores, ownership, k=7):
    eligible = (ownership == 0) & np.isfinite(ownership)
    masked = np.where(eligible, scores, -np.inf)
    order = np.argsort(-masked, axis=1, kind="stable")[:, :k]
    return [[int(j) for j in row if eligible[i, j]] for i, row in enumerate(order)]
