"""Shared helpers for data source collectors."""
from __future__ import annotations

import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = REPO_ROOT / "data"

DEFAULT_HEADERS = {
    "User-Agent": "cv19-volleyball-data-collector/1.0 (+https://github.com/quesohusker/cv19)"
}


def download_file(
    url: str,
    dest: Path,
    *,
    session: requests.Session | None = None,
    max_retries: int = 4,
    timeout: int = 120,
) -> dict:
    """Download `url` to `dest`, skipping if a same-size file already exists.

    Returns a small result dict used to build the manifest: status is one of
    "downloaded", "skipped" (already present), or "failed".
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    sess = session or requests
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            with sess.get(url, headers=DEFAULT_HEADERS, stream=True, timeout=timeout) as resp:
                resp.raise_for_status()
                expected = int(resp.headers.get("Content-Length", 0)) or None
                if expected and dest.exists() and dest.stat().st_size == expected:
                    return {"url": url, "path": str(dest), "status": "skipped", "bytes": expected}
                tmp = dest.with_suffix(dest.suffix + ".part")
                written = 0
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            written += len(chunk)
                tmp.rename(dest)
                return {"url": url, "path": str(dest), "status": "downloaded", "bytes": written}
        except requests.RequestException as exc:
            last_error = str(exc)
            time.sleep(min(2 ** attempt, 20))

    return {"url": url, "path": str(dest), "status": "failed", "error": last_error}
