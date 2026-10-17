from pathlib import Path
import hashlib, json, math, re
import pandas as pd

PRODUCTS = [
    "ind_ahor_fin_ult1",
    "ind_aval_fin_ult1",
    "ind_cco_fin_ult1",
    "ind_cder_fin_ult1",
    "ind_cno_fin_ult1",
    "ind_ctju_fin_ult1",
    "ind_ctma_fin_ult1",
    "ind_ctop_fin_ult1",
    "ind_ctpp_fin_ult1",
    "ind_deco_fin_ult1",
    "ind_deme_fin_ult1",
    "ind_dela_fin_ult1",
    "ind_ecue_fin_ult1",
    "ind_fond_fin_ult1",
    "ind_hip_fin_ult1",
    "ind_plan_fin_ult1",
    "ind_pres_fin_ult1",
    "ind_reca_fin_ult1",
    "ind_tjcr_fin_ult1",
    "ind_valo_fin_ult1",
    "ind_viv_fin_ult1",
    "ind_nomina_ult1",
    "ind_nom_pens_ult1",
    "ind_recibo_ult1",
]
DEMOS = ["age", "renta", "antiguedad", "canal_entrada", "segmento", "sexo", "nomprov"]
CATS = ["canal_entrada", "segmento", "sexo", "nomprov"]
BASE_NUM = [
    "age",
    "renta",
    "antiguedad",
    "relationship_age_months",
    "n_products",
    "observed_pairs",
    "calendar_month",
] + PRODUCTS
GROUPS = {
    "rfm": (
        ["R", "F_event_months", "M_group_points", "M_group_history_n",
         "M_group_uses_baseline", "rfm_no_event", "rfm_m_missing"],
        [],
    ),
    "clv": (["predicted_acquisitions_1m", "clv_unavailable"], []),
    "persona": (["persona_unavailable"], ["persona_id"]),
    "lifecycle": (["missing_months", "absence_before_return"], ["lifecycle"]),
    "affinity": (["affinity_" + p for p in PRODUCTS], []),
}

FEATURE_VERSIONS = {
    "rfm": "notebook01-group-points-baseline-v2",
    "persona": "notebook10-tree6-nov2015-fixed-rules-v1",
    "lifecycle": "lifecycle-v3-presence-gap6",
    "clv": "baseline-numeric-poisson-1m-v1",
    "affinity": "temporal-ownership-smoothed-24-v1",
}
GROUP_DEPENDENCIES = {
    "rfm": ["observed consecutive complete product pairs"],
    "persona": ["F_event_months", "n_products", "R eligibility", "observed_pairs"],
    "lifecycle": ["snapshot presence", "fecha_alta", "past panel gaps"],
    "clv": list(BASE_NUM),
    "affinity": ["past acquisition labels", "24 current ownership flags"],
}


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def shift(m, j):
    return str(pd.Period(m, "M") + j)


def month_index(m):
    p = pd.Period(m, "M")
    return p.year * 12 + p.month


def write_json(path, obj):
    Path(path).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )


def features_for(flags):
    require(
        set(flags) == set(GROUPS),
        "feature_groups must explicitly contain rfm/clv/persona/lifecycle/affinity",
    )
    require(
        all(type(v) is bool for v in flags.values()),
        "feature toggles must be JSON booleans",
    )
    nums = list(BASE_NUM)
    cats = list(CATS)
    for group, on in flags.items():
        if on:
            n, c = GROUPS[group]
            nums += n
            cats += c
    return nums, cats


def load_config(path):
    c = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_config(c)


def validate_config(c):
    require(isinstance(c, dict), "config must be an object")
    for section in ["data", "split", "feature_groups", "meta_models", "model", "run"]:
        require(isinstance(c.get(section), dict), f"missing config section: {section}")
    features_for(c["feature_groups"])
    for key in ["refit_for_forecast", "ablation"]:
        require(type(c["run"][key]) is bool, f"run.{key} must be a JSON boolean")
    require(
        type(c["data"]["rebuild_cache"]) is bool, "rebuild_cache must be a JSON boolean"
    )
    for section, keys in [
        ("data", ["chunk_size"]),
        ("model", ["max_train_event_rows", "n_estimators", "max_depth", "n_jobs"]),
        (
            "meta_models",
            [
                "clv_max_train_rows",
                "clv_max_iter",
                "clv_min_train_rows",
                "affinity_window_months",
            ],
        ),
    ]:
        for key in keys:
            require(
                type(c[section][key]) is int and c[section][key] > 0,
                f"{section}.{key} must be a positive integer",
            )
    for section, key in [("meta_models", "affinity_prior"), ("model", "learning_rate")]:
        v = c[section][key]
        require(type(v) in (int, float) and math.isfinite(v) and v > 0,
                f"{section}.{key} must be finite and positive")
    require(c["model"]["learning_rate"] <= 1, "learning_rate must be <= 1")
    require(type(c["model"]["seed"]) is int and c["model"]["seed"] >= 0,
            "seed must be a nonnegative integer")
    require(bool(re.fullmatch(r"[A-Za-z0-9_-]+", c["run"]["name"])),
            "run.name must be a simple directory name")
    sp = c["split"]
    groups = [sp[k] for k in ["train_origins", "validation_origins", "test_origins"]]
    require(all(isinstance(x, list) for x in groups), "origin groups must be lists")
    require(
        all(x == sorted(set(x)) and x for x in groups),
        "origins must be sorted, nonempty and unique",
    )
    require(
        max(groups[0]) < min(groups[1]) and max(groups[1]) < min(groups[2]),
        "use ordered disjoint temporal splits",
    )
    require(
        shift(max(groups[2]), 1) <= c["data"]["forecast_month"],
        "test labels must finish by forecast month",
    )
    for m in sum(groups, []) + [
        c["data"]["history_start"],
        c["data"]["forecast_month"],
        c["meta_models"]["clv_min_history_origin"],
        c["meta_models"]["persona_rules_available_from"],
        c["meta_models"]["persona_rules_fit_origin"],
        c["meta_models"]["persona_rules_label_month"],
    ]:
        require(isinstance(m, str) and bool(re.fullmatch(r"\d{4}-\d{2}", m)),
                "month must be YYYY-MM")
        require(str(pd.Period(m, "M")) == m, "month must be YYYY-MM")
    require(
        c["model"]["backend"] in ["xgboost", "hist_gradient_boosting"],
        "unsupported backend",
    )
    require(
        c["data"]["history_start"] < min(groups[0]), "history required before training"
    )
    if c["feature_groups"]["persona"]:
        meta = c["meta_models"]
        require(shift(meta["persona_rules_fit_origin"], 1) == meta["persona_rules_label_month"],
                "persona provenance must use next-month labels")
        require(meta["persona_rules_available_from"] >= meta["persona_rules_label_month"],
                "persona rules cannot be available before their fit labels")
        require(
            c["meta_models"]["persona_rules_available_from"] <= min(groups[0]),
            "persona rules unavailable at earliest training origin",
        )
    require(c["model"]["max_train_event_rows"] >= sum(map(len, groups)),
            "max_train_event_rows must cover every origin, including forecast refit")
    return c


def fingerprint(path):
    p = Path(path)
    s = p.stat()
    return dict(path=str(p.resolve()), size=s.st_size, mtime_ns=s.st_mtime_ns)


def config_hash(c):
    return hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()
