"""Chunked raw EDA, including fields intentionally absent from ranker inputs."""
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
from pipeline.common import PRODUCTS, write_json
from pipeline.ingest import csv_source

AUDIT_COLS = ["age", "renta", "cod_prov", "indrel_1mes", "canal_entrada", "segmento",
              "pais_residencia", "ind_actividad_cliente", "indfall", "antiguedad"]
CATEGORICAL = ["canal_entrada", "segmento", "pais_residencia", "indrel_1mes"]


def raw_eda(raw, panel, out):
    missing, cardinality = Counter(), defaultdict(set)
    monthly, portfolios = Counter(), Counter()
    segment_rows, last_flags = [], []
    row_count = 0
    customer_ids = set()
    available = []

    def consume(source):
        nonlocal row_count, available
        reader = pd.read_csv(source, dtype="string", chunksize=100000,
            usecols=lambda col: col in AUDIT_COLS + PRODUCTS + ["fecha_dato", "ncodpers"],
            na_values=["NA", " NA", ""], keep_default_na=True)
        for frame in reader:
            available = list(frame.columns)
            frame = frame.apply(lambda col: col.str.strip().replace("", pd.NA))
            month = pd.to_datetime(frame.fecha_dato, errors="raise").dt.strftime("%Y-%m")
            frame = frame.loc[month.isin(panel.months)].copy()
            frame["month"] = month.loc[frame.index]
            row_count += len(frame)
            customer_ids.update(pd.to_numeric(frame.ncodpers, errors="raise").astype("int64").unique().tolist())
            missing.update(frame.isna().sum().to_dict())
            monthly.update(frame.month.value_counts().to_dict())
            for col in CATEGORICAL:
                if col in frame:
                    cardinality[col].update(frame[col].dropna().unique().tolist())
            product = frame[PRODUCTS].apply(pd.to_numeric, errors="raise")
            frame["n_products"] = product.sum(axis=1, min_count=len(PRODUCTS))
            portfolios.update(frame.n_products.dropna().astype(int).value_counts().to_dict())
            for dimension in ["segmento", "canal_entrada", "antiguedad"]:
                if dimension not in frame:
                    continue
                if dimension == "antiguedad":
                    tenure = pd.to_numeric(frame[dimension], errors="coerce")
                    conditions = [v.fillna(False).to_numpy(dtype=bool) for v in
                                  [tenure.between(0, 12), tenure.between(13, 60), tenure.gt(60)]]
                    key = pd.Series(np.select(conditions,
                        ["0-12m", "13-60m", "61m+"], default="__MISSING_INVALID__"), index=frame.index)
                else:
                    key = frame[dimension].fillna("__MISSING__")
                grouped = frame.assign(segment=key).groupby(["month", "segment"]).n_products.agg(["count", "sum"]).reset_index()
                grouped["dimension"] = dimension
                segment_rows.append(grouped)
            wanted = [c for c in ["ncodpers", "month", "ind_actividad_cliente", "indfall"] if c in frame]
            last_flags.append(frame.loc[frame.month.eq(panel.months[-1]), wanted])

    csv_source(raw, "train_ver2.csv", consume)
    if row_count == 0:
        raise ValueError("No raw rows in source run's history")
    coverage = pd.DataFrame([dict(column=col, present=col in available,
        missing_n=missing[col] if col in available else None,
        missing_share=missing[col] / row_count if col in available else None,
        cardinality=len(cardinality[col]) if col in CATEGORICAL and col in available else None)
        for col in AUDIT_COLS])
    coverage.to_csv(out / "raw_column_audit.csv", index=False)
    pd.DataFrame(sorted(monthly.items()), columns=["month", "snapshots"]).to_csv(out / "monthly_snapshots.csv", index=False)
    pd.DataFrame(sorted(portfolios.items()), columns=["n_products", "snapshots"]).to_csv(out / "portfolio_distribution.csv", index=False)
    if segment_rows:
        trend = pd.concat(segment_rows).groupby(["month", "dimension", "segment"], dropna=False)[["count", "sum"]].sum().reset_index()
        trend["mean_products"] = trend["sum"] / trend["count"]
        trend.to_csv(out / "segment_product_trend.csv", index=False)
    presence, segment_presence = [], []
    for origin, following in zip(panel.months, panel.months[1:]):
        a, b = panel.features(origin), panel.features(following)
        # Denominator is explicitly current COMPLETE snapshot cohort.
        n_missing = int((~a.index.isin(b.index)).sum())
        presence.append(dict(origin=origin, n_complete_current=len(a), absent_or_incomplete_next=n_missing,
            absence_or_incomplete_rate=n_missing / len(a) if len(a) else 0))
        detail = a[["segmento", "canal_entrada"]].copy()
        detail["absent_or_incomplete"] = ~a.index.isin(b.index)
        for dimension in ["segmento", "canal_entrada"]:
            for group, values in detail.groupby(dimension):
                segment_presence.append(dict(origin=origin, dimension=dimension, segment=str(group), n=len(values),
                    absent_or_incomplete_n=int(values.absent_or_incomplete.sum()),
                    rate=float(values.absent_or_incomplete.mean())))
    pd.DataFrame(presence).to_csv(out / "panel_presence.csv", index=False)
    pd.DataFrame(segment_presence).to_csv(out / "panel_presence_by_segment.csv", index=False)
    flags = pd.concat(last_flags, ignore_index=True).rename(columns={"ncodpers": "customer_id"})
    flags["customer_id"] = pd.to_numeric(flags.customer_id).astype("int64")
    if not flags.customer_id.is_unique:
        raise ValueError("Duplicate raw customer-month in lifecycle sidecar")
    summary = dict(rows=row_count, months=len(monthly), customers=len(customer_ids),
        first_month=panel.months[0], last_month=panel.months[-1], cardinality={k: len(v) for k, v in cardinality.items()},
        missing_share={c: missing[c] / row_count for c in AUDIT_COLS if c in available},
        absent_optional_columns=[c for c in AUDIT_COLS if c not in available],
        mean_owned_products=sum(k * n for k, n in portfolios.items()) / max(sum(portfolios.values()), 1),
        mean_absence_or_incomplete_rate=float(np.mean([p["absence_or_incomplete_rate"] for p in presence])))
    write_json(out / "eda_summary.json", summary)
    return summary, flags.set_index("customer_id")


