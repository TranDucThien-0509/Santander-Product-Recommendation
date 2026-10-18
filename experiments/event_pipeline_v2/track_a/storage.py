"""Explicit processed-file manifest and private, opt-in S3 upload."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from pipeline.common import write_json


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(root, paths):
    root = Path(root).resolve()
    records = []
    for path in paths:
        path = Path(path).resolve()
        relative = path.relative_to(root)
        if path.suffix not in (".parquet", ".json", ".md"):
            raise ValueError("Only explicitly generated processed Parquet/spec files may be published")
        records.append(dict(path=relative.as_posix(), bytes=path.stat().st_size, sha256=digest(path)))
    write_json(root / "processed_manifest.json", dict(format_version=1, files=records,
        content="Kaggle research customer features and verified acquisition events; not real production customers"))


def upload(manifest, destination, region=None, apply=False, client=None):
    manifest = Path(manifest).resolve()
    root = manifest.parent
    uri = urlsplit(destination)
    if uri.scheme != "s3" or not uri.netloc or uri.query or uri.fragment or "@" in uri.netloc:
        raise ValueError("Destination must be s3://bucket/optional-prefix, without credentials")
    prefix = uri.path.strip("/")
    if ".." in prefix.split("/"):
        raise ValueError("S3 prefix must not contain traversal")
    records = json.loads(manifest.read_text())["files"]
    plan = []
    for record in records:
        path = (root / record["path"]).resolve()
        path.relative_to(root)
        if not path.is_file() or digest(path) != record["sha256"] or path.stat().st_size != record["bytes"]:
            raise ValueError("Processed file changed after manifest generation")
        key = "/".join(s for s in [prefix, record["path"]] if s)
        plan.append(dict(path=str(path), bucket=uri.netloc, key=key, sha256=record["sha256"], bytes=record["bytes"]))
    # Resolve every path/hash before performing the first network write.
    if apply:
        if client is None:
            import boto3
            client = boto3.client("s3", region_name=region)
        for item in plan:
            client.upload_file(item["path"], item["bucket"], item["key"], ExtraArgs={
                "ServerSideEncryption": "AES256", "ChecksumAlgorithm": "SHA256", "Metadata": {"sha256": item["sha256"]}})
            head = client.head_object(Bucket=item["bucket"], Key=item["key"])
            if head["ContentLength"] != item["bytes"] or head.get("Metadata", {}).get("sha256") != item["sha256"]:
                raise RuntimeError("Uploaded object failed size/manifest metadata verification")
        # Publish the manifest last, so readers can require it as the completion marker.
        client.upload_file(str(manifest), uri.netloc, "/".join(s for s in [prefix, manifest.name] if s),
            ExtraArgs={"ServerSideEncryption": "AES256", "ChecksumAlgorithm": "SHA256"})
    return dict(applied=apply, destination=destination, files=plan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--region")
    parser.add_argument("--apply", action="store_true", help="Upload; without this flag only validate and print the plan")
    args = parser.parse_args()
    print(json.dumps(upload(args.manifest, args.destination, args.region, args.apply), indent=2))


if __name__ == "__main__":
    main()
