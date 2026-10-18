import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mlflow import MlflowClient
from test_pipeline import fixture
from pipeline.run_pipeline import run
from pipeline.import_mlflow import import_run
from pipeline.mlflow_tracking import sanitize, validate_tracking


@patch.dict(os.environ, {"MLFLOW_SQLALCHEMYSTORE_POOLCLASS": "NullPool"})
class MLflowTests(unittest.TestCase):
    def test_live_nested_runs_and_historical_import(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            c = fixture(folder)
            c['run'].update(ablation=True, refit_for_forecast=False)
            c['feature_groups'] = {k: k == 'rfm' for k in c['feature_groups']}
            c['tracking'].update(enabled=True, log_models=True)
            out = run(c)
            record = json.loads((out / 'mlflow_tracking.json').read_text())
            client = MlflowClient(tracking_uri=record['tracking_uri'])
            self.assertEqual(record['status'], 'FINISHED')
            self.assertEqual(set(record['variant_run_ids']), {'baseline', 'baseline_plus_rfm'})
            comparison = json.loads((out / 'comparison.json').read_text())
            for row in comparison:
                child = client.get_run(record['variant_run_ids'][row['variant']])
                self.assertEqual(child.info.status, 'FINISHED')
                self.assertEqual(child.data.tags['mlflow.parentRunId'], record['parent_run_id'])
                self.assertEqual(child.data.metrics['test.map_at_7_all'], row['test']['map_at_7_all'])
                self.assertIn('ranker.wall_seconds', child.data.metrics)
                self.assertEqual(child.data.params['feature_groups.rfm'], json.dumps(row['feature_groups']['rfm']))
                artifacts = client.list_artifacts(child.info.run_id)
                self.assertFalse(any(a.path.endswith(('.csv', '.parquet')) for a in artifacts))
                models = client.list_artifacts(child.info.run_id, 'evaluation_model')
                self.assertTrue(any(a.path.endswith('model.pkl') for a in models))
            settings = dict(tracking_uri=record['tracking_uri'], experiment_name='historical')
            imported = import_run(out, settings, 'gs://example/run', 'original-sha')
            self.assertEqual(imported, import_run(out, settings, 'gs://example/run', 'original-sha'))
            parent = client.get_run(imported)
            self.assertEqual(parent.data.tags['tracking.mode'], 'historical_import')
            self.assertEqual(parent.data.tags['santander.source_revision'], 'original-sha')
            self.assertEqual(len(client.search_runs([parent.info.experiment_id])), 3)

    def test_failed_fit_marks_parent_and_child_failed(self):
        with tempfile.TemporaryDirectory() as td:
            c = fixture(Path(td))
            c['tracking']['enabled'] = True
            with patch('pipeline.run_pipeline.train', side_effect=RuntimeError('fit failed')):
                with self.assertRaisesRegex(RuntimeError, 'fit failed'):
                    run(c)
            root = next((Path(c['data']['work_dir']) / 'runs').iterdir())
            record = json.loads((root / 'mlflow_tracking.json').read_text())
            client = MlflowClient(tracking_uri=record['tracking_uri'])
            self.assertEqual(record['status'], 'FAILED')
            for run_id in [record['parent_run_id'], *record['variant_run_ids'].values()]:
                self.assertEqual(client.get_run(run_id).info.status, 'FAILED')
            self.assertFalse((root / 'completed.json').exists())

    def test_tracking_config_and_redaction(self):
        validate_tracking({})
        with self.assertRaises(ValueError):
            validate_tracking({'enabled': 'true'})
        self.assertEqual(sanitize({'api_key': 'abc'})['api_key'], '[REDACTED]')
        self.assertEqual(sanitize('https://user:pass@host/path?token=abc'), 'https://host/path')
