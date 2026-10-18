"""Six-month acquisition-count backtest, with explicit probabilistic fallbacks."""
import warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from pipeline.common import shift, write_json

INPUTS = ["R", "F_event_months", "M_group_points", "n_products", "observed_pairs",
          "age", "renta", "antiguedad", "relationship_age_months"]


def errors(y, prediction):
    y, prediction = np.asarray(y, float), np.asarray(prediction, float)
    if len(y) == 0 or not np.isfinite(prediction).all() or (prediction < 0).any():
        raise ValueError("CLV predictions must be finite, nonnegative and nonempty")
    top_n = max(1, int(np.ceil(.1 * len(y))))
    boundary = np.partition(prediction, len(prediction) - top_n)[len(prediction) - top_n]
    above, tied = prediction > boundary, prediction == boundary
    selected_mass = y[above].sum() + y[tied].sum() * (top_n - int(above.sum())) / int(tied.sum())
    return dict(n=len(y), MAE=float(mean_absolute_error(y, prediction)),
        RMSE=float(np.sqrt(mean_squared_error(y, prediction))),
        actual_mean=float(y.mean()), predicted_mean=float(prediction.mean()),
        capture10=float(selected_mass / y.sum()) if y.sum() else None,
        calibration_ratio=float(prediction.sum() / y.sum()) if y.sum() else None)


def probabilistic(history, horizon, fallback):
    from lifetimes import BetaGeoFitter, GammaGammaFitter
    predictions = {"BGNBD": np.full(len(history), fallback, dtype=float),
                   "BGNBD_GammaGamma": np.full(len(history), fallback, dtype=float)}
    status = []
    eligible = history.event_n.gt(0) & history.bg_T.gt(0)
    data = history.loc[eligible]
    repeat = data.loc[data.bg_frequency.gt(0) & data.repeat_value.gt(0)]
    base = dict(n_current=len(history), bg_eligible_n=len(data), gamma_eligible_n=len(repeat),
        fallback_share=float(1 - eligible.mean()), horizon_months=horizon)
    if len(data) < 20 or len(repeat) < 5:
        return predictions, [{**base, "method": name, "status": "insufficient_repeat_history"} for name in predictions]
    bg = None
    for penalty in [.01, .1, 1.0]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                candidate = BetaGeoFitter(penalizer_coef=penalty)
                grouped = data.groupby(["bg_frequency", "bg_recency", "bg_T"]).size().reset_index(name="weight")
                candidate.fit(grouped.bg_frequency, grouped.bg_recency, grouped.bg_T, weights=grouped.weight)
                count = np.asarray(candidate.conditional_expected_number_of_purchases_up_to_time(
                    horizon, data.bg_frequency, data.bg_recency, data.bg_T))
            if not np.isfinite(count).all() or (count < 0).any():
                raise ValueError("Invalid BG/NBD predictions")
            bg = candidate
            break
        except (ValueError, RuntimeError, ArithmeticError) as error:
            last_error = type(error).__name__
    if bg is None:
        return predictions, [{**base, "method": name, "status": "fit_failed", "error": last_error} for name in predictions]
    mean_value = float(repeat.repeat_products.sum() / repeat.bg_frequency.sum())
    predictions["BGNBD"][eligible.to_numpy()] = count * mean_value
    status.append({**base, "method": "BGNBD", "status": "fit", "penalizer": penalty})
    gamma = None
    for penalty in [.01, .1, 1.0]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                candidate = GammaGammaFitter(penalizer_coef=penalty)
                candidate.fit(repeat.bg_frequency, repeat.repeat_value, q_constraint=True)
                # NoEvent customers keep the explicit mean fallback; first-event customers
                # receive the population prior, without inventing a repeat value.
                value = np.asarray(candidate.conditional_expected_average_profit(
                    data.bg_frequency, data.repeat_value.fillna(mean_value)))
            if not np.isfinite(value).all() or (value <= 0).any():
                raise ValueError("Invalid Gamma-Gamma values")
            gamma = candidate
            break
        except (ValueError, RuntimeError, ArithmeticError) as error:
            last_error = type(error).__name__
    if gamma is None:
        status.append({**base, "method": "BGNBD_GammaGamma", "status": "fit_failed", "error": last_error})
    else:
        predictions["BGNBD_GammaGamma"][eligible.to_numpy()] = count * value
        corr = repeat.bg_frequency.corr(repeat.repeat_value, method="spearman")
        status.append({**base, "method": "BGNBD_GammaGamma", "status": "fit", "penalizer": penalty,
            "frequency_value_spearman": float(corr) if np.isfinite(corr) else None,
            "proxy_unit": "products acquired per event-month; not money"})
    return predictions, status


