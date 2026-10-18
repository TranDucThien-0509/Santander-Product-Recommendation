import numpy as np
import pandas as pd
from .common import PRODUCTS, require, write_json
from .features import pair
from .train import predict_scores, ranked_products


def metrics(y, ranks):
    require(len(y) == len(ranks), "One ranking is required for each label row")
    require(all(len(r) <= 7 and len(set(r)) == len(r) for r in ranks),
            "Rankings must contain at most seven distinct products")
    ap = []
    recall = []
    buyers = y.any(axis=1)
    for row, ranking in zip(y, ranks):
        n = int(row.sum())
        hits = 0
        precision = 0.0
        for rank, j in enumerate(ranking, 1):
            if row[j]:
                hits += 1
                precision += hits / rank
        ap.append(precision / min(n, 7) if n else 0.0)
        if n:
            recall.append(hits / n)
    ap = np.asarray(ap)
    n = len(y)
    b = int(buyers.sum())
    return dict(
        n_all=n,
        n_buyers=b,
        buyer_prevalence=b / n if n else None,
        map_at_7_all=float(ap.mean()) if n else None,
        map_at_7_buyers=float(ap[buyers].mean()) if b else None,
        recall_at_7_buyers=float(np.mean(recall)) if b else None,
        recommendation_coverage=sum(bool(r) for r in ranks) / n if n else None,
    )


def evaluate(package, cache, feature_dir, origins, out):
    reports = []
    all_y = []
    all_ranks = []
    for origin in origins:
        ids, y, audit = pair(cache, origin)
        require(len(ids) > 0, f"No eligible evaluation pairs: {origin}")
        q = (
            pd.read_parquet(feature_dir / f"{origin}.parquet")
            .set_index("customer_id")
            .loc[ids]
        )
        ranks = ranked_products(predict_scores(package, q), q[PRODUCTS].to_numpy())
        reports.append(dict(**audit, **metrics(y, ranks)))
        all_y.append(y)
        all_ranks.extend(ranks)
    result = dict(
        aggregate=metrics(np.concatenate(all_y), all_ranks), by_origin=reports,
        evaluation_scope="temporal development backtest",
    )
    write_json(out, result)
    return result
