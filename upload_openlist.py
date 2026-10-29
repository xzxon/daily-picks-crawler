#!/usr/bin/env python3
"""Upload Pixiv files to OpenList WebDAV and verify by re-downloading via signed proxy URL.

The WebDAV GET on the /S3/TG storage 302-redirects to an internal address
(tgs3:8090) that is unreachable from outside, so verification goes through
OpenList's /api/fs/get signed raw_url (which proxies the download).
"""
from __future__ import annotations
import argparse, hashlib, json, os
from pathlib import Path
import requests
from crawler import load_dotenv, append_jsonl


def remote_path(base: str, name: str) -> str:
    target = "/".join([base.strip("/"), name.lstrip("/")])
    return "/" + target if not target.startswith("/") else target


def _openlist_token(base: str, user: str, password: str) -> str:
    r = requests.post(base + "/api/auth/login",
                      json={"username": user, "password": password}, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 200:
        raise RuntimeError(f"OpenList login failed: {data.get('message')}")
    return data["data"]["token"]


def _verify_remote(base: str, token: str, webdav_file_path: str, digest: str) -> tuple[bool, str]:
    """webdav_file_path like /nanobot/pixiv/foo.jpg (nanobot user view)."""
    try:
        g = requests.post(base + "/api/fs/get", json={"path": webdav_file_path},
                          headers={"Authorization": token}, timeout=180)
        g.raise_for_status()
        raw = (g.json().get("data") or {}).get("raw_url")
        if not raw:
            return False, "no_raw_url"
        resp = requests.get(raw, timeout=300)
        resp.raise_for_status()
        remote_digest = hashlib.sha256(resp.content).hexdigest()
        return remote_digest == digest, "verified" if remote_digest == digest else "hash_mismatch"
    except Exception as exc:
        return False, f"verify_error:{type(exc).__name__}"


def upload_file(path: Path, remote_dir: str, cfg: dict, log_path: Path, token: str) -> bool:
    base = os.getenv("OPENLIST_URL", "").rstrip("/")
    user, password = os.getenv("OPENLIST_USERNAME"), os.getenv("OPENLIST_PASSWORD")
    if not base or not user or not password:
        raise RuntimeError("OpenList credentials are not configured")
    target = remote_path(remote_dir, path.name)
    url = base + "/dav" + target  # WebDAV root + user-view path
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        with path.open("rb") as fh:
            put = requests.put(url, data=fh, auth=(user, password), timeout=300)
        put.raise_for_status()
        ok, status = _verify_remote(base, token, target, digest)
        append_jsonl(log_path, "upload", file=path.name, remote=target,
                     status=status, sha256=digest)
        return ok
    except Exception as exc:
        append_jsonl(log_path, "upload", file=path.name, remote=target,
                     status="error", error=type(exc).__name__)
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="+")
    p.add_argument("--remote-dir", default=None)
    p.add_argument("--log", default=None)
    p.add_argument("--new-items", default=None)
    args = p.parse_args()
    project = Path(__file__).resolve().parent
    load_dotenv(project / ".env")
    log = Path(args.log or os.getenv("PIXIV_DAILY_OUTPUT_DIR", "/tmp")) / "upload_events.jsonl"
    remote = args.remote_dir or os.getenv("OPENLIST_NORMAL_DIR", "/nanobot/pixiv/")
    base = os.getenv("OPENLIST_URL", "").rstrip("/")
    token = _openlist_token(base, os.getenv("OPENLIST_USERNAME"), os.getenv("OPENLIST_PASSWORD"))
    ok = sum(upload_file(Path(f), remote, {}, log, token) for f in args.files)
    return 0 if ok == len(args.files) else 1


if __name__ == "__main__":
    raise SystemExit(main())
