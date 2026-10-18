"""Frozen RFM tiering and multiblock persona clustering, with membership stability."""
import numpy as np
import pandas as pd
import pickle
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler
from pipeline.common import PRODUCTS, write_json


def safe_silhouette(x, labels):
    if len(np.unique(labels)) < 2 or len(np.unique(labels)) >= len(labels):
        return None
    return float(silhouette_score(x, labels, sample_size=min(1500, len(x)), random_state=42))


def rfm_benchmark(panel, out, fit_month):
    columns = ["R", "F_event_months", "n_products", "rfm_no_event"]
    fit = panel.features(fit_month)
    transform = make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler())
    x = transform.fit_transform(fit[columns])
    km = KMeans(n_clusters=6, n_init=10, random_state=42).fit(x)
    model_dir = out / "model_artifacts"
    model_dir.mkdir(exist_ok=True)
    with (model_dir / "rfm_kmeans.pkl").open("wb") as handle:
        pickle.dump(dict(transform=transform, model=km, columns=columns, fit_month=fit_month), handle)
    edges = {c: np.unique(fit[c].dropna().quantile([1/3, 2/3]).to_numpy()) for c in columns[:3]}

    def labels(frame, method):
        if method == "kmeans_6":
            return km.predict(transform.transform(frame[columns])).astype(str)
        if method == "quantile_333":
            bins = [np.where(frame[c].isna(), -1, np.searchsorted(edges[c], frame[c], side="right")) for c in columns[:3]]
        else:
            bins = [np.where(frame.R.isna(), -1, np.select([frame.R.le(1), frame.R.le(3)], [0, 1], default=2)),
                    np.select([frame.F_event_months.eq(0), frame.F_event_months.eq(1)], [0, 1], default=2),
                    np.select([frame.n_products.le(2), frame.n_products.le(4)], [0, 1], default=2)]
        return np.array(["_".join(map(str, b)) for b in zip(*bins)])

    profiles, transitions = [], []
    previous = {}
    for month in [m for m in panel.months if m >= fit_month]:
        current = panel.features(month)
        for method in ["quantile_333", "kmeans_6", "rule_based"]:
            assigned = pd.Series(labels(current, method), index=current.index)
            profiles.append(dict(month=month, method=method, n=len(current), groups=assigned.nunique(),
                silhouette=safe_silhouette(transform.transform(current[columns]), assigned)))
            if method in previous:
                old_month, old = previous[method]
                common = old.index.intersection(assigned.index)
                transitions.append(dict(method=method, source_month=old_month, target_month=month,
                    common_n=len(common), common_coverage=len(common)/len(old),
                    same_label_rate=float((old.loc[common] == assigned.loc[common]).mean()),
                    adjusted_rand=float(adjusted_rand_score(old.loc[common], assigned.loc[common]))))
            previous[method] = (month, assigned)
    pd.DataFrame(profiles).to_csv(out / "rfm_geometry.csv", index=False)
    pd.DataFrame(transitions).to_csv(out / "rfm_membership_stability.csv", index=False)
    write_json(out / "rfm_tiering_spec.json", dict(fit_month=fit_month, inputs=columns,
        monetary_proxy="current n_products, separate from the ranker's historical portfolio propensity points",
        quantile_edges={k: v.tolist() for k, v in edges.items()},
        ties="duplicate quantile edges collapse; actual group count is reported",
        rule_r=[1, 3], rule_f=[0, 1], rule_products=[2, 4], missing_R="separate no-event bucket",
        comparison="geometry and membership stability here; predictive AP/Lift/Brier in archived notebook 03 evidence"))
    latest = panel.features(panel.months[-1])
    return pd.DataFrame({f"rfm_{method}": labels(latest, method)
                         for method in ["quantile_333", "kmeans_6", "rule_based"]}, index=latest.index)


