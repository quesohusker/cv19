"""Thin HTTP client for the CFBD API.

Handles bearer auth, polite pacing, retry with exponential backoff, and
classification of the errors the sweep needs to react to.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import Any, Dict, Optional

import requests

from .config import resolve_api_key
from .endpoints import BASE_URL

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class CFBDError(Exception):
    """Base error for this client."""


class AuthError(CFBDError):
    """API key missing, rejected, or lacking entitlement for an endpoint."""


class BadRequest(CFBDError):
    """HTTP 400 -- usually a required query parameter we did not supply.

    The runner treats this as a signal to retry at finer granularity rather
    than as a fatal error.
    """


class NotFound(CFBDError):
    """HTTP 404 -- no such resource (e.g. a game id that does not exist)."""


class RateLimited(CFBDError):
    """Retries exhausted against 429."""


def load_api_key(explicit: Optional[str] = None) -> str:
    """Resolve the API key. See :mod:`cfbd_pull.config` for the search order."""
    key = resolve_api_key(explicit)
    if not key:
        raise AuthError(
            "No API key found.\n"
            "Create cfbd_pull/local_key.py containing:\n"
            '    API_KEY = "your-key-here"\n'
            "(that file is git-ignored), or set the CFBD_API_KEY environment "
            "variable, or pass --api-key.\n"
            "Get a free key at https://collegefootballdata.com/key"
        )
    return key


class CFBDClient:
    """Rate-limited, retrying JSON client for a single CFBD account."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = BASE_URL,
        *,
        min_interval: float = 0.6,
        timeout: float = 60.0,
        max_retries: int = 5,
        user_agent: str = "cfbd-pull/1.0 (+https://github.com/quesohusker/cv19)",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval

        self._lock = threading.Lock()
        self._next_allowed = 0.0

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {load_api_key(api_key)}",
                "Accept": "application/json",
                "User-Agent": user_agent,
            }
        )

        # Counters for the end-of-run summary.
        self.calls = 0
        self.retries = 0
        self.bytes_in = 0

    # -- internals ---------------------------------------------------------
    def _pace(self) -> None:
        """Space requests out by at least ``min_interval`` seconds."""
        with self._lock:
            now = time.monotonic()
            wait = self._next_allowed - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._next_allowed = now + self.min_interval

    @staticmethod
    def _clean(params: Dict[str, Any]) -> Dict[str, Any]:
        """Drop None values and normalise booleans to the API's spelling."""
        out = {}
        for k, v in params.items():
            if v is None:
                continue
            out[k] = "true" if v is True else "false" if v is False else v
        return out

    # -- public ------------------------------------------------------------
    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """GET ``path`` and return decoded JSON.

        Raises :class:`BadRequest`, :class:`NotFound`, :class:`AuthError` or
        :class:`RateLimited` as appropriate; retries transient failures.
        """
        url = f"{self.base_url}{path}"
        query = self._clean(params or {})
        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            self._pace()
            try:
                self.calls += 1
                resp = self.session.get(url, params=query, timeout=self.timeout)
            except requests.RequestException as exc:  # network-level failure
                last_exc = exc
                if attempt == self.max_retries:
                    break
                self._sleep_backoff(attempt)
                continue

            status = resp.status_code

            if status == 200:
                self.bytes_in += len(resp.content)
                if not resp.content:
                    return []
                try:
                    return resp.json()
                except ValueError as exc:
                    last_exc = CFBDError(f"non-JSON response from {path}: {exc}")
                    if attempt == self.max_retries:
                        break
                    self._sleep_backoff(attempt)
                    continue

            if status == 400:
                raise BadRequest(f"400 {path} params={query}: {resp.text[:300]}")
            if status in (401, 403):
                raise AuthError(
                    f"{status} {path}: {resp.text[:300]}\n"
                    "Check CFBD_API_KEY; some endpoints require a paid tier."
                )
            if status == 404:
                raise NotFound(f"404 {path} params={query}")

            if status in RETRY_STATUS:
                if attempt == self.max_retries:
                    if status == 429:
                        raise RateLimited(f"429 {path}: retries exhausted")
                    break
                self.retries += 1
                self._sleep_backoff(attempt, resp.headers.get("Retry-After"))
                continue

            raise CFBDError(f"{status} {path}: {resp.text[:300]}")

        raise CFBDError(f"{path} failed after {self.max_retries} retries: {last_exc}")

    def _sleep_backoff(self, attempt: int, retry_after: Optional[str] = None) -> None:
        """Exponential backoff with jitter, honouring Retry-After when given."""
        if retry_after:
            try:
                time.sleep(min(float(retry_after), 120.0))
                return
            except (TypeError, ValueError):
                pass
        delay = min(2.0 ** attempt, 60.0) + random.uniform(0, 0.75)
        log.debug("backing off %.1fs (attempt %d)", delay, attempt + 1)
        time.sleep(delay)
