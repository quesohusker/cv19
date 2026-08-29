"""Output storage and run manifest.

Responses are organised by season first, then endpoint::

    <root>/2023/games/all.json.gz
    <root>/2023/plays/week-3_seasonType-regular.json.gz
    <root>/2023/stats__season/all.json.gz
    <root>/static/venues/all.json.gz

Season-less reference data (venues, play types, draft positions...) lands in
``static/``. Because the directory carries the season, it is not repeated in
the filename.

A JSONL manifest at the root records every completed call so an interrupted
sweep resumes without re-spending API quota.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import threading
from typing import Any, Dict, Iterator, Optional, Set

log = logging.getLogger(__name__)

MANIFEST_NAME = "_manifest.jsonl"
STATIC_PARTITION = "static"

#: Default destination: the user's external drive.
DEFAULT_OUT = "/Volumes/1TB external/CFDB Stats"


class DriveNotMounted(RuntimeError):
    """The destination volume is not mounted."""


def ensure_destination(path: str) -> str:
    """Validate the output root before a long run writes anything.

    On macOS an unmounted external drive leaves ``/Volumes`` writable, so a
    naive ``makedirs`` would silently create a stub directory on the boot disk
    and fill it with tens of gigabytes. Refuse that case explicitly.
    """
    path = os.path.abspath(path)
    parts = path.split(os.sep)
    if len(parts) > 2 and parts[1] == "Volumes":
        mount = os.sep.join(parts[:3])  # e.g. /Volumes/1TB external
        if not os.path.ismount(mount) and not os.path.isdir(mount):
            raise DriveNotMounted(
                f"{mount!r} is not mounted. Connect the drive (or pass --out) "
                "before starting the pull."
            )
    os.makedirs(path, exist_ok=True)
    if not os.access(path, os.W_OK):
        raise PermissionError(f"output directory is not writable: {path}")
    return path


def _safe(value: Any) -> str:
    """Make a parameter value safe for use in a filename."""
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in str(value))


def task_key(path: str, params: Dict[str, Any]) -> str:
    """Stable identifier for one (endpoint, parameters) call."""
    if not params:
        return path
    parts = ",".join(f"{k}={params[k]}" for k in sorted(params))
    return f"{path}?{parts}"


def partition_of(params: Dict[str, Any]) -> str:
    """Season directory for a call, or ``static`` when it has no season."""
    year = params.get("year")
    return str(year) if year is not None else STATIC_PARTITION


def file_stem(params: Dict[str, Any]) -> str:
    """Filename (no extension) from the params, excluding the season."""
    rest = {k: v for k, v in params.items() if k != "year"}
    if not rest:
        return "all"
    return "_".join(f"{k}-{_safe(rest[k])}" for k in sorted(rest))


class Store:
    """Writes responses to disk and tracks what has already been pulled."""

    def __init__(self, root: str, *, compress: bool = True) -> None:
        self.root = ensure_destination(root)
        self.compress = compress
        self.manifest_path = os.path.join(self.root, MANIFEST_NAME)
        self._lock = threading.Lock()
        self._done: Set[str] = set()
        #: endpoint path -> finer strategy the API forced us onto previously.
        self.degraded: Dict[str, str] = {}
        self._load_manifest()

    # -- manifest ----------------------------------------------------------
    def _load_manifest(self) -> None:
        if not os.path.exists(self.manifest_path):
            return
        bad = 0
        with open(self.manifest_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    bad += 1
                    continue
                if rec.get("status") in ("ok", "empty", "skipped"):
                    self._done.add(rec["key"])
                if rec.get("degraded_to") and rec.get("endpoint"):
                    self.degraded[rec["endpoint"]] = rec["degraded_to"]
        if bad:
            log.warning("ignored %d malformed manifest line(s)", bad)
        if self._done:
            log.info("resume: %d call(s) already completed", len(self._done))

    def is_done(self, key: str) -> bool:
        with self._lock:
            return key in self._done

    def record(self, key: str, status: str, **extra: Any) -> None:
        """Append a manifest entry. ``status`` is ok/empty/skipped/error."""
        rec = {"key": key, "status": status}
        rec.update(extra)
        line = json.dumps(rec, separators=(",", ":")) + "\n"
        with self._lock:
            with open(self.manifest_path, "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
            if status in ("ok", "empty", "skipped"):
                self._done.add(key)

    # -- payloads ----------------------------------------------------------
    def path_for(self, slug: str, params: Dict[str, Any]) -> str:
        ext = ".json.gz" if self.compress else ".json"
        return os.path.join(
            self.root, partition_of(params), slug, file_stem(params) + ext
        )

    def write(self, slug: str, params: Dict[str, Any], payload: Any) -> str:
        """Persist one response; returns the path written."""
        path = self.path_for(slug, params)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"

        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if self.compress:
            with gzip.open(tmp, "wb") as fh:
                fh.write(data)
        else:
            with open(tmp, "wb") as fh:
                fh.write(data)
        os.replace(tmp, path)  # atomic: a partial file never looks complete
        return path

    # -- reading back ------------------------------------------------------
    def seasons(self) -> list:
        """Season partitions present on disk, newest first."""
        out = []
        for name in os.listdir(self.root):
            if name.isdigit() and os.path.isdir(os.path.join(self.root, name)):
                out.append(int(name))
        return sorted(out, reverse=True)

    def read(self, slug: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Load a single previously-written payload."""
        params = params or {}
        base = os.path.join(self.root, partition_of(params), slug, file_stem(params))
        for ext in (".json.gz", ".json"):
            if os.path.exists(base + ext):
                opener = gzip.open if ext.endswith(".gz") else open
                with opener(base + ext, "rb") as fh:
                    return json.loads(fh.read().decode("utf-8"))
        raise FileNotFoundError(base)

    def iter_payloads(self, slug: str, seasons: Optional[list] = None) -> Iterator[Any]:
        """Yield every payload stored for an endpoint, across all seasons."""
        wanted = {str(s) for s in seasons} if seasons else None
        for part in sorted(os.listdir(self.root)):
            if wanted is not None and part not in wanted and part != STATIC_PARTITION:
                continue
            directory = os.path.join(self.root, part, slug)
            if not os.path.isdir(directory):
                continue
            for name in sorted(os.listdir(directory)):
                if not name.endswith((".json", ".json.gz")):
                    continue
                path = os.path.join(directory, name)
                opener = gzip.open if name.endswith(".gz") else open
                try:
                    with opener(path, "rb") as fh:
                        yield json.loads(fh.read().decode("utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    log.warning("could not read %s: %s", path, exc)

    def iter_rows(
        self, slug: str, seasons: Optional[list] = None
    ) -> Iterator[Dict[str, Any]]:
        """Flatten every stored payload for an endpoint into dict rows."""
        for payload in self.iter_payloads(slug, seasons):
            if isinstance(payload, list):
                for row in payload:
                    if isinstance(row, dict):
                        yield row
            elif isinstance(payload, dict):
                yield payload


def count_rows(payload: Any) -> int:
    """Number of records in a response payload."""
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        return 1
    return 0
