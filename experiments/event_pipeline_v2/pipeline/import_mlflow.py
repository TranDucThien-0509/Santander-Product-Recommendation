"""Import completed historical runs without fitting models again."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from .mlflow_tracking import ExperimentTracker


def import_run(root, settings, source_uri=None, source_code_sha=None):
    root = Path(root).resolve()
    config = json.loads((root / 'config.resolved.json').read_text(encoding='utf-8-sig'))
    completed = json.loads((root / 'completed.json').read_text(encoding='utf-8-sig'))
    if completed.get('status') != 'success':
        raise ValueError('Only completed successful source runs may be imported')
    rows = json.loads((root / 'comparison.json').read_text(encoding='utf-8-sig'))
    names = [row['variant'] for row in rows]
    if not names or len(set(names)) != len(names) or set(names) != set(completed['variants']):
        raise ValueError('Comparison variants must match the completion manifest')
    for name in names:
        if not isinstance(name, str) or not name or any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for ch in name):
            raise ValueError('Unsafe variant directory name')
        for stage in ('validation', 'test'):
            json.loads((root / name / f'{stage}_metrics.json').read_text(encoding='utf-8-sig'))
    identity = source_uri or root.as_uri()
    tracker = ExperimentTracker(config, root, settings={**settings, 'enabled': True},
                                mode='historical_import', source_uri=identity,
                                source_code_sha=source_code_sha)
    tracker._setup()
    key = hashlib.sha256(identity.encode()).hexdigest()
    existing = tracker.client.search_runs([tracker.experiment_id],
        filter_string=f"tags.`santander.source_key` = '{key}' and attributes.status = 'FINISHED'")
    if existing:
        return existing[0].info.run_id
    with tracker:
        resources = root / 'feature_build_resources.json'
        if resources.is_file():
            tracker.parent.metrics('feature_build', json.loads(resources.read_text()))
        for row in rows:
            variant = copy.deepcopy(config)
            variant['feature_groups'] = row['feature_groups']
            with tracker.variant(row['variant'], variant) as child:
                child.metrics('ranker', row.get('resources', {}))
    return tracker.parent.run_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, help='Local copy of the original completed run directory')
    parser.add_argument('--tracking-uri', required=True)
    parser.add_argument('--experiment-name', default='santander-event-v2')
    parser.add_argument('--artifact-location')
    parser.add_argument('--source-uri', help='Original gs:// run URI, for provenance and deduplication')
    parser.add_argument('--source-code-sha', help='Revision which produced the original results')
    parser.add_argument('--log-models', action='store_true')
    args = parser.parse_args()
    run_id = import_run(args.run_dir, dict(tracking_uri=args.tracking_uri,
        experiment_name=args.experiment_name, artifact_location=args.artifact_location,
        log_models=args.log_models), args.source_uri, args.source_code_sha)
    print(f'MLflow parent run: {run_id}')


if __name__ == '__main__':
    main()
