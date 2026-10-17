import json, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from .common import PRODUCTS, DEMOS, CATS, require, fingerprint, write_json


def csv_source(path, basename, consume):
    p = Path(path)
    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as z:
            names = [n for n in z.namelist() if Path(n).name == basename]
            require(len(names) == 1, f"ZIP needs one {basename}")
            with z.open(names[0]) as f:
                consume(f)
    else:
        consume(p)


def ingest(c):
    data = c["data"]
    cache = Path(data["work_dir"]) / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    signature = dict(
        raw=fingerprint(data["train_csv_or_zip"]),
        history_start=data["history_start"],
        forecast_month=data["forecast_month"],
        version=1,
        products=PRODUCTS,
    )
    manifest = cache / "manifest.json"
    if manifest.exists() and not data["rebuild_cache"]:
        require(
            json.loads(manifest.read_text()) == signature,
            "Cache source/config changed: use a new work_dir or rebuild_cache=true",
        )
        months = pd.period_range(
            data["history_start"], data["forecast_month"], freq="M"
        ).astype(str)
        require(
            all((cache / f"{m}.parquet").exists() for m in months),
            "Incomplete cache; rebuild required",
        )
        return cache
    chunks = cache / "chunks"
    chunks.mkdir(exist_ok=True)
    old = list(chunks.glob("*.parquet"))
    for p in old:
        p.unlink()
    wanted = ["fecha_dato", "ncodpers", "fecha_alta"] + DEMOS + PRODUCTS

    def consume(src):
        for chunk_no, q in enumerate(
            pd.read_csv(
                src,
                usecols=wanted,
                dtype={x: "string" for x in wanted if x not in PRODUCTS},
                chunksize=data["chunk_size"],
                na_values=["NA", " NA", ""],
                keep_default_na=True,
            )
        ):
            date = pd.to_datetime(q.fecha_dato, errors="coerce")
            require(date.notna().all(), "Invalid fecha_dato")
            q["month"] = date.dt.strftime("%Y-%m")
            q = q.loc[
                q.month.between(data["history_start"], data["forecast_month"])
            ].copy()
            if q.empty:
                continue
            ids = pd.to_numeric(q.ncodpers, errors="raise")
            require(ids.notna().all() and ids.mod(1).eq(0).all(), "Invalid IDs")
            q["customer_id"] = ids.astype("int64")
            q = q.drop(columns=["ncodpers", "fecha_dato"])
            for f in ["age", "renta", "antiguedad"]:
                v = pd.to_numeric(q[f].str.strip(), errors="coerce").astype(float)
                v = v.where(np.isfinite(v) & v.ge(0))
                if f == "age":
                    v = v.where(v.le(110))
                q[f] = v
            for f in CATS:
                q[f] = q[f].str.strip().fillna("__MISSING__")
            q["fecha_alta"] = pd.to_datetime(q.fecha_alta, errors="coerce")
            for f in PRODUCTS:
                q[f] = pd.to_numeric(q[f], errors="raise").astype("float32")
                require((q[f].isin([0, 1]) | q[f].isna()).all(), f"Invalid product {f}")
            for m, z in q.groupby("month"):
                z.to_parquet(chunks / f"{m}_{chunk_no:06d}.parquet", index=False)

    csv_source(data["train_csv_or_zip"], "train_ver2.csv", consume)
    for m in pd.period_range(
        data["history_start"], data["forecast_month"], freq="M"
    ).astype(str):
        files = sorted(chunks.glob(f"{m}_*.parquet"))
        require(bool(files), f"Missing raw month {m}")
        q = pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)
        require(q.customer_id.is_unique, f"Duplicate customer-month: {m}")
        q.sort_values("customer_id").to_parquet(cache / f"{m}.parquet", index=False)
        for p in files:
            p.unlink()
    write_json(manifest, signature)
    return cache
