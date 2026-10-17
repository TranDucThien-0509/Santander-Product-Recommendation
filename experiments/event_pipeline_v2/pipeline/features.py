"""Every origin is built before its following month's target is read."""

from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from .common import PRODUCTS, BASE_NUM, shift, month_index, write_json, FEATURE_VERSIONS


def read_month(cache, month):
    return pd.read_parquet(Path(cache) / f"{month}.parquet").set_index(
        "customer_id", drop=False
    )


def pair(cache, origin):
    """Only consecutive, observed, complete product snapshots define labels."""
    a = read_month(cache, origin)
    b = read_month(cache, shift(origin, 1))
    n_origin, n_next = len(a), len(b)
    first_seen_next = int((~b.index.isin(a.index)).sum())
    ids = a.index.intersection(b.index)
    a = a.loc[ids]
    b = b.loc[ids]
    good = a[PRODUCTS].notna().all(axis=1) & b[PRODUCTS].notna().all(axis=1)
    a = a.loc[good]
    b = b.loc[good]
    y = ((a[PRODUCTS].to_numpy() == 0) & (b[PRODUCTS].to_numpy() == 1)).astype("uint8")
    return (
        a.index.to_numpy(),
        y,
        dict(
            origin=origin,
            n_origin=n_origin,
            n_next=n_next,
            n_eligible=len(a),
            n_first_seen_next=first_seen_next,
            n_absent_next=n_origin - len(ids),
            n_incomplete_pairs=int((~good).sum()),
        ),
    )


def portfolio_code(x):
    return (
        (x.astype("uint32") * (1 << np.arange(24, dtype="uint32")))
        .sum(axis=1)
        .astype("int64")
    )


def persona(q, available):
    f = q.F_event_months.to_numpy()
    n = q.n_products.to_numpy()
    ids = np.select(
        [
            (f == 0) & (n <= 2),
            (f == 0) & (n >= 3),
            f == 1,
            (f >= 2) & (n <= 1),
            (f >= 2) & (n >= 2) & (n <= 4),
            (f >= 2) & (n >= 5),
        ],
        ["P1", "P2", "P3", "P4", "P5", "P6"],
        default="UNKNOWN",
    )
    # Same common cohort as notebook 10: current complete snapshot, valid F/R,
    # finite exposure, and at least three observed consecutive complete pairs.
    valid = (
        q.product_complete.eq(1).to_numpy()
        & np.isfinite(f) & (f >= 0) & (f == np.floor(f))
        & np.isfinite(n) & (n >= 0) & (n <= 24) & (n == np.floor(n))
        & np.isfinite(q.observed_pairs.to_numpy())
        & (q.observed_pairs.to_numpy() >= 3)
        & ((f == 0) | (np.isfinite(q.R.to_numpy()) & q.R.ge(0).to_numpy()))
    )
    unknown = ~valid
    if not available:
        unknown[:] = True
    ids[unknown] = "UNKNOWN"
    return ids, unknown.astype("int8")


def portfolio_points(q, stats, total_n, total_events):
    """Notebook 01 export: 100 * historical rate, with global-rate fallback."""
    complete = q[PRODUCTS].notna().all(axis=1)
    q["M_group_points"] = np.nan
    q["M_group_history_n"] = 0
    q["M_group_uses_baseline"] = 0
    q["score_history_available"] = int(total_n > 0)
    q["historical_baseline"] = total_events / total_n if total_n else np.nan
    if complete.any() and total_n:
        codes = portfolio_code(q.loc[complete, PRODUCTS].to_numpy())
        support = np.array([stats.get(int(code), (0, 0))[0] for code in codes])
        rates = [stats[int(code)][1] / stats[int(code)][0] if n else total_events / total_n
                 for code, n in zip(codes, support)]
        q.loc[complete, "M_group_points"] = np.round(np.asarray(rates) * 100, 10)
        q.loc[complete, "M_group_history_n"] = support
        q.loc[complete, "M_group_uses_baseline"] = (support == 0).astype("int8")
    q["rfm_m_missing"] = q.M_group_points.isna().astype("int8")
    return q


