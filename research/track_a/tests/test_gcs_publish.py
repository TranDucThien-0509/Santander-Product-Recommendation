import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("publish_gcs", Path(__file__).parents[1] / "scripts/publish_gcs.py")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class GcsPublisherTests(unittest.TestCase):
    def test_cli_metadata_nested_and_flat_shapes(self):
        items = publisher.object_records([
            {"type": "cloud_object", "metadata": {"name": "a", "generation": "1", "size": "20", "crc32c": "abc"}},
            {"name": "b", "generation": "2", "size": 30, "crc32c_hash": "def"},
            {"type": "prefix", "url": "gs://bucket/prefix/"},
        ])
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0], {"name": "a", "generation": "1", "bytes": 20, "crc32c": "abc"})
        self.assertEqual(items[1]["crc32c"], "def")

    def test_dry_run_and_changed_file_never_call_cloud(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "features.parquet"
            data.write_bytes(b"synthetic processed bytes")
            manifest = root / "processed_manifest.json"
            manifest.write_text(json.dumps({"files": [{"path": data.name, "bytes": data.stat().st_size,
                "sha256": publisher.sha256(data)}]}))
            with patch.object(publisher, "cloud", side_effect=AssertionError("No network expected")):
                receipt = publisher.publish(manifest, "gs://test-bucket/new-run")
                self.assertEqual(receipt["status"], "dry_run")
                self.assertEqual(receipt["file_count"], 1)
                data.write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "changed"):
                    publisher.publish(manifest, "gs://test-bucket/new-run", apply=True)

    def test_reject_traversal_and_shell_metacharacters(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps({"files": [{"path": "../secret.json", "bytes": 1, "sha256": "bad"}]}))
            with patch.object(publisher, "cloud", side_effect=AssertionError("No network expected")):
                with self.assertRaises(ValueError):
                    publisher.publish(manifest, "gs://test-bucket/new-run", apply=True)
                with self.assertRaises(ValueError):
                    publisher.publish(manifest, "gs://test-bucket/run&command", apply=True)