def benchmark(panel, out, origin=None, horizon=6):
    origin = origin or shift(panel.months[-1], -horizon)
    origins = panel.training_origins(origin, horizon)
    if not origins:
        raise ValueError("Insufficient history for a causal long-horizon ML training set")
    train_x, train_y, used = [], [], []
    for month in origins:
        target = panel.target(month, horizon)
        if len(target):
            train_x.append(panel.features(month).loc[target.index, INPUTS])
            train_y.append(target)
            used.append(month)
    if not train_y or not sum(len(y) for y in train_y):
        raise ValueError("No continuously observed long-horizon train labels")
    x, y = pd.concat(train_x), pd.concat(train_y)
    model = HistGradientBoostingRegressor(loss="poisson", max_iter=80, max_leaf_nodes=15,
        min_samples_leaf=30, learning_rate=.06, l2_regularization=10, early_stopping=False, random_state=42)
    if y.sum() == 0:
        raise ValueError("No training acquisitions for a Poisson model")
    model.fit(x, y)
    current = panel.features(origin)
    target = panel.target(origin, horizon)
    if target.empty:
        raise ValueError("No fully observed long-horizon evaluation customers")
    history = panel.history[origin].loc[current.index]
    predictions, status = probabilistic(history, horizon, float(y.mean()))
    predictions["gradient_boosting"] = model.predict(current[INPUTS])
    predictions["historical_mean"] = np.full(len(current), y.mean())
    indexer = current.index.get_indexer(target.index)
    group = np.where(current.loc[target.index, "F_event_months"].eq(0), "NoObservedEvent", "HasEvent")
    young = current.loc[target.index, "observed_pairs"].lt(3).to_numpy()
    # RFM analysis uses observable R/F/M buckets; learned quantiles come only from training.
    f_cut = float(x.F_event_months.median())
    r_cut = float(x.R.median()) if x.R.notna().any() else 0
    m_cut = float(x.M_group_points.median()) if x.M_group_points.notna().any() else 0
    q = current.loc[target.index]
    # SHAP describes this fixed model; it is not used to tune the held-out months.
    import shap
    explain = q[INPUTS].sample(min(200, len(q)), random_state=42)
    explainer = shap.TreeExplainer(model)
    explanation = explainer(explain, check_additivity=False)
    reconstructed = np.asarray(explanation.base_values).reshape(-1) + explanation.values.sum(axis=1)
    original = model.predict(explain)
    if np.allclose(reconstructed, original, rtol=1e-5, atol=1e-6):
        link = "identity"
    elif np.allclose(np.exp(reconstructed), original, rtol=1e-5, atol=1e-6):
        link = "log_expected_acquisitions"
    else:
        raise ValueError("SHAP additive reconstruction does not match the fitted model")
    pd.DataFrame({"feature": INPUTS, "mean_abs_shap": np.abs(explanation.values).mean(axis=0),
                  "explained_n": len(explain), "link": link}).sort_values("mean_abs_shap", ascending=False).to_csv(
                      out / "clv_6m_shap_importance.csv", index=False)
    rfm = np.array([f"R{int(r <= r_cut) if pd.notna(r) else 'NA'}_F{int(f > f_cut)}_M{int(m > m_cut) if pd.notna(m) else 'NA'}"
                    for r, f, m in zip(q.R, q.F_event_months, q.M_group_points)])
    rows, grouped = [], []
    for method, pred in predictions.items():
        p = pred[indexer]
        fit = next((s for s in status if s["method"] == method), {"status": "fit"})
        rows.append(dict(method=method, horizon_months=horizon, origin=origin,
                         fit_status=fit["status"], **errors(target, p)))
        for kind, labels in [("event_history", group), ("history_short", young.astype(str)), ("rfm", rfm)]:
            for label in np.unique(labels):
                ix = labels == label
                grouped.append(dict(method=method, group_type=kind, group=str(label), **errors(target.to_numpy()[ix], p[ix])))
    pd.DataFrame(rows).to_csv(out / "clv_6m_benchmark.csv", index=False)
    pd.DataFrame(grouped).to_csv(out / "clv_6m_segment_errors.csv", index=False)
    pd.DataFrame(status).to_csv(out / "clv_probabilistic_fit_status.csv", index=False)
    audit = dict(origin=origin, label_end=shift(origin, horizon), horizon_months=horizon,
        train_origins=used, max_train_label_month=max(shift(m, horizon) for m in used),
        train_rows=len(y), current_complete_n=len(current), labeled_n=len(target),
        label_coverage=len(target) / len(current), scope="fixed-configuration development backtest; no 6m validation selection",
        monetary_proxy="acquisitions per repeat event-month, unit product weights = 1; not revenue or profit",
        explanation=dict(method="SHAP TreeExplainer", sample_n=len(explain), link=link, additive_reconstruction_verified=True),
        inputs=INPUTS, twelve_month_status="not enough calendar history for causal supervised train/validation/test")
    assert audit["max_train_label_month"] <= origin
    write_json(out / "clv_6m_audit.json", audit)
    return rows, audit
