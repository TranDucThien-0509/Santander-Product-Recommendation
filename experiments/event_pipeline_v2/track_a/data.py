"""Auditable acquisition history and fully observed long-horizon targets."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from pipeline.common import PRODUCTS, month_index, shift, fingerprint
from pipeline.features import pair, read_month


class Panel:
    def __init__(self, run_dir, cache_dir):
        self.root, self.cache = Path(run_dir), Path(cache_dir)
        self.months = sorted(p.stem for p in (self.root / "features").glob("????-??.parquet"))
        if not self.months or self.months != pd.period_range(self.months[0], self.months[-1], freq="M").astype(str).tolist():
            raise ValueError("Feature history must contain consecutive monthly partitions")
        config = json.loads((self.root / "config.resolved.json").read_text(encoding="utf-8-sig"))
        self.config = config
        # The schema and raw fingerprint must belong to the same run/cache.
        manifest = json.loads((self.root / "input_manifest.json").read_text())
        if manifest != json.loads((self.cache / "manifest.json").read_text()):
            raise ValueError("Source run and cache manifests differ")
        if fingerprint(config["data"]["train_csv_or_zip"]) != manifest["raw"]:
            raise ValueError("Raw source changed after the completed run")
        audit = json.loads((self.root / "point_in_time_audit.json").read_text())
        for entry in audit:
            for cutoff in [entry.get("m_max_label_month"), entry.get("clv", {}).get("max_label_month")]:
                if cutoff is not None and cutoff > entry["origin"]:
                    raise ValueError("Source features contain labels beyond their scoring origin")
        completion = json.loads((self.root / "completed.json").read_text())
        if completion.get("status") != "success":
            raise ValueError("Track A requires a successfully completed source pipeline")
        self.events = {}
        self.history = {}
        ledger = pd.DataFrame()
        for month in self.months:
            q = read_month(self.cache, month)
            new = q.index.difference(ledger.index)
            if len(new):
                extra = pd.DataFrame(0.0, index=new, columns=["event_n", "product_n", "repeat_products"])
                extra["first_event"] = np.nan
                extra["last_event"] = np.nan
                ledger = pd.concat([ledger, extra])
            ev = pd.DataFrame(columns=["event_months", "acquisitions"], dtype=float)
            if shift(month, -1) in self.months:
                ids, y, _ = pair(self.cache, shift(month, -1))
                ev = pd.DataFrame({"event_months": y.any(axis=1).astype(int), "acquisitions": y.sum(axis=1)}, index=ids)
                positive = ev.index[ev.event_months.gt(0)]
                repeat = positive[ledger.loc[positive, "event_n"].gt(0).to_numpy()]
                ledger.loc[repeat, "repeat_products"] += ev.loc[repeat, "acquisitions"]
                first = positive[ledger.loc[positive, "first_event"].isna().to_numpy()]
                ledger.loc[first, "first_event"] = month_index(month)
                ledger.loc[positive, "last_event"] = month_index(month)
                ledger.loc[ev.index, "event_n"] += ev.event_months
                ledger.loc[ev.index, "product_n"] += ev.acquisitions
            self.events[month] = ev
            d = ledger.loc[q.index].copy()
            d["bg_frequency"] = (d.event_n - 1).clip(lower=0)
            d["bg_recency"] = d.last_event - d.first_event
            d["bg_T"] = month_index(month) - d.first_event
            d["repeat_value"] = d.repeat_products / d.bg_frequency.replace(0, np.nan)
            self.history[month] = d

    def features(self, month):
        q = pd.read_parquet(self.root / "features" / f"{month}.parquet").set_index("customer_id")
        return q.loc[q.product_complete.eq(1)].copy()

    def target(self, origin, horizon):
        """Absence/incomplete pairs are censored, never silently assigned zero."""
        if type(horizon) is not int or horizon < 1:
            raise ValueError("Horizon must be a positive integer")
        future = [shift(origin, j) for j in range(1, horizon + 1)]
        if any(m not in self.events for m in future):
            raise ValueError("Future target extends beyond observed data")
        ids = self.features(origin).index
        for month in future:
            ids = ids.intersection(self.events[month].index)
        count = sum((self.events[m].loc[ids, "acquisitions"] for m in future), pd.Series(0., index=ids))
        return count.rename("acquisitions")

    def training_origins(self, cutoff, horizon):
        return [m for m in self.months if m >= shift(self.months[0], 2) and shift(m, horizon) <= cutoff]


def export_events(panel, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    rows = 0
    files = []
    for month in panel.months[:-1]:
        ids, y, _ = pair(panel.cache, month)
        i, j = np.nonzero(y)
        events = pd.DataFrame({"customer_id": ids[i], "source_month": month,
            "event_month": shift(month, 1), "product": np.asarray(PRODUCTS)[j],
            "available_month": shift(month, 1)})
        path = destination / f"{shift(month, 1)}.parquet"
        events.to_parquet(path, index=False)
        rows += len(events)
        files.append(path)
    return dict(acquisition_rows=rows, partitions=len(files)), files
