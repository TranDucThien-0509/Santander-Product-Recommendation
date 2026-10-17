from pathlib import Path
import hashlib, json
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
        ["R", "F_event_months", "M_group_points", "rfm_no_event", "rfm_m_missing"],
        [],
    ),
    "clv": (["clv_expected_acquisitions_1m", "clv_unavailable"], []),
    "persona": (["persona_unavailable"], ["persona_id"]),
    "lifecycle": (["missing_months"], ["lifecycle"]),
    "affinity": (["affinity_" + p for p in PRODUCTS], []),
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
    c = json.loads(Path(path).read_text())
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
    require(c["meta_models"]["affinity_prior"] > 0, "affinity_prior must be positive")
    sp = c["split"]
    groups = [sp[k] for k in ["train_origins", "validation_origins", "test_origins"]]
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
    ]:
        require(str(pd.Period(m, "M")) == m, "month must be YYYY-MM")
    require(
        c["model"]["backend"] in ["xgboost", "hist_gradient_boosting"],
        "unsupported backend",
    )
    require(
        c["data"]["history_start"] < min(groups[0]), "history required before training"
    )
    if c["feature_groups"]["persona"]:
        require(
            c["meta_models"]["persona_rules_available_from"] <= min(groups[0]),
            "persona rules unavailable at earliest training origin",
        )
    return c


def fingerprint(path):
    p = Path(path)
    s = p.stat()
    return dict(path=str(p.resolve()), size=s.st_size, mtime_ns=s.st_mtime_ns)


def config_hash(c):
    return hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()
