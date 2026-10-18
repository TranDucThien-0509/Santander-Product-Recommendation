"""Publish only manifest-listed processed files to GCS, verify SHA256 round-trip.

The destination is a NEW run prefix; the processed/ directory is created below it.
No ACL or bucket policy is changed. The completion manifest is published last.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cloud(*args):
    binary = "gcloud.cmd" if os.name == "nt" else "gcloud"
    # gcloud's Windows entry point is a batch file. Restrict shell metacharacters.
    if os.name == "nt" and any(re.search(r"[&|<>^%!\r\n]", str(arg)) for arg in args):
        raise ValueError("Unsupported shell metacharacters in gcloud arguments")
    env = {**os.environ, "CLOUDSDK_STORAGE_PROCESS_COUNT": "1", "CLOUDSDK_STORAGE_THREAD_COUNT": "1"}
    result = subprocess.run([binary, "storage", *map(str, args)], check=True,
        capture_output=True, text=True, encoding="utf-8", env=env)
    return result.stdout


def object_records(entries):
    records = []
    for entry in entries:
        item = entry.get("metadata", entry)
        if "generation" in item:
            records.append(dict(name=item["name"], generation=item["generation"], bytes=int(item["size"]),
                crc32c=item.get("crc32c_hash", item.get("crc32c"))))
    return records


def publish(manifest, destination, apply=False, verify_only=False):
    manifest = Path(manifest).resolve()
    if not re.fullmatch(r"gs://[a-z0-9][a-z0-9._-]+/[A-Za-z0-9._/-]+", destination) or ".." in destination.split("/"):
        raise ValueError("Use gs://bucket/new-run-prefix with simple path components")
    destination = destination.rstrip("/")
    records = json.loads(manifest.read_text(encoding="utf-8-sig"))["files"]
    if not records:
        raise ValueError("Processed manifest must list files")
    names = set()
    for item in records:
        name = item["path"]
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", name) or ".." in name.split("/") or name in names:
            raise ValueError("Invalid or duplicate processed path")
        names.add(name)
        path = (manifest.parent / name).resolve()
        path.relative_to(manifest.parent)
        if path.suffix not in (".parquet", ".json", ".md"):
            raise ValueError("Only generated processed data/spec files are allowed")
        if sha256(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
            raise ValueError("Processed file changed after manifest generation")
    receipt = dict(provider="GCS", status="dry_run", destination=destination + "/processed",
        file_count=len(records), data_bytes=sum(r["bytes"] for r in records),
        manifest_sha256=sha256(manifest))
    if not apply and not verify_only:
        return receipt
    with tempfile.TemporaryDirectory(prefix="gcs_publish_", dir=manifest.parent.parent) as temporary:
        temporary = Path(temporary)
        staged = temporary / "processed"
        staged.mkdir()
        for item in records:
            target = staged / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(manifest.parent / item["path"], target)
            if sha256(target) != item["sha256"]:
                raise ValueError("Staged processed bytes changed")
        # A zero generation precondition prevents overwriting a previous object.
        if not verify_only:
            cloud("cp", "--recursive", "--if-generation-match=0", staged, destination + "/")
        downloaded = temporary / "downloaded"
        downloaded.mkdir()
        cloud("cp", "--recursive", receipt["destination"], str(downloaded) + os.sep)
        verified = downloaded / "processed"
        for item in records:
            path = verified / item["path"]
            if not path.is_file() or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
                raise RuntimeError("GCS round-trip SHA256/size verification failed; completion manifest not published")
        if not verify_only:
            cloud("cp", "--if-generation-match=0", manifest, receipt["destination"] + "/processed_manifest.json")
        marker = temporary / "manifest_download.json"
        cloud("cp", receipt["destination"] + "/processed_manifest.json", marker)
        if sha256(marker) != receipt["manifest_sha256"]:
            raise RuntimeError("GCS completion manifest SHA256 mismatch")
        metadata = json.loads(cloud("ls", "--json", receipt["destination"] + "/**"))
        receipt.update(status="verified", verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            verification="Downloaded every data/spec object and completion manifest; matched size and SHA256",
            manifest_uri=receipt["destination"] + "/processed_manifest.json",
            action="verify_existing" if verify_only else "upload_and_verify",
            objects=object_records(metadata))
        if len(receipt["objects"]) != len(records) + 1:
            raise RuntimeError("Unexpected published object count")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--destination", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify-only", action="store_true", help="Download/verify an existing publication; no cloud writes")
    parser.add_argument("--receipt", help="Local verification receipt path")
    args = parser.parse_args()
    receipt = publish(args.manifest, args.destination, args.apply, args.verify_only)
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k != "objects"}, indent=2))


if __name__ == "__main__":
    main()