def lifecycle_export(panel, flags, path):
    frame = pd.read_parquet(panel.root / "lifecycle" / f"{panel.months[-1]}.parquet").set_index("customer_id")
    frame["presence_lifecycle"] = frame.lifecycle
    frame = frame.join(flags.drop(columns="month", errors="ignore"), how="left")
    if "indfall" not in frame:
        frame["indfall"] = pd.NA
    if "ind_actividad_cliente" not in frame:
        frame["ind_actividad_cliente"] = pd.NA
    dead = frame.indfall.eq("S").fillna(False)
    inactive = frame.ind_actividad_cliente.eq("0").fillna(False)
    frame["activity_status_known"] = frame.ind_actividad_cliente.isin(["0", "1"])
    frame["deceased_status_known"] = frame.indfall.isin(["S", "N"])
    frame["lifecycle"] = frame.presence_lifecycle
    frame.loc[frame.is_observed & inactive & ~frame.lifecycle.isin(["New", "Win-back"]), "lifecycle"] = "At-risk"
    frame.loc[dead, "lifecycle"] = "Churned"
    frame["cross_sell_eligible"] = frame.is_observed & ~dead & frame.activity_status_known & ~inactive & frame.deceased_status_known
    frame["feature_version"] = "track-a-lifecycle-activity-v1"
    frame["as_of_month"] = panel.months[-1]
    frame.reset_index().to_parquet(path, index=False)
    return {str(k): int(v) for k, v in frame.lifecycle.value_counts().items()}, frame
