"""Metrics with shared denominators and fractional, order-independent cutoff ties."""
import math

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score


def top_fraction_weights(scores, fraction=0.1):
    scores = np.asarray(scores, dtype=float)
    if scores.ndim != 1 or not len(scores) or not np.isfinite(scores).all():
        raise ValueError("A nonempty finite score vector is required")
    if not 0 < fraction <= 1:
        raise ValueError("Selection fraction must be in (0,1]")
    mass = fraction * len(scores)
    cutoff = np.partition(scores, len(scores) - math.ceil(mass))[len(scores) - math.ceil(mass)]
    above, tied = scores > cutoff, scores == cutoff
    weights = above.astype(float)
    weights[tied] = np.clip((mass - above.sum()) / tied.sum(), 0, 1)
    return weights, dict(selected_mass=float(weights.sum()), cutoff=float(cutoff), cutoff_ties=int(tied.sum()))


def customer_metrics(scores, acquisitions, fraction=0.1, event_probability=None, predicted_count=None):
    scores, acquisitions = np.asarray(scores, dtype=float), np.asarray(acquisitions, dtype=float)
    if scores.shape != acquisitions.shape or (acquisitions < 0).any() or not np.isfinite(acquisitions).all():
        raise ValueError("Scores and nonnegative outcomes must have the same shape")
    buyers = acquisitions > 0
    n, positives, total = len(buyers), int(buyers.sum()), float(acquisitions.sum())
    weights, selection = top_fraction_weights(scores, fraction)
    selected_events = float(weights @ buyers)
    selected_products = float(weights @ acquisitions)
    precision = selected_events / selection["selected_mass"]
    prevalence = positives / n
    result = dict(n_all=n, n_buyers=positives, product_acquisitions=int(total), buyer_prevalence=prevalence,
        AP=float(average_precision_score(buyers, scores)) if positives else None,
        AUC=float(roc_auc_score(buyers, scores)) if 0 < positives < n else None,
        precision10=precision, lift10_buyers=precision / prevalence if positives else None,
        capture10_buyers=selected_events / positives if positives else None,
        capture10_products=selected_products / total if total else None,
        lift10_products=(selected_products / total) / fraction if total else None,
        oracle_lift10_buyers=min(positives, fraction*n) / (fraction*n*prevalence) if positives else None,
        Brier=None, probability_calibration_ratio=None, MAE_count=None, RMSE_count=None,
        count_calibration_ratio=None, **selection)
    if event_probability is not None:
        probability = np.asarray(event_probability, dtype=float)
        if probability.shape != scores.shape or not np.isfinite(probability).all() or ((probability < 0) | (probability > 1)).any():
            raise ValueError("Event probabilities must be finite and in [0,1]")
        result.update(Brier=float(np.mean((probability-buyers)**2)),
            probability_calibration_ratio=float(probability.sum()/positives) if positives else None)
    if predicted_count is not None:
        prediction = np.asarray(predicted_count, dtype=float)
        if prediction.shape != scores.shape or not np.isfinite(prediction).all() or (prediction < 0).any():
            raise ValueError("Count predictions must be finite and nonnegative")
        error = prediction - acquisitions
        result.update(MAE_count=float(np.mean(np.abs(error))), RMSE_count=float(np.sqrt(np.mean(error**2))),
            count_calibration_ratio=float(prediction.sum()/total) if total else None)
    return result


def wilson(events, n):
    if not n:
        return None, None
    z = 1.959963984540054
    p = events/n
    center = (p+z*z/(2*n))/(1+z*z/n)
    radius = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return center-radius, center+radius


def mask_matrix(masks):
    masks = np.asarray(masks, dtype=np.int64)
    if ((masks < 0) | (masks >= 1 << 24)).any():
        raise ValueError("Ownership/event masks must contain exactly the 24-product domain")
    return ((masks[:, None] >> np.arange(24, dtype=np.int64)) & 1).astype(bool)


class ProductMetrics:
    """Vectorized equivalent of pipeline.evaluate.metrics, processed in bounded batches."""
    def __init__(self):
        self.n = self.buyers = self.recommended = self.products = 0
        self.ap_sum = self.recall_sum = self.recall_ceiling_sum = 0.

    def update(self, scores, owned_masks, acquired_masks):
        scores = np.asarray(scores, dtype=float)
        own, truth = mask_matrix(owned_masks), mask_matrix(acquired_masks)
        if scores.shape != own.shape or not np.isfinite(scores).all() or (truth & own).any():
            raise ValueError("Finite 24-product scores and verified unowned acquisition labels are required")
        masked = np.where(own, -np.inf, scores)
        ranking = np.argsort(-masked, axis=1, kind="stable")[:, :7]
        allowed = ~np.take_along_axis(own, ranking, axis=1)
        hits = np.take_along_axis(truth, ranking, axis=1) & allowed
        counts = truth.sum(axis=1)
        buyers = counts > 0
        numerator = ((np.cumsum(hits, axis=1) / np.arange(1, 8)) * hits).sum(axis=1)
        ap = np.divide(numerator, np.minimum(counts, 7), out=np.zeros(len(counts)), where=buyers)
        self.n += len(counts)
        self.buyers += int(buyers.sum())
        self.products += int(counts.sum())
        self.recommended += int(allowed.any(axis=1).sum())
        self.ap_sum += float(ap.sum())
        self.recall_sum += float((hits.sum(axis=1)[buyers]/counts[buyers]).sum())
        self.recall_ceiling_sum += float((np.minimum(counts[buyers], 7)/counts[buyers]).sum())

    def result(self):
        return dict(n_all=self.n, n_buyers=self.buyers, product_acquisitions=self.products,
            buyer_prevalence=self.buyers/self.n if self.n else None,
            map_at_7_all=self.ap_sum/self.n if self.n else None,
            map_at_7_buyers=self.ap_sum/self.buyers if self.buyers else None,
            recall_at_7_buyers=self.recall_sum/self.buyers if self.buyers else None,
            recommendation_coverage=self.recommended/self.n if self.n else None,
            map_at_7_all_ceiling=self.buyers/self.n if self.n else None,
            recall_at_7_buyers_ceiling=self.recall_ceiling_sum/self.buyers if self.buyers else None)
