"""Small independent notebook-formula oracles and temporal/cohort contracts."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from pipeline.common import PRODUCTS, GROUPS, features_for, validate_config
from pipeline.features import (persona, portfolio_points, portfolio_code,
                               build_features, pair, affinity, clv_fit_predict)
from pipeline.train import event_training_data, ranked_products, train
from pipeline.evaluate import metrics
from test_pipeline import fixture


def cached_month(cache, month, customers):
    rows = []
    for customer, owned in customers.items():
        row = dict(customer_id=customer, month=month, fecha_alta=pd.Timestamp("2019-01-01"),
                   age=35., renta=50000., antiguedad=12., canal_entrada="KHE",
                   segmento="02", sexo="H", nomprov="MADRID")
        row.update({p: float(j in owned) for j, p in enumerate(PRODUCTS)})
        rows.append(row)
    pd.DataFrame(rows).to_parquet(cache / f"{month}.parquet", index=False)


class NotebookContracts(unittest.TestCase):
    def test_persona_full_450_point_domain(self):
        rows = [(f, n) for f in range(18) for n in range(25)]
        q = pd.DataFrame(rows, columns=["F_event_months", "n_products"])
        q["observed_pairs"] = 17
        q["product_complete"] = 1
        q["R"] = 0.
        actual, unavailable = persona(q, True)
        expected = []
        for f, n in rows:
            if f == 0:
                expected.append("P1" if n <= 2 else "P2")
            elif f == 1:
                expected.append("P3")
            else:
                expected.append("P4" if n <= 1 else ("P5" if n <= 4 else "P6"))
        self.assertEqual(actual.tolist(), expected)
        self.assertFalse(unavailable.any())

    def test_persona_eligibility_and_availability(self):
        q = pd.DataFrame(dict(F_event_months=[0., 1., 2., 2., 1., 1.5, -1., 1.],
                              n_products=[2., 3., 5., 2., 3., 3., 3., 25.],
                              observed_pairs=[3, 3, 3, 2, 3, 3, 3, 3],
                              product_complete=[1, 1, 0, 1, 1, 1, 1, 1],
                              R=[np.nan, np.nan, 0., 0., -1., 0., 0., 0.]))
        self.assertEqual(persona(q, True)[0].tolist(), ["P1"] + ["UNKNOWN"] * 7)
        self.assertTrue(persona(q, False)[1].all())

    def test_notebook_m_points_support_fallback_and_nan(self):
        q = pd.DataFrame(np.zeros((4, 24)), columns=PRODUCTS)
        q.loc[1, PRODUCTS[0]] = 1
        q.loc[2, PRODUCTS[1]] = 1
        q.loc[3, PRODUCTS[2]] = np.nan
        codes = portfolio_code(q.iloc[:3].to_numpy())
        stats = {int(codes[0]): (4, 1), int(codes[1]): (6, 3)}
        out = portfolio_points(q.copy(), stats, 10, 4)
        np.testing.assert_allclose(out.M_group_points, [25., 50., 40., np.nan], equal_nan=True)
        self.assertEqual(out.M_group_history_n.tolist(), [4, 6, 0, 0])
        self.assertEqual(out.M_group_uses_baseline.tolist(), [0, 0, 1, 0])
        self.assertEqual(out.rfm_m_missing.tolist(), [0, 0, 0, 1])
        self.assertTrue(portfolio_points(q.copy(), {}, 0, 0).M_group_points.isna().all())

    def test_lifecycle_all_known_and_return_precedence(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            c = fixture(folder)
            c["feature_groups"] = {k: False for k in GROUPS}
            cache = folder / "cache"
            cache.mkdir()
            months = pd.period_range("2020-01", "2020-09", freq="M").astype(str)
            for i, month in enumerate(months):
                customers = {2: [0]}
                if i in [0, 7, 8]:
                    customers[1] = [0, 1]
                if i == 8:
                    customers[3] = [0]
                cached_month(cache, month, customers)
                if i == 7:
                    q = pd.read_parquet(cache / f"{month}.parquet")
                    q.loc[q.customer_id.eq(1), "fecha_alta"] = pd.Timestamp("2020-08-01")
                    q.to_parquet(cache / f"{month}.parquet", index=False)
            out = folder / "out"
            build_features(cache, c, out)
            states = []
            for month in months:
                q = pd.read_parquet(out / "lifecycle" / f"{month}.parquet").set_index("customer_id")
                states.append(q.loc[1, "lifecycle"])
                if month < "2020-09":
                    self.assertNotIn(3, q.index)
            self.assertEqual(states, ["Active"] + ["At-risk"] * 5 + ["Churned", "Win-back", "Active"])
            aug = pd.read_parquet(out / "features/2020-08.parquet").set_index("customer_id")
            self.assertEqual(aug.loc[1, "missing_months"], 0)
            self.assertEqual(aug.loc[1, "absence_before_return"], 6)
            # Reappearance after the gap is not a verified acquisition pair.
            self.assertNotIn(1, pair(cache, "2020-07")[0])

    def test_multi_product_labels_and_nonbuyer_evaluation(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            c = fixture(folder)
            c["feature_groups"] = {k: False for k in GROUPS}
            cache = folder / "cache"
            cache.mkdir()
            for month in pd.period_range("2020-01", "2020-09", freq="M").astype(str):
                cached_month(cache, month, {1: [0, 2, 3] if month >= "2020-06" else [0], 2: [0]})
            features = build_features(cache, c, folder / "out")
            ids, labels, _ = pair(cache, "2020-05")
            x, y, audit = event_training_data(cache, features, ["2020-05"], c)
            self.assertEqual(y.tolist(), [2, 3])
            self.assertEqual(len(x), 2)
            self.assertEqual(audit[0]["n_event_customers"], 1)
            self.assertEqual(ids.tolist(), [1, 2])
            result = metrics(labels, [[2, 3], [2, 3]])
            self.assertEqual(result["map_at_7_all"], .5)
            self.assertEqual(result["map_at_7_buyers"], 1.)
            self.assertEqual(result["recommendation_coverage"], 1.)
            # CLV sees both zero-count and positive-count outcomes, at each origin.
            c["meta_models"]["clv_min_history_origin"] = "2020-05"
            c["meta_models"]["clv_min_train_rows"] = 1
            with patch("pipeline.features.HistGradientBoostingRegressor") as model:
                current = pd.read_parquet(features / "2020-06.parquet")
                model.return_value.predict.return_value = np.ones(len(current))
                _, _, info = clv_fit_predict(cache, features, "2020-06", c, current)
                self.assertEqual(sorted(model.return_value.fit.call_args.args[1].tolist()), [0, 2])
                self.assertLessEqual(info["max_label_month"], "2020-06")

    def test_affinity_formula_and_ownership_mask(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            c = fixture(folder)
            c["meta_models"].update(affinity_window_months=1, affinity_prior=2.)
            cached_month(folder, "2020-01", {1: [0], 2: [0]})
            cached_month(folder, "2020-02", {1: [0, 1], 2: [0]})
            current = pd.read_parquet(folder / "2020-02.parquet")
            scores, pop, info = affinity(folder, "2020-02", c, current)
            self.assertEqual(pop[1], .5)
            self.assertEqual(scores[0, 1], 0.)
            self.assertEqual(scores[1, 1], .5)
            self.assertEqual(info["max_label_month"], "2020-02")
            own = np.ones((2, 24))
            own[1, 2:4] = 0
            self.assertEqual(ranked_products(np.ones((2, 24)), own), [[], [2, 3]])

    def test_config_rejects_temporal_and_numeric_errors(self):
        with tempfile.TemporaryDirectory() as td:
            c = fixture(Path(td))
            for section, key, value in [
                ("model", "learning_rate", float("nan")), ("model", "n_jobs", True),
                ("data", "chunk_size", 0), ("run", "name", "../escape"),
                ("meta_models", "persona_rules_available_from", "2019-11"),
                ("meta_models", "persona_rules_available_from", "2020-06"),
                ("model", "max_train_event_rows", 1),
            ]:
                bad = copy.deepcopy(c)
                bad[section][key] = value
                with self.subTest(section=section, key=key, value=value):
                    with self.assertRaises(ValueError):
                        validate_config(bad)

    def test_customer_sample_is_order_invariant_and_keeps_all_months(self):
        from pipeline.sample import sample
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            raw = pd.DataFrame([dict(ncodpers=i, fecha_dato=f"2020-{m:02d}-28", value=i+m)
                                for i in range(20) for m in range(1, 5)])
            p = folder / "train_ver2.csv"
            raw.to_csv(p, index=False)
            first = sample(p, folder / "a.csv", customers=5, seed=42, chunk_size=7)
            raw.sample(frac=1, random_state=19).to_csv(p, index=False)
            second = sample(p, folder / "b.csv", customers=5, seed=42, chunk_size=11)
            self.assertEqual(first["selected_ids_sha256"], second["selected_ids_sha256"])
            a = pd.read_csv(folder / "a.csv")
            b = pd.read_csv(folder / "b.csv")
            pd.testing.assert_frame_equal(a.sort_values(["ncodpers", "fecha_dato"]).reset_index(drop=True),
                                          b.sort_values(["ncodpers", "fecha_dato"]).reset_index(drop=True))
            self.assertTrue(a.groupby("ncodpers").size().eq(4).all())


if __name__ == "__main__":
    unittest.main()