def lifecycle_frame(ledger, current, month, gaps):
    """Presence-only notebook 05 states for all customers known by this month."""
    mi = month_index(month)
    frame = pd.DataFrame(index=ledger.index)
    frame["customer_id"] = frame.index
    frame["month"] = month
    frame["is_observed"] = frame.index.isin(current.index)
    frame["missing_months"] = (mi - ledger.last_seen).astype("int64")
    frame["first_seen_month_idx"] = ledger.first_seen
    frame["is_left_censored"] = ledger.is_left_censored.astype(bool)
    frame["bank_relationship_age_months"] = current.relationship_age_months
    frame["returned_to_panel"] = False
    frame["absence_before_return"] = np.nan
    returned = gaps.index[gaps.gt(0)]
    frame.loc[returned, "returned_to_panel"] = True
    frame.loc[returned, "absence_before_return"] = gaps.loc[returned]
    frame["lifecycle"] = np.select(
        [~frame.is_observed & frame.missing_months.ge(6), ~frame.is_observed,
         frame.returned_to_panel & frame.absence_before_return.ge(6),
         frame.bank_relationship_age_months.between(0, 2, inclusive="left")],
        ["Churned", "At-risk", "Win-back", "New"], default="Active",
    )
    frame["lifecycle_reason"] = frame.lifecycle.map({
        "New": "new_bank_relationship", "Active": "observed_presence",
        "At-risk": "short_panel_absence", "Churned": "panel_absence_proxy",
        "Win-back": "return_after_churn_proxy",
    })
    frame["rule_version"] = FEATURE_VERSIONS["lifecycle"]
    return frame


def affinity(cache, month, c, current):
    meta = c["meta_models"]
    start = c["data"]["history_start"]
    counts = np.zeros((24, 24))
    exposure = np.zeros((24, 24))
    pop_num = np.zeros(24)
    pop_den = np.zeros(24)
    sources = []
    for offset in range(1, meta["affinity_window_months"] + 1):
        origin = shift(month, -offset)
        if origin < start:
            continue
        ids, y, _ = pair(cache, origin)
        a = read_month(cache, origin).loc[ids, PRODUCTS].to_numpy(dtype="float64")
        counts += a.T @ y
        exposure += a.T @ (1 - a)
        pop_num += y.sum(axis=0)
        pop_den += (1 - a).sum(axis=0)
        sources.append(shift(origin, 1))
    pop = np.divide(pop_num, pop_den, out=np.zeros(24), where=pop_den > 0)
    strength = meta["affinity_prior"]
    conditional = (counts + strength * pop[None, :]) / (exposure + strength)
    np.fill_diagonal(conditional, 0)
    own = current[PRODUCTS].to_numpy(dtype="float64")
    score = (
        0.5 * (own @ conditional / np.maximum(own.sum(axis=1, keepdims=True), 1))
        + 0.5 * pop
    )
    score[own == 1] = 0
    return (
        score,
        pop,
        dict(
            max_label_month=max(sources) if sources else None,
            n_pairs_months=len(sources),
        ),
    )


