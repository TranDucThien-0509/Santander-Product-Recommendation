import copy
import json
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import numpy as np
import pandas as pd
from test_pipeline import fixture
from pipeline.run_pipeline import run
from track_a.data import Panel, export_events
from track_a.eda import lifecycle_export, raw_eda
from track_a.affinity import matrices
from track_a.storage import upload, write_manifest
from track_a.clv import benchmark, errors


class TrackAContracts(unittest.TestCase):
    def test_constant_forecasts_have_fair_expected_top_decile_capture(self):
        result = errors([0] * 9 + [10], [1] * 10)
        self.assertAlmostEqual(result["capture10"], .1)

    @unittest.skipUnless(importlib.util.find_spec("lifetimes") and importlib.util.find_spec("shap"),
                         "Install requirements-track-a.txt for probabilistic and SHAP integration")
    def test_long_horizon_models_and_shap_additive_reconstruction(self):
        out = self.folder / "clv_benchmark"
        out.mkdir()
        rows, audit = benchmark(self.panel, out, origin="2020-07", horizon=2)
        self.assertEqual({r["method"] for r in rows},
                         {"BGNBD", "BGNBD_GammaGamma", "gradient_boosting", "historical_mean"})
        self.assertLessEqual(audit["max_train_label_month"], audit["origin"])
        self.assertTrue(audit["explanation"]["additive_reconstruction_verified"])
        self.assertTrue((out / "clv_6m_segment_errors.csv").is_file())

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temporary.name)
        cls.config = fixture(cls.folder)
        cls.root = run(cls.config)
        cls.panel = Panel(cls.root, Path(cls.config["data"]["work_dir"]) / "cache")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_horizon_censoring_and_mature_training_labels(self):
        panel = self.panel
        target = panel.target("2020-02", 3)
        self.assertNotIn(0, target.index)  # disappears in March / April
        self.assertNotIn(1, target.index)  # first observed in May
        self.assertTrue(target.ge(0).all())
        self.assertTrue(all(pd.Period(m, "M") + 3 <= pd.Period("2020-07", "M")
                            for m in panel.training_origins("2020-07", 3)))
        with self.assertRaisesRegex(ValueError, "beyond observed"):
            panel.target("2020-08", 2)

    def test_raw_eda_handles_nullable_tenure_and_missing_optional_fields(self):
        out = self.folder / "raw_eda"
        out.mkdir()
        summary, _ = raw_eda(self.config["data"]["train_csv_or_zip"], self.panel, out)
        self.assertEqual(summary["months"], 9)
        self.assertIn("indfall", summary["absent_optional_columns"])
        trend = pd.read_csv(out / "segment_product_trend.csv")
        self.assertEqual(set(trend.dimension), {"segmento", "canal_entrada", "antiguedad"})

    def test_future_changes_do_not_change_current_history(self):
        old = self.panel.history["2020-05"].copy()
        future = self.panel.cache / "2020-09.parquet"
        raw_bytes = future.read_bytes()
        try:
            from pipeline.common import PRODUCTS
            q = pd.read_parquet(future)
            q[PRODUCTS[4]] = 1 - q[PRODUCTS[4]]
            q.to_parquet(future, index=False)
            rebuilt = Panel(self.root, self.panel.cache)
            pd.testing.assert_frame_equal(old, rebuilt.history["2020-05"])
        finally:
            future.write_bytes(raw_bytes)

    def test_product_event_export_and_count_overflow(self):
        destination = self.folder / "event_export"
        result, paths = export_events(self.panel, destination)
        actual = sum(int(ev.acquisitions.sum()) for ev in self.panel.events.values())
        self.assertEqual(result["acquisition_rows"], actual)
        exported = pd.concat([pd.read_parquet(path) for path in paths])
        self.assertTrue((exported.available_month == exported.event_month).all())
        self.assertTrue((exported.source_month < exported.event_month).all())
        from pipeline.common import PRODUCTS
        counts, confidence, lift, _ = matrices(pd.DataFrame(np.ones((300, 24), dtype="uint8"), columns=PRODUCTS))
        self.assertEqual(counts[0, 1], 300)  # no uint8 wrap at 255
        self.assertEqual(confidence[0, 1], 1)
        self.assertEqual(lift[0, 1], 1)

    def test_activity_death_and_unknown_eligibility(self):
        flags = pd.DataFrame({"indfall": ["S", "N", "N"], "ind_actividad_cliente": ["1", "0", pd.NA]},
                             index=pd.Index([10, 11, 12], name="customer_id"))
        _, frame = lifecycle_export(self.panel, flags, self.folder / "lifecycle.parquet")
        self.assertEqual(frame.loc[10, "lifecycle"], "Churned")
        self.assertEqual(frame.loc[11, "lifecycle"], "At-risk")
        self.assertFalse(frame.loc[[10, 11, 12], "cross_sell_eligible"].any())
        self.assertTrue(frame.loc[12, "is_observed"])

    def test_s3_manifest_validation_before_any_network_write(self):
        root = self.folder / "publish"
        root.mkdir(exist_ok=True)
        path = root / "features.parquet"
        pd.DataFrame({"customer_id": [1]}).to_parquet(path, index=False)
        write_manifest(root, [path])
        plan = upload(root / "processed_manifest.json", "s3://test-bucket/track-a")
        self.assertFalse(plan["applied"])
        self.assertEqual(plan["files"][0]["key"], "track-a/features.parquet")
        client = Mock()
        client.head_object.return_value = {"ContentLength": path.stat().st_size,
            "Metadata": {"sha256": plan["files"][0]["sha256"]}}
        result = upload(root / "processed_manifest.json", "s3://test-bucket/track-a", apply=True, client=client)
        self.assertTrue(result["applied"])
        self.assertEqual(client.upload_file.call_count, 2)  # data then completion manifest
        path.write_bytes(b"changed")
        client.reset_mock()
        with self.assertRaisesRegex(ValueError, "changed"):
            upload(root / "processed_manifest.json", "s3://test-bucket/track-a", apply=True, client=client)
        client.upload_file.assert_not_called()
        with self.assertRaises(ValueError):
            upload(root / "processed_manifest.json", "s3://test-bucket/../bad")
