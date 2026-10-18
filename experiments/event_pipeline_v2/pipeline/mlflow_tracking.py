"""Explicit MLflow runs; allowlisted aggregate artifacts, optional model bytes."""
import contextlib
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT_ARTIFACTS = (
    "config.resolved.json", "environment.json", "input_manifest.json",
    "point_in_time_audit.json", "feature_build_resources.json", "comparison.json",
    "completed.json", "published.json", "selection.json",
)
VARIANT_ARTIFACTS = (
    "validation_metrics.json", "test_metrics.json", "forecast_audit.json",
    "evaluation_model/feature_manifest.json", "forecast_model/feature_manifest.json",
)
MODEL_ARTIFACTS = ("evaluation_model/model.pkl", "forecast_model/model.pkl")
_SENSITIVE = re.compile(r"password|secret|token|credential|api[_-]?key|access[_-]?key|private[_-]?key|authorization", re.I)


def validate_tracking(settings):
    if not isinstance(settings, dict):
        raise ValueError("tracking must be an object")
    for key in ("enabled", "log_models"):
        if type(settings.get(key, False)) is not bool:
            raise ValueError(f"tracking.{key} must be a JSON boolean")
    for key in ("tracking_uri", "artifact_location"):
        value = settings.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"tracking.{key} must be null or a nonempty string")
    name = settings.get("experiment_name", "santander-event-v2")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("tracking.experiment_name must be nonempty")


def sanitize(value, key=""):
    """Never serialize environment credentials or credential-bearing URLs."""
    if _SENSITIVE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str) and "://" in value:
        parts = urlsplit(value)
        if "@" not in parts.netloc:
            return value.split("?", 1)[0].split("#", 1)[0]
        return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", ""))
    return value


def flatten(value, prefix=""):
    result = {}
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, dict):
            result.update(flatten(item, name))
        else:
            result[name] = json.dumps(item, sort_keys=True) if isinstance(item, (list, bool)) or item is None else str(item)
    return result


class TrackedRun:
    def __init__(self, client=None, run_id=None):
        self.client, self.run_id = client, run_id

    def metrics(self, prefix, values):
        if self.client is None:
            return
        from mlflow.entities import Metric
        timestamp = int(time.time() * 1000)
        metrics = [Metric(f"{prefix}.{key}" if prefix else key, float(value), timestamp, 0)
                   for key, value in values.items()
                   if type(value) in (int, float) and math.isfinite(value)]
        if metrics:
            self.client.log_batch(self.run_id, metrics=metrics)

    def params(self, values):
        if self.client is None:
            return
        from mlflow.entities import Param
        params = [Param(key, value) for key, value in flatten(sanitize(values)).items()]
        for start in range(0, len(params), 100):
            self.client.log_batch(self.run_id, params=params[start:start + 100])

    def json_artifact(self, path, artifact_file=None):
        path = Path(path)
        if self.client is not None and path.is_file():
            self.client.log_dict(self.run_id, sanitize(json.loads(path.read_text(encoding="utf-8-sig"))),
                                 artifact_file or path.name)