def clv_fit_predict(cache, feature_dir, month, c, current):
    meta = c["meta_models"]
    origins = []
    first = max(c["data"]["history_start"], meta["clv_min_history_origin"])
    if first < month:
        origins = (
            pd.period_range(first, shift(month, -1), freq="M").astype(str).tolist()
        )
    xparts = []
    yparts = []
    used_origins = []
    seed = c["model"]["seed"]
    cap = meta["clv_max_train_rows"]
    # Reserve equal capacity per month; every model sees only outcomes already observed.
    each = max(1, cap // max(len(origins), 1))
    for origin in origins:
        ids, y, _ = pair(cache, origin)
        if not len(ids):
            continue
        q = pd.read_parquet(feature_dir / f"{origin}.parquet").set_index("customer_id")
        q = q.loc[ids, BASE_NUM]
        target = y.sum(axis=1)
        if len(q) > each:
            ix = np.random.default_rng(seed + month_index(origin)).choice(
                len(q), each, replace=False
            )
            q = q.iloc[ix]
            target = target[ix]
        xparts.append(q)
        yparts.append(target)
        used_origins.append(origin)
    audit = dict(
        max_label_month=max((shift(o, 1) for o in used_origins), default=None),
        train_rows=sum(map(len, yparts)),
        inputs=BASE_NUM,
        method="unavailable",
        version=FEATURE_VERSIONS["clv"],
        horizon_months=1,
        sampling_seed=seed,
        origin_candidates=origins,
        origins_used=used_origins,
    )
    if not yparts:
        return np.full(len(current), np.nan), np.ones(len(current), dtype="int8"), audit
    x = pd.concat(xparts)
    y = np.concatenate(yparts)
    if len(x) < meta["clv_min_train_rows"] or np.max(y) == 0:
        audit["method"] = "historical_mean_fallback"
        return (
            np.full(len(current), y.mean()),
            np.ones(len(current), dtype="int8"),
            audit,
        )
    model = HistGradientBoostingRegressor(
        loss="poisson",
        max_iter=meta["clv_max_iter"],
        max_leaf_nodes=15,
        min_samples_leaf=20,
        early_stopping=False,
        random_state=seed,
    )
    model.fit(x, y)
    audit["method"] = "poisson_gradient_boosting"
    return model.predict(current[BASE_NUM]), np.zeros(len(current), dtype="int8"), audit


def build_features(cache, c, out):
    feature_dir = Path(out) / "features"
    feature_dir.mkdir(parents=True, exist_ok=True)
    lifecycle_dir = Path(out) / "lifecycle"
    lifecycle_dir.mkdir(parents=True, exist_ok=True)
    flags = c["feature_groups"]
    ledger = pd.DataFrame()
    stats = {}
    total_n = total_events = 0
    audits = []
    last = None
    months = pd.period_range(
        c["data"]["history_start"], c["data"]["forecast_month"], freq="M"
    ).astype(str)
    for month in months:
        q = read_month(cache, month)
        mi = month_index(month)
        complete = q[PRODUCTS].notna().all(axis=1)
        if last is not None:
            ids, y, _ = pair(cache, shift(month, -1))
            previous = read_month(cache, shift(month, -1)).loc[ids, PRODUCTS].to_numpy()
            code = portfolio_code(previous)
            events = y.any(axis=1).astype("int64")
            agg = (
                pd.DataFrame({"code": code, "event": events})
                .groupby("code")
                .event.agg(["size", "sum"])
            )
            for key, row in agg.iterrows():
                n, s = stats.get(int(key), (0, 0))
                stats[int(key)] = (n + int(row["size"]), s + int(row["sum"]))
            total_n += len(events)
            total_events += int(events.sum())
        else:
            ids = np.array([], dtype="int64")
            y = np.zeros((0, 24), dtype="uint8")
        if ledger.empty:
            ledger = pd.DataFrame(index=q.index)
            ledger["F_event_months"] = 0
            ledger["observed_pairs"] = 0
            ledger["last_event"] = np.nan
            ledger["last_seen"] = mi
            ledger["first_seen"] = mi
            ledger["is_left_censored"] = True
        new = q.index.difference(ledger.index)
        if len(new):
            extra = pd.DataFrame(
                {
                    "F_event_months": 0,
                    "observed_pairs": 0,
                    "last_event": np.nan,
                    "last_seen": mi,
                    "first_seen": mi,
                    "is_left_censored": False,
                },
                index=new,
            )
            ledger = pd.concat([ledger, extra])
        gaps = (mi - ledger.loc[q.index, "last_seen"] - 1).clip(lower=0)
        if len(ids):
            event = y.any(axis=1)
            ledger.loc[ids, "observed_pairs"] += 1
            ledger.loc[ids[event], "F_event_months"] += 1
            ledger.loc[ids[event], "last_event"] = mi
        ledger.loc[q.index, "last_seen"] = mi
        q["F_event_months"] = ledger.loc[q.index, "F_event_months"]
        q["observed_pairs"] = ledger.loc[q.index, "observed_pairs"]
        q["R"] = mi - ledger.loc[q.index, "last_event"]
        q["rfm_no_event"] = q.R.isna().astype("int8")
        q["n_products"] = q[PRODUCTS].sum(axis=1, min_count=24)
        alta = q.fecha_alta
        q["relationship_age_months"] = (mi - (alta.dt.year * 12 + alta.dt.month)).where(
            alta.notna()
        )
        q["relationship_age_months"] = q.relationship_age_months.where(
            q.relationship_age_months >= 0
        )
        q["calendar_month"] = pd.Period(month).month
        lifecycle = lifecycle_frame(ledger, q, month, gaps)
        lifecycle.to_parquet(lifecycle_dir / f"{month}.parquet", index=False)
        q["missing_months"] = lifecycle.loc[q.index, "missing_months"]
        q["absence_before_return"] = gaps
        q["lifecycle"] = lifecycle.loc[q.index, "lifecycle"]
        q["product_complete"] = complete.astype("int8")
        q = portfolio_points(q, stats, total_n, total_events)
        q["persona_id"], q["persona_unavailable"] = persona(
            q, month >= c["meta_models"]["persona_rules_available_from"]
        )
        q.to_parquet(feature_dir / f"{month}.parquet", index=False)
        audit = dict(origin=month, history_through=month, feature_versions=FEATURE_VERSIONS,
                     m_history_customer_months=total_n,
                     m_max_label_month=month if total_n else None,
                     lifecycle_counts={str(k): int(v) for k, v in lifecycle.lifecycle.value_counts().items()},
                     persona_rules_available_from=c["meta_models"]["persona_rules_available_from"])
        if flags["clv"]:
            v, unavailable, info = clv_fit_predict(cache, feature_dir, month, c, q)
            q["predicted_acquisitions_1m"] = v
            q["clv_unavailable"] = unavailable
            audit["clv"] = info
        if flags["affinity"]:
            # Missing ownership snapshots are ineligible for recommendation.
            score, pop, info = affinity(cache, month, c, q.loc[complete])
            for j, p in enumerate(PRODUCTS):
                q["affinity_" + p] = np.nan
                q.loc[complete, "affinity_" + p] = score[:, j]
            audit["affinity"] = info
        q.to_parquet(feature_dir / f"{month}.parquet", index=False)
        audits.append(audit)
        last = month
        print(f"features {month}: {len(q):,} snapshots", flush=True)
    write_json(Path(out) / "point_in_time_audit.json", audits)
    return feature_dir
