"""Select fixed customer IDs deterministically, retaining every observed month."""
import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from .common import require, write_json
from .ingest import csv_source


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def id_hash(ids, seed):
    """SplitMix64 permutation: stable across Python versions and CSV row order."""
    with np.errstate(over="ignore"):
        x = np.asarray(ids, dtype="uint64") ^ np.uint64(seed)
        x = x + np.uint64(0x9E3779B97F4A7C15)
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return x ^ (x >> np.uint64(31))


def sample(source, output, customers=10000, seed=42, chunk_size=400000):
    require(customers > 0 and seed >= 0 and chunk_size > 0, "invalid sample parameters")
    source, output = Path(source), Path(output)
    require(source.resolve() != output.resolve(), "sample must not overwrite its source")
    candidates = np.array([], dtype="int64")

    def choose(stream):
        nonlocal candidates
        for chunk in pd.read_csv(stream, usecols=["ncodpers"], chunksize=chunk_size):
            ids = chunk.ncodpers.to_numpy(dtype="int64")
            ids = np.unique(np.concatenate([candidates, ids]))
            order = np.lexsort((ids, id_hash(ids, seed)))
            candidates = ids[order[:customers]]
    csv_source(source, "train_ver2.csv", choose)
    selected = np.sort(candidates)
    output.parent.mkdir(parents=True, exist_ok=True)
    counts, seen = {}, set()
    first = True

    def retain(stream):
        nonlocal first
        for chunk in pd.read_csv(stream, dtype=str, chunksize=chunk_size):
            keep = chunk.ncodpers.astype("int64").isin(selected)
            q = chunk.loc[keep]
            if q.empty:
                continue
            q.to_csv(output, mode="w" if first else "a", header=first, index=False)
            first = False
            seen.update(q.ncodpers.astype("int64").tolist())
            for month, n in q.fecha_dato.str[:7].value_counts().items():
                counts[month] = counts.get(month, 0) + int(n)
    csv_source(source, "train_ver2.csv", retain)
    require(bool(seen), "source contains no selected customers")
    manifest = dict(algorithm="splitmix64-smallest-hash-fixed-id-v1", seed=seed,
                    requested_customers=customers, selected_customers=len(selected),
                    observed_customers=len(seen), rows=sum(counts.values()),
                    rows_by_month=dict(sorted(counts.items())),
                    source_sha256=sha256(source), sample_sha256=sha256(output),
                    selected_ids_sha256=hashlib.sha256(selected.astype("<i8").tobytes()).hexdigest(),
                    all_months_retained=True)
    write_json(output.with_suffix(".manifest.json"), manifest)
    print(manifest, flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--customers", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    sample(args.source, args.out, args.customers, args.seed)


if __name__ == "__main__":
    main()
