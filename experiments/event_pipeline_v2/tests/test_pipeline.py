import copy, json, tempfile, unittest
from pathlib import Path
import numpy as np
import pandas as pd
from pipeline.common import PRODUCTS, features_for, load_config, write_json
from pipeline.features import pair, persona
from pipeline.ingest import ingest
from pipeline.run_pipeline import run
from pipeline.evaluate import metrics


def fixture(folder, backend="hist_gradient_boosting"):
    rng = np.random.default_rng(9)
    rows = []
    ownership = np.zeros((160, 24), dtype=int)
    for t, month in enumerate(
        pd.period_range("2020-01", "2020-09", freq="M").astype(str)
    ):
        ownership[:, 2] = 1
        for i in range(160):
            # Multiple labels and cancellations; propensity depends on customer ID.
            if rng.random() < 0.38:
                j = 3 + ((i + t) % 8)
                ownership[i, j] = 1
            if rng.random() < 0.06:
                ownership[i, 3 + ((i + t + 1) % 8)] = 1
            if rng.random() < 0.12:
                ownership[i, 3 + ((i + t + 3) % 8)] = 0
            if i == 0 and t in (2, 3):
                continue  # reappearance must not create gap events
            if i == 1 and t < 4:
                continue  # first observed portfolio is not acquisition
            d = dict(
                fecha_dato=month + "-28",
                ncodpers=i,
                fecha_alta="2019-01-01",
                age=15 if i == 2 else (164 if i == 3 else 20 + i % 50),
                renta=50000 + i * 100,
                antiguedad=12 + t,
                canal_entrada="KHE" if i % 2 else "KAT",
                segmento="02",
                sexo="H" if i % 2 else "V",
                nomprov="MADRID",
            )
            d.update(dict(zip(PRODUCTS, ownership[i].copy())))
            if i == 4 and t == 5:
                d[PRODUCTS[5]] = np.nan
            rows.append(d)
    raw = folder / "train_ver2.csv"
    pd.DataFrame(rows).to_csv(raw, index=False)
    c = json.loads((Path(__file__).parents[1] / "configs/default.json").read_text())
    c["data"].update(
        train_csv_or_zip=str(raw),
        work_dir=str(folder / "work"),
        history_start="2020-01",
        forecast_month="2020-09",
        chunk_size=90,
    )
    c["split"] = dict(
        train_origins=["2020-05", "2020-06"],
        validation_origins=["2020-07"],
        test_origins=["2020-08"],
    )
    c["meta_models"].update(
        clv_max_train_rows=500,
        clv_max_iter=3,
        clv_min_train_rows=10,
        clv_min_history_origin="2020-02",
        persona_rules_available_from="2020-01",
        persona_rules_fit_origin="2019-11",
        persona_rules_label_month="2019-12",
        affinity_prior=10.0,
    )
    c["model"].update(
        backend=backend,
        n_estimators=4,
        max_depth=2,
        max_train_event_rows=1000,
        n_jobs=1,
    )
    return c


