"""Export interpretable co-ownership matrices and evaluate on next-month events."""
import numpy as np
import pandas as pd
from pipeline.common import PRODUCTS
from pipeline.evaluate import metrics
from pipeline.features import pair
from pipeline.train import ranked_products


def matrices(frame):
    ownership = frame[PRODUCTS].to_numpy(dtype="int64")
    counts = ownership.T @ ownership
    marginal = ownership.sum(axis=0)
    confidence = np.divide(counts, marginal[:, None], out=np.zeros((24, 24)), where=marginal[:, None] > 0)
    prevalence = marginal / max(len(frame), 1)
    lift = np.divide(confidence, prevalence[None, :], out=np.zeros((24, 24)), where=prevalence[None, :] > 0)
    support = counts / max(len(frame), 1)
    return counts, confidence, lift, support


def audit_affinity(panel, out):
    current = panel.features(panel.months[-1])
    counts, confidence, lift, support = matrices(current)
    for name, matrix in [("counts", counts), ("confidence", confidence), ("lift", lift), ("support", support)]:
        pd.DataFrame(matrix, index=PRODUCTS, columns=PRODUCTS).to_csv(out / f"affinity_{name}_24x24.csv")
    rules = []
    for i, a in enumerate(PRODUCTS):
        for j, b in enumerate(PRODUCTS):
            if i != j and counts[i, j] >= 5:
                rules.append(dict(antecedent=a, consequent=b, count=int(counts[i, j]),
                    support=float(support[i, j]), confidence=float(confidence[i, j]), lift=float(lift[i, j])))
    pd.DataFrame(rules, columns=["antecedent", "consequent", "count", "support", "confidence", "lift"]).to_csv(out / "affinity_pair_rules.csv", index=False)
    origin = panel.months[-2]
    source = panel.features(origin)
    ids, target, _ = pair(panel.cache, origin)
    q = source.loc[ids, PRODUCTS].to_numpy()
    _, conf, _, _ = matrices(source)
    np.fill_diagonal(conf, 0)
    score = q @ conf
    # Acquisition popularity is learned only from the last already-known pair.
    past_origin = panel.months[-3]
    _, past_y, _ = pair(panel.cache, past_origin)
    popularity = past_y.mean(axis=0) if len(past_y) else np.zeros(24)
    results = []
    for method, values in [("coownership_confidence", score), ("past_acquisition_popularity", np.tile(popularity, (len(q), 1)))]:
        ranks = ranked_products(values, q)
        results.append(dict(method=method, origin=origin, **metrics(target, ranks)))
    pd.DataFrame(results).to_csv(out / "affinity_next_month_benchmark.csv", index=False)
    return results
