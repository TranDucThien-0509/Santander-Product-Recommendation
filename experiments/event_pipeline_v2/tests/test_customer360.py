"""Synthetic point-in-time, recommendation eligibility and local HTTP contracts."""
import copy
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from pipeline.common import PRODUCTS
from track_a.customer360 import CustomerStore, care_policy
from track_a.serve_customer360 import handler_for


class Transform:
    def transform(self, frame):
        return frame.to_numpy()


class Model:
    def predict(self, x):
        return np.zeros(len(x), dtype=int)


def fixture():
    frames, life, flags = {}, {}, []
    for month in ["2020-01", "2020-02", "2020-03"]:
        ids = [1, 2, 3, 4, 5] + ([6] if month == "2020-03" else [])
        rows = []
        for i in ids:
            observed = not (i == 1 and month == "2020-02")
            rows.append(dict(customer_id=i, is_observed=observed, missing_months=0 if observed else 1,
                             lifecycle="Active" if observed else "At-risk"))
            if not observed:
                continue
            row = dict(customer_id=i, product_complete=int(i != 5), R=0., F_event_months=1.,
                       M_group_points=.3, M_group_uses_baseline=0, rfm_no_event=0,
                       observed_pairs=4, n_products=1., predicted_acquisitions_1m=.2,
                       clv_unavailable=0, persona_id="P3")
            row.update({p: int(j == 0) for j, p in enumerate(PRODUCTS)})
            row.update({"affinity_"+p: .8-j*.01 for j, p in enumerate(PRODUCTS)})
            frames.setdefault(month, []).append(row)
            flags.append(dict(customer_id=i, month=month, indfall="S" if i == 4 else "N",
                              ind_actividad_cliente=None if i == 3 else "0" if i == 2 else "1"))
        life[month] = pd.DataFrame(rows).set_index("customer_id")
    frames = {m: pd.DataFrame(rows).set_index("customer_id") for m, rows in frames.items()}
    bundle = dict(transform=Transform(), model=Model(), fit_month="2020-02", columns=["n_products"])
    return frames, life, pd.DataFrame(flags), bundle, "synthetic", "synthetic, not customer data"