class PipelineTests(unittest.TestCase):
    def test_metrics_denominators_and_mask(self):
        from pipeline.train import ranked_products

        y = np.zeros((2, 24), int)
        y[0, 2] = 1
        y[0, 3] = 1
        m = metrics(y, [[2, 4, 3], [0, 1]])
        self.assertAlmostEqual(
            m["map_at_7_all"], m["buyer_prevalence"] * m["map_at_7_buyers"]
        )
        self.assertAlmostEqual(m["map_at_7_buyers"], (1 + 2 / 3) / 2)
        s = np.ones((1, 24))
        own = np.zeros((1, 24))
        own[0, 0] = 1
        self.assertNotIn(0, ranked_products(s, own)[0])

    def test_invalid_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            c = fixture(folder)
            c["feature_groups"]["clv"] = "false"
            write_json(folder / "config.json", c)
            with self.assertRaises(ValueError):
                load_config(folder / "config.json")
            c["feature_groups"]["clv"] = False
            c["split"]["test_origins"] = ["2020-06"]
            write_json(folder / "config.json", c)
            with self.assertRaises(ValueError):
                load_config(folder / "config.json")

    def test_persona_unknown(self):
        q = pd.DataFrame(
            {
                "F_event_months": [0, 0, 2],
                "n_products": [2, 3, 5],
                "observed_pairs": [5, 0, 5],
                "product_complete": [1, 1, 1],
                "R": [np.nan, np.nan, 1.0],
            }
        )
        ids, missing = persona(q, True)
        self.assertEqual(ids.tolist(), ["P1", "UNKNOWN", "P6"])
        self.assertTrue(persona(q, False)[1].all())

    def test_full_pipeline_and_future_invariance(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            c = fixture(folder)
            write_json(folder / "config.json", c)
            load_config(folder / "config.json")
            out = run(c)
            report = json.loads((out / "comparison.json").read_text())[0]
            self.assertGreater(report["test"]["n_buyers"], 0)
            manifest = json.loads(
                (
                    out / c["run"]["name"] / "evaluation_model/feature_manifest.json"
                ).read_text()
            )
            self.assertIn("persona_id", manifest["categorical_columns"])
            self.assertIn("affinity_" + PRODUCTS[0], manifest["numeric_columns"])
            prediction = pd.read_csv(out / c["run"]["name"] / "submission.csv")
            self.assertEqual(len(prediction), 160)
            cache = Path(c["data"]["work_dir"]) / "cache"
            may = pd.read_parquet(cache / "2020-05.parquet").set_index("customer_id")
            self.assertEqual(may.loc[2, "age"], 15)
            self.assertTrue(pd.isna(may.loc[3, "age"]))
            ids, _, audit = pair(cache, "2020-04")
            self.assertNotIn(1, ids)
            self.assertNotIn(0, ids)
            self.assertEqual(audit["n_first_seen_next"], 2)
            # July's snapshots/features and meta predictions cannot depend on August or September raw values.
            old = pd.read_parquet(out / "features/2020-07.parquet")
            raw = pd.read_csv(c["data"]["train_csv_or_zip"], dtype={"segmento": str})
            raw.loc[raw.fecha_dato >= "2020-08-01", PRODUCTS[10]] = 1
            raw.to_csv(c["data"]["train_csv_or_zip"], index=False)
            c2 = copy.deepcopy(c)
            c2["data"]["work_dir"] = str(folder / "work_mutated")
            c2["run"].update(refit_for_forecast=False)
            out2 = run(c2)
            pd.testing.assert_frame_equal(
                old, pd.read_parquet(out2 / "features/2020-07.parquet")
            )
            # Disabled groups are absent from actual fitted columns, not merely set to zero.
            from pipeline.train import train

            c3 = copy.deepcopy(c)
            c3["feature_groups"] = {k: False for k in c["feature_groups"]}
            pkg = train(
                cache,
                out / "features",
                c["split"]["train_origins"],
                c3,
                folder / "baseline",
            )
            nums, cats = features_for(c3["feature_groups"])
            self.assertEqual(pkg["columns"], nums + cats)
            self.assertNotIn("persona_id", pkg["columns"])
            self.assertNotIn("R", pkg["columns"])
            # Chunked cache identity prevents stale raw data from being silently reused.
            with self.assertRaises(ValueError):
                ingest(c)

    def test_xgboost_and_ablation(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            c = fixture(folder, "xgboost")
            import zipfile

            archive = folder / "train_ver2.csv.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.write(c["data"]["train_csv_or_zip"], "nested/train_ver2.csv")
            c["data"]["train_csv_or_zip"] = str(archive)
            c["run"].update(ablation=True, refit_for_forecast=False)
            out = run(c)
            rows = json.loads((out / "comparison.json").read_text())
            self.assertEqual(
                [r["variant"] for r in rows],
                [
                    "baseline",
                    "baseline_plus_rfm",
                    "baseline_plus_clv",
                    "baseline_plus_persona",
                    "baseline_plus_lifecycle",
                    "baseline_plus_affinity",
                    "all_enabled",
                ],
            )
            self.assertEqual(len({r["test"]["n_all"] for r in rows}), 1)
            for r in rows:
                manifest = json.loads(
                    (
                        out / r["variant"] / "evaluation_model/feature_manifest.json"
                    ).read_text()
                )
                n, cat = features_for(r["feature_groups"])
                self.assertEqual(
                    manifest["numeric_columns"] + manifest["categorical_columns"],
                    n + cat,
                )
            # Reload and score the saved model with a roster including a cold-start ID.
            import pickle
            from pipeline.predict import forecast

            with (out / "all_enabled/evaluation_model/model.pkl").open("rb") as f:
                package = pickle.load(f)
            roster = folder / "test_ver2.csv"
            pd.DataFrame({"ncodpers": [0, 9999]}).to_csv(roster, index=False)
            c["data"]["prediction_roster_csv_or_zip"] = str(roster)
            dest = folder / "roster"
            dest.mkdir()
            audit = forecast(
                package,
                Path(c["data"]["work_dir"]) / "cache",
                out / "features",
                c,
                dest,
            )
            self.assertEqual(audit["n_fallback"], 1)
            status = pd.read_csv(dest / "predictions_with_status.csv")
            self.assertEqual(
                status.status.tolist(),
                ["current_complete_snapshot", "fallback_ownership_unverified"],
            )


if __name__ == "__main__":
    unittest.main()