class ExperimentTracker:
    def __init__(self, config, root, settings=None, mode="live", source_uri=None,
                 source_code_sha=None):
        self.config, self.root = config, Path(root)
        self.settings = settings if settings is not None else config.get("tracking", {})
        validate_tracking(self.settings)
        self.enabled = self.settings.get("enabled", False)
        self.mode, self.source_uri = mode, source_uri
        self.source_code_sha = source_code_sha or os.environ.get("SANTANDER_CODE_SHA", "unrecorded")
        self.client = None
        self.parent = TrackedRun()
        self.children = {}
        self.experiment_id = None
        self.uri = None

    def _setup(self):
        if not self.enabled:
            return
        from mlflow import MlflowClient
        self.uri = self.settings.get("tracking_uri") or os.environ.get("MLFLOW_TRACKING_URI")
        local_artifacts = None
        if not self.uri:
            work = Path(self.config["data"]["work_dir"])
            if str(work).replace("\\", "/").startswith("/gcs/"):
                raise ValueError("Set MLFLOW_TRACKING_URI to a tracking server for GCS/Vertex runs; SQLite requires a local disk")
            store = work.resolve() / "mlflow"
            store.mkdir(parents=True, exist_ok=True)
            self.uri = "sqlite:///" + (store / "tracking.db").as_posix()
            local_artifacts = (store / "artifacts").as_uri()
        if self.uri.startswith("sqlite:") and "/gcs/" in self.uri:
            raise ValueError("SQLite tracking databases must not be placed on a GCS FUSE mount")
        self.client = MlflowClient(tracking_uri=self.uri)
        name = self.settings.get("experiment_name", "santander-event-v2")
        experiment = self.client.get_experiment_by_name(name)
        if experiment:
            if experiment.lifecycle_stage != "active":
                raise ValueError(f"MLflow experiment {name!r} is deleted; restore it or choose a new name")
            self.experiment_id = experiment.experiment_id
        else:
            artifact_location = self.settings.get("artifact_location") or local_artifacts
            self.experiment_id = self.client.create_experiment(name, artifact_location=artifact_location)

    def __enter__(self):
        self._setup()
        if not self.enabled:
            return self
        tags = {"mlflow.runName": self.root.name, "tracking.mode": self.mode,
                "santander.role": "pipeline", "santander.source_revision": self.source_code_sha,
                "evaluation.scope": "temporal development backtest"}
        if self.source_uri:
            tags["santander.source_uri"] = sanitize(self.source_uri)
            tags["santander.source_key"] = hashlib.sha256(self.source_uri.encode()).hexdigest()
        run = self.client.create_run(self.experiment_id, tags=tags)
        self.parent = TrackedRun(self.client, run.info.run_id)
        try:
            self.parent.params({k: v for k, v in self.config.items() if k != "tracking"})
            for name in ("config.resolved.json", "environment.json"):
                self.parent.json_artifact(self.root / name)
            self._write_record("RUNNING")
        except BaseException:
            self.client.set_terminated(self.parent.run_id, status="FAILED")
            raise
        return self

    def _write_record(self, status):
        record = dict(tracking_uri=sanitize(self.uri), experiment_id=self.experiment_id,
                      parent_run_id=self.parent.run_id, variant_run_ids=self.children,
                      mode=self.mode, status=status)
        (self.root / "mlflow_tracking.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    @contextlib.contextmanager
    def variant(self, name, config):
        if self.client is None:
            yield TrackedRun()
            return
        run = self.client.create_run(self.experiment_id, tags={
            "mlflow.runName": name, "mlflow.parentRunId": self.parent.run_id,
            "santander.role": "variant", "santander.variant": name,
            "tracking.mode": self.mode, "santander.source_revision": self.source_code_sha,
            "evaluation.scope": "temporal development backtest",
        })
        child = TrackedRun(self.client, run.info.run_id)
        self.children[name] = child.run_id
        self._write_record("RUNNING")
        try:
            child.params({k: config[k] for k in ("feature_groups", "model", "meta_models", "split")})
            yield child
            self.variant_artifacts(name, child)
        except BaseException:
            self.client.set_terminated(child.run_id, status="FAILED")
            raise
        else:
            self.client.set_terminated(child.run_id, status="FINISHED")

    def variant_artifacts(self, name, child):
        folder = self.root / name
        for relative in VARIANT_ARTIFACTS:
            child.json_artifact(folder / relative, relative)
        for stage in ("validation", "test"):
            path = folder / f"{stage}_metrics.json"
            if path.is_file():
                result = json.loads(path.read_text(encoding="utf-8-sig"))
                child.metrics(stage, result["aggregate"])
                for origin in result.get("by_origin", []):
                    child.metrics(f"{stage}.origin_{origin['origin']}", origin)
        forecast = folder / "forecast_audit.json"
        if forecast.is_file():
            child.metrics("forecast", json.loads(forecast.read_text(encoding="utf-8-sig")))
        if self.settings.get("log_models", False):
            for relative in MODEL_ARTIFACTS:
                path = folder / relative
                if path.is_file():
                    self.client.log_artifact(child.run_id, str(path), artifact_path=path.parent.name)

    def __exit__(self, exc_type, exc, traceback):
        if self.client is None:
            return False
        status = "FAILED" if exc_type else "FINISHED"
        try:
            for name in ROOT_ARTIFACTS:
                self.parent.json_artifact(self.root / name)
        except BaseException:
            self.client.set_terminated(self.parent.run_id, status="FAILED")
            self._write_record("FAILED")
            if exc_type is None:
                raise
        else:
            self.client.set_terminated(self.parent.run_id, status=status)
            self._write_record(status)
        return False