class Customer360Contracts(unittest.TestCase):
    def setUp(self):
        self.args = fixture()
        self.store = CustomerStore(*self.args)

    def test_future_month_mutations_do_not_change_as_of_profile(self):
        before = self.store.profile(1, "2020-01", 6)
        other = copy.deepcopy(self.args)
        other[0]["2020-03"].loc[1, ["predicted_acquisitions_1m", "n_products"]] = [99, 24]
        other[2].loc[other[2].month.eq("2020-03"), "indfall"] = "S"
        after = CustomerStore(*other).profile(1, "2020-01", 6)
        self.assertEqual(before, after)
        self.assertIsNone(before["current"]["cluster"])
        self.assertEqual(self.store.profile(1, "2020-03")["current"]["cluster"], "C1")

    def test_absence_is_null_and_breaks_product_events(self):
        profile = self.store.profile(1, "2020-03")
        gap = profile["timeline"][1]
        for key in ["R", "F", "M", "clv_1m", "n_products", "cluster", "acquired"]:
            self.assertIsNone(gap[key], key)
        self.assertIsNone(profile["current"]["acquired"])
        absent = self.store.profile(1, "2020-02")
        self.assertEqual(absent["recommendations"], [])
        self.assertEqual(absent["policy"]["action"], "verify")

    def test_owned_mask_and_status_gates(self):
        eligible = self.store.profile(1, "2020-03")
        self.assertTrue(eligible["recommendations"])
        self.assertNotIn(PRODUCTS[0], [r["product"] for r in eligible["recommendations"]])
        self.assertTrue(all(r["score"] > 0 for r in eligible["recommendations"]))
        for i in [2, 3, 4, 5]:
            p = self.store.profile(i, "2020-03")
            self.assertFalse(p["current"]["cross_sell_eligible"])
            self.assertEqual(p["recommendations"], [])
        self.assertEqual(self.store.profile(2,"2020-03")["current"]["lifecycle"], "At-risk")
        self.assertEqual(self.store.profile(4,"2020-03")["current"]["lifecycle"], "Churned")

    def test_constant_peer_forecasts_are_midrank_not_all_high_priority(self):
        p = self.store.profile(1, "2020-03")
        self.assertEqual(p["current"]["clv_peer_percentile"], 50)
        self.assertEqual(p["current"]["clv_peer_n"], 2)
        self.assertEqual(p["policy"]["action"], "maintain")
        self.assertIsNone(p["policy"]["roi"])

    def test_historical_search_cannot_reveal_future_customers(self):
        self.assertEqual(self.store.search("6", "2020-01"), [])
        with self.assertRaises(KeyError):
            self.store.profile(6, "2020-01")
        with self.assertRaises(ValueError):
            self.store.profile(1, "2020-04")

    def test_unavailable_negative_nan_clv_and_affinity_are_not_actionable(self):
        frames = self.args[0]
        frames["2020-03"].loc[1, "affinity_"+PRODUCTS[1]] = np.nan
        frames["2020-03"].loc[1, "affinity_"+PRODUCTS[2]] = -1
        valid = CustomerStore(*self.args).profile(1,"2020-03")
        self.assertFalse({PRODUCTS[1], PRODUCTS[2]} & {r["product"] for r in valid["recommendations"]})
        frames["2020-03"].loc[1, "clv_unavailable"] = 1
        p = CustomerStore(*self.args).profile(1,"2020-03")
        self.assertIsNone(p["current"]["clv_1m"])
        self.assertEqual(p["recommendations"], [])
        frames["2020-03"].loc[1, "clv_unavailable"] = 0
        for value in [-1, np.nan, np.inf]:
            frames["2020-03"].loc[1, "predicted_acquisitions_1m"] = value
            invalid = CustomerStore(*self.args).profile(1,"2020-03")
            self.assertIsNone(invalid["current"]["clv_1m"])
            self.assertEqual(invalid["recommendations"], [])

    def test_policy_threshold_and_minimum_history_are_explicit(self):
        s = self.store.profile(1,"2020-03")["current"]
        self.assertEqual(care_policy(dict(s, clv_peer_percentile=80))["action"], "test")
        self.assertEqual(care_policy(dict(s, clv_peer_percentile=79.9))["action"], "maintain")
        self.assertEqual(care_policy(dict(s, observed_pairs=2, clv_peer_percentile=99))["action"], "observe")

    def test_past_deceased_flag_blocks_even_after_absence_or_changed_flag(self):
        flags = self.args[2]
        flags.loc[flags.customer_id.eq(1) & flags.month.eq("2020-01"), "indfall"] = "S"
        store = CustomerStore(*self.args)
        for month in ["2020-02", "2020-03"]:
            p = store.profile(1, month)
            self.assertTrue(p["current"]["historical_deceased"])
            self.assertFalse(p["current"]["cross_sell_eligible"])
            self.assertEqual(p["policy"]["action"], "stop")
            self.assertEqual(p["recommendations"], [])

    def test_http_uses_strict_json_no_store_and_rejects_host_and_origin(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.store))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base+"/api/profile?id=1&month=2020-03") as response:
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertEqual(json.load(response)["customer_id"], 1)
            for path, headers, expected in [
                ("/api/meta", {"Host": "attacker.example"}, 403),
                ("/api/meta", {"Origin": "https://attacker.example"}, 403),
                ("/../customer360.py", {}, 404),
                ("/api/profile?id=999&month=2020-03", {}, 404),
                ("/api/profile?id=1&window=999", {}, 400),
                ("/api/profile?id=not-a-number", {}, 400),
            ]:
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(base+path, headers=headers))
                self.assertEqual(error.exception.code, expected)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
