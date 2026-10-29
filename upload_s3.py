#!/usr/bin/env python3
"""Upload Pixiv artifacts directly to an S3-compatible object store."""
from __future__ import annotations

import argparse
import base64
import hashlib
import mimetypes
import os
import sys
from pathlib import Path

import boto3
from botocore.client import Config

from crawler import append_jsonl, load_dotenv

PROJECT = Path(__file__).resolve().parent


def create_client():
    load_dotenv(PROJECT / ".env")
    required = ("S3_ENDPOINT", "S3_REGION", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("missing S3 configuration: " + ",".join(missing))
    # Optional Cloudflare bypass marker: when CF_BYPASS_TOKEN is set, it is
    # appended to the User-Agent so a CF rule can Skip the challenge for
    # requests carrying it. It is NOT a credential: S3 auth still relies on
    # the access keys, and this token must never be a real key or password.
    config_kwargs = dict(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    )
    bypass = os.getenv("CF_BYPASS_TOKEN", "").strip()
    if bypass:
        config_kwargs["user_agent_extra"] = bypass
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"].rstrip("/"),
        region_name=os.environ["S3_REGION"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        config=Config(**config_kwargs),
    )


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    parser.add_argument("--remote-dir", required=True)
    parser.add_argument("--log", required=True)
    args = parser.parse_args()
    log_path = Path(args.log)
    remote_dir = args.remote_dir.strip("/")
    try:
        client = create_client()
    except Exception as exc:
        print(f"s3 config failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        append_jsonl(log_path, "s3_config", status="error", error=type(exc).__name__)
        return 2
    success = True
    for raw_path in args.files:
        path = Path(raw_path)
        # The caller supplies the complete remote directory for each pool.
        # Do not infer or append R-18 again; that produced duplicate paths.
        key = f"{remote_dir}/{path.name}"
        try:
            if not path.is_file():
                raise FileNotFoundError(path)
            with path.open("rb") as stream:
                client.put_object(
                    Bucket=os.environ["S3_BUCKET"],
                    Key=key,
                    Body=stream,
                    ContentLength=path.stat().st_size,
                    ContentMD5=base64.b64encode(hashlib.md5(path.read_bytes()).digest()).decode(),
                    ContentType=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                )
            metadata = client.head_object(Bucket=os.environ["S3_BUCKET"], Key=key)
            if int(metadata.get("ContentLength", -1)) != path.stat().st_size:
                raise RuntimeError("remote size mismatch")
            append_jsonl(log_path, "s3_upload", file=str(path), key=key, size=path.stat().st_size, sha256=file_sha256(path), status="ok")
        except Exception as exc:
            print(f"s3 upload failed: {path} -> {key}: {type(exc).__name__}: {exc}", file=sys.stderr)
            append_jsonl(log_path, "s3_upload", file=str(path), key=key, status="error", error=type(exc).__name__)
            success = False
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