def persona_cluster(panel, out, fit_month="2015-11"):
    numeric = ["R", "rfm_no_event", "F_event_months", "n_products", "M_group_points",
               "predicted_acquisitions_1m", "age", "renta", "antiguedad"]
    affinity = ["affinity_" + p for p in PRODUCTS]
    cats = ["canal_entrada", "segmento"]
    fit = panel.features(fit_month)
    needed = numeric + PRODUCTS + affinity + cats
    absent = [c for c in needed if c not in fit]
    if absent:
        raise ValueError(f"Persona clustering needs source run with CLV and affinity enabled; missing: {absent}")
    if len(fit) < 100:
        raise ValueError("Persona fit needs at least 100 complete customers")
    for col in ["predicted_acquisitions_1m"]:
        if fit[col].notna().sum() < 20:
            raise ValueError("Insufficient point-in-time CLV features for persona fit")
    num_pipe = make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True),
                             FunctionTransformer(np.log1p), StandardScaler())
    encoder = ColumnTransformer([
        ("behavior_demographics", num_pipe, numeric),
        ("portfolio", make_pipeline(SimpleImputer(strategy="median")), PRODUCTS),
        ("affinity", make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler()), affinity),
        ("categories", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cats),
    ], transformer_weights={"portfolio": 1 / np.sqrt(24), "affinity": 1 / np.sqrt(24)})
    x = encoder.fit_transform(fit[needed])
    candidates, models = [], {}
    for k in range(5, 9):
        model = KMeans(n_clusters=k, random_state=42, n_init=10).fit(x)
        score = safe_silhouette(x, model.labels_)
        share = float(np.bincount(model.labels_, minlength=k).min() / len(x))
        candidates.append(dict(k=k, silhouette=score, min_cluster_share=share, inertia=float(model.inertia_)))
        models[k] = model
    # Screen tiny clusters before comparing fit-only geometry. No label/test selection.
    eligible = [c for c in candidates if c["silhouette"] is not None and c["min_cluster_share"] >= .01]
    if not eligible:
        raise ValueError("No 5–8-cluster candidate passes the 1% fit-size screen")
    winner = max(eligible, key=lambda row: row["silhouette"])
    model = models[winner["k"]]
    model_dir = out / "model_artifacts"
    model_dir.mkdir(exist_ok=True)
    with (model_dir / "persona_clustering.pkl").open("wb") as handle:
        pickle.dump(dict(transform=encoder, model=model, columns=needed, fit_month=fit_month), handle)
    pd.DataFrame(candidates).to_csv(out / "persona_k_selection.csv", index=False)
    bootstrap = []
    for seed in [43, 44, 45]:
        ix = np.random.default_rng(seed).choice(len(x), len(x), replace=True)
        other = KMeans(n_clusters=winner["k"], random_state=seed, n_init=10).fit(x[ix])
        bootstrap.append(dict(seed=seed, adjusted_rand=float(adjusted_rand_score(model.labels_, other.predict(x)))))
    pd.DataFrame(bootstrap).to_csv(out / "persona_bootstrap_stability.csv", index=False)
    previous = None
    temporal = []
    final = None
    for month in [m for m in panel.months if m >= fit_month]:
        current = panel.features(month)
        labels = pd.Series(model.predict(encoder.transform(current[needed])), index=current.index)
        if previous is not None:
            old_month, old = previous
            common = old.index.intersection(labels.index)
            temporal.append(dict(source_month=old_month, target_month=month, common_n=len(common),
                common_coverage=len(common)/len(old), same_label_rate=float((old.loc[common] == labels.loc[common]).mean()),
                adjusted_rand=float(adjusted_rand_score(old.loc[common], labels.loc[common]))))
        previous = (month, labels)
        final = current.assign(cluster_id=labels, as_of_month=month)
    pd.DataFrame(temporal).to_csv(out / "persona_temporal_stability.csv", index=False)
    profiles, cards = [], ["# Persona clustering — hồ sơ định lượng\n",
        f"KMeans k={winner['k']}, fit tại {fit_month}; mô tả tại {panel.months[-1]}. CLV là số acquisition dự báo một tháng, không phải tiền.\n",
        "Các cluster C1…Ck là phương án nghiên cứu bổ sung; không thay nhãn P1–P6 theo rule đang dùng trong ranker.\n"]
    for label, group in final.groupby("cluster_id"):
        products = group[PRODUCTS].mean().sort_values(ascending=False)
        channel = group.canal_entrada.value_counts(normalize=True)
        row = dict(persona=f"C{label+1}", n=len(group), share=len(group)/len(final),
            median_age=float(group.age.median()), income_coverage=float(group.renta.notna().mean()),
            median_income=float(group.renta.median()), median_tenure=float(group.antiguedad.median()),
            median_F=float(group.F_event_months.median()), median_n_products=float(group.n_products.median()),
            mean_clv_1m=float(group.predicted_acquisitions_1m.mean()),
            top_product=products.index[0], top_product_ownership=float(products.iloc[0]),
            top_channel=str(channel.index[0]), top_channel_share=float(channel.iloc[0]))
        profiles.append(row)
        activity = "Chưa ghi nhận acquisition ở khách điển hình" if row["median_F"] == 0 else "Có lịch sử mở thêm sản phẩm"
        width = "danh mục hẹp" if row["median_n_products"] <= 2 else "danh mục đa sản phẩm"
        cards += [f"\n## C{label+1} — {activity}, {width}\n",
            f"- Quy mô: {len(group):,} ({row['share']:.1%}); tuổi median {row['median_age']:.1f}; tenure median {row['median_tenure']:.1f} tháng.",
            f"- F median {row['median_F']:.1f}; số sản phẩm median {row['median_n_products']:.1f}; CLV-proxy mean {row['mean_clv_1m']:.4f} acquisition/khách/tháng.",
            f"- Renta median {row['median_income']:.1f}, coverage {row['income_coverage']:.1%}; không diễn giải là lợi nhuận.",
            f"- Sản phẩm phổ biến nhất: {row['top_product']} ({row['top_product_ownership']:.1%}); canal {row['top_channel']} ({row['top_channel_share']:.1%}).",
            "- Gợi ý business cần kiểm thử: dùng affinity để chọn sản phẩm chưa sở hữu, CLV để ưu tiên và lifecycle/activity để lọc eligibility; chưa đo uplift chiến dịch.\n"]
    pd.DataFrame(profiles).to_csv(out / "persona_cluster_profiles.csv", index=False)
    (out / "persona_cluster_cards.md").write_text("\n".join(cards), encoding="utf-8")
    write_json(out / "persona_cluster_spec.json", dict(fit_month=fit_month, selected_k=winner["k"], seed=42,
        input_columns=needed, selection="fit-only silhouette among k=5..8, minimum cluster share 1%",
        preprocessing="numeric median + log1p + standardization; one-hot categories; fixed portfolio/affinity block weights",
        missing_R="median imputation for geometry with explicit rfm_no_event; original feature remains missing",
        stability="bootstrap ARI and temporal common-customer ARI/stay rate; no causal claim"))
    return final, winner
