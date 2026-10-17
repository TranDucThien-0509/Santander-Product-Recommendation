from pathlib import Path
import numpy as np
import pandas as pd
from .common import PRODUCTS, require, shift
from .features import pair
from .ingest import csv_source
from .train import predict_scores, ranked_products


def forecast(package, cache, feature_dir, c, out):
    month = c["data"]["forecast_month"]
    q = pd.read_parquet(feature_dir / f"{month}.parquet").set_index("customer_id")
    q = q.loc[q.product_complete.eq(1)]
    # Score eligible current customers regardless of whether next month's event occurs.
    scores = predict_scores(package, q)
    ranks = ranked_products(scores, q[PRODUCTS].to_numpy())
    own = q[PRODUCTS].to_numpy()
    violations = sum(int(own[i, j] != 0) for i, ranking in enumerate(ranks) for j in ranking)
    require(violations == 0, "Ownership mask violated")
    result = pd.DataFrame(
        {
            "ncodpers": q.index,
            "added_products": [" ".join(PRODUCTS[j] for j in r) for r in ranks],
            "status": "current_complete_snapshot",
        }
    )
    roster = c["data"].get("prediction_roster_csv_or_zip")
    if roster:
        pieces = []

        def consume(src):
            for z in pd.read_csv(
                src, usecols=["ncodpers"], chunksize=c["data"]["chunk_size"]
            ):
                pieces.append(z)

        csv_source(roster, "test_ver2.csv", consume)
        ids = pd.concat(pieces, ignore_index=True)
        require(
            ids.ncodpers.notna().all() and ids.ncodpers.is_unique,
            "Roster IDs must be unique and non-null",
        )
        result = ids.merge(result, on="ncodpers", how="left", validate="one_to_one")
        # Explicit cold-start fallback. Ownership cannot be verified for these IDs.
        hist_ids, y, _ = pair(cache, shift(month, -1))
        pop = y.sum(axis=0)
        fallback = " ".join(PRODUCTS[j] for j in np.argsort(-pop, kind="stable")[:7])
        result["added_products"] = result.added_products.fillna(fallback)
        result["status"] = result.status.fillna("fallback_ownership_unverified")
    out = Path(out)
    result.to_csv(out / "predictions_with_status.csv", index=False)
    result[["ncodpers", "added_products"]].to_csv(out / "submission.csv", index=False)
    return dict(
        n_predictions=len(result),
        n_fallback=int(result.status.ne("current_complete_snapshot").sum()),
        ownership_violations=violations,
        ownership_verified_predictions=int(result.status.eq("current_complete_snapshot").sum()),
    )
