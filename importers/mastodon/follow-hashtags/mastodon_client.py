#!/usr/bin/env python3
"""Mastodon tag-follow client with pacing, rate-limit respect, and retries.

Uses stdlib urllib. Never logs the bearer token.

Run:  python importers/mastodon/follow-hashtags/follow_hashtags.py --help
"""

from __future__ import annotations

import json
import math
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

DEFAULT_RATE_LIMIT_BUFFER = 5
DEFAULT_MAX_RETRIES = 3
DEFAULT_REQUEST_TIMEOUT = 30
MAX_SLEEP_MS = 5 * 60 * 1000


class FatalApiError(RuntimeError):
    """401/403 from the API. Retrying will not help."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class FollowResult:
    kind: str  # "followed" | "already" | "error"
    name: str
    status: int | None = None
    message: str | None = None


@dataclass
class _RateInfo:
    remaining: float | None = None
    reset_ms: float | None = None


@dataclass
class _HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


HttpFn = Callable[[str, dict[str, str], float], _HttpResponse]


def parse_reset(header: str | None) -> float | None:
    """Parse X-RateLimit-Reset (epoch secs, epoch ms, ISO, or HTTP date) to ms."""
    if header is None:
        return None
    trimmed = header.strip()
    if not trimmed:
        return None
    try:
        numeric = float(trimmed)
    except ValueError:
        numeric = float("nan")
    if math.isfinite(numeric):
        if numeric > 1e12:
            return numeric
        return numeric * 1000
    iso = trimmed.replace("Z", "+00:00") if trimmed.endswith("Z") else trimmed
    try:
        parsed = datetime.fromisoformat(iso)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp() * 1000
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(trimmed)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp() * 1000


def _urllib_post(url: str, headers: dict[str, str], timeout: float) -> _HttpResponse:
    req = urllib.request.Request(url, data=b"", headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            lowered = {k.lower(): v for k, v in resp.headers.items()}
            return _HttpResponse(status=resp.status, headers=lowered, body=resp.read())
    except urllib.error.HTTPError as exc:
        try:
            lowered = {
                k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])
            }
            body = exc.read() if hasattr(exc, "read") else b""
            return _HttpResponse(status=exc.code, headers=lowered, body=body or b"")
        finally:
            with suppress(OSError):
                exc.close()


class MastodonClient:
    """POST /api/v1/tags/<name>/follow with pacing and retries."""

    def __init__(
        self,
        instance: str,
        token: str,
        min_delay_ms: float,
        rate_limit_buffer: int = DEFAULT_RATE_LIMIT_BUFFER,
        max_retries: int = DEFAULT_MAX_RETRIES,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        http_fn: HttpFn | None = None,
        now: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._base = instance.rstrip("/")
        self._token = token
        self._min_delay_ms = min_delay_ms
        self._buffer = rate_limit_buffer
        self._max_retries = max(1, max_retries)
        self._timeout = request_timeout
        self._http = http_fn or _urllib_post
        self._now = now or (lambda: time.time() * 1000)
        self._sleep = sleep or (lambda ms: time.sleep(ms / 1000))
        self._request_count = 0
        self._last_start: float | None = None
        self._last_rate = _RateInfo()

    def request_count(self) -> int:
        """Return total POST attempts including retries."""
        return self._request_count

    def _bounded_sleep(self, ms: float) -> None:
        if ms <= 0:
            return
        self._sleep(min(ms, MAX_SLEEP_MS))

    def _backoff_sleep(
        self, attempt: int, retry_after: str | None, reset_ms: float | None = None
    ) -> None:
        if retry_after is not None:
            try:
                seconds = float(retry_after)
            except ValueError:
                seconds = float("nan")
            if math.isfinite(seconds) and seconds > 0:
                self._bounded_sleep(seconds * 1000)
                return
        if reset_ms is not None and reset_ms > self._now():
            self._bounded_sleep(reset_ms - self._now())
            return
        jitter = random.random() * 250
        self._bounded_sleep(1000 * (2**attempt) + jitter)

    def _request(self, path: str) -> _HttpResponse:
        if self._min_delay_ms > 0 and self._last_start is not None:
            elapsed = self._now() - self._last_start
            if elapsed < self._min_delay_ms:
                self._bounded_sleep(self._min_delay_ms - elapsed)
        remaining = self._last_rate.remaining
        reset = self._last_rate.reset_ms
        now_after_pace = self._now()
        if (
            remaining is not None
            and remaining < self._buffer
            and reset is not None
            and reset > now_after_pace
        ):
            self._bounded_sleep(reset - now_after_pace + 250)
        url = f"{self._base}{path}"
        real_headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            self._last_start = self._now()
            self._request_count += 1
            try:
                response = self._http(url, real_headers, self._timeout)
            except Exception as exc:
                last_error = exc
                if attempt + 1 >= self._max_retries:
                    raise RuntimeError(f"request to {path} failed: {exc}") from exc
                self._backoff_sleep(attempt, None)
                continue
            remaining_h = response.headers.get("x-ratelimit-remaining")
            try:
                remaining_n = float(remaining_h) if remaining_h is not None else None
            except ValueError:
                remaining_n = None
            reset_ms = parse_reset(response.headers.get("x-ratelimit-reset"))
            if remaining_n is not None and math.isfinite(remaining_n):
                self._last_rate = _RateInfo(remaining=remaining_n, reset_ms=reset_ms)
            if response.status in (401, 403):
                label = "unauthorized" if response.status == 401 else "forbidden"
                raise FatalApiError(f"{label} ({response.status})", response.status)
            if response.status == 429:
                if attempt + 1 >= self._max_retries:
                    raise RuntimeError(f"request to {path} rate-limited")
                self._backoff_sleep(
                    attempt, response.headers.get("retry-after"), reset_ms
                )
                continue
            if response.status >= 500:
                if attempt + 1 >= self._max_retries:
                    raise RuntimeError(
                        f"request to {path} failed with status {response.status}"
                    )
                self._backoff_sleep(attempt, None, reset_ms)
                continue
            return response
        raise RuntimeError(f"request to {path} failed: {last_error}")

    def follow_tag(self, name: str) -> FollowResult:
        """Follow one hashtag. 422 Duplicate record maps to already."""
        path = f"/api/v1/tags/{urllib.parse.quote(name, safe='')}/follow"
        response = self._request(path)
        if response.status == 200:
            return FollowResult(kind="followed", name=name)
        message: str | None = None
        if 400 <= response.status < 500:
            try:
                body = json.loads(response.body.decode("utf-8") or "{}")
                err = body.get("error") if isinstance(body, dict) else None
                if isinstance(err, str):
                    message = err
            except (ValueError, UnicodeDecodeError):
                message = None
        if response.status == 422 and message and "duplicate record" in message.lower():
            return FollowResult(kind="already", name=name, status=422, message=message)
        if 400 <= response.status < 500:
            return FollowResult(
                kind="error", name=name, status=response.status, message=message
            )
        return FollowResult(kind="error", name=name, status=response.status)


def create_mastodon_client(
    instance: str,
    token: str,
    min_delay_ms: float,
    rate_limit_buffer: int = DEFAULT_RATE_LIMIT_BUFFER,
    max_retries: int = DEFAULT_MAX_RETRIES,
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
    http_fn: HttpFn | None = None,
    now: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> MastodonClient:
    """Create a MastodonClient. Token never appears in errors."""
    return MastodonClient(
        instance=instance,
        token=token,
        min_delay_ms=min_delay_ms,
        rate_limit_buffer=rate_limit_buffer,
        max_retries=max_retries,
        request_timeout=request_timeout,
        http_fn=http_fn,
        now=now,
        sleep=sleep,
    )
