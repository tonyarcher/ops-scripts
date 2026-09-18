#!/usr/bin/env python3
"""Tests for mastodon_client.py against a loopback mock. No external network."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import UTC
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


mastodon_client = _load("fh_client3", ROOT / "mastodon_client.py")
mock_mod = _load("fh_mock", TESTS / "mock_mastodon.py")


class FakeClock:
    def __init__(self, start: float = 0) -> None:
        self.current = start
        self.sleeps: list[float] = []

    def now(self) -> float:
        """Return fake time in ms."""
        return self.current

    def sleep(self, ms: float) -> None:
        """Record sleep and advance time."""
        self.sleeps.append(ms)
        self.current += ms


def _client(url: str, clock: FakeClock, **kwargs: object) -> object:
    return mastodon_client.create_mastodon_client(
        instance=url,
        token="test-token",
        min_delay_ms=0,
        now=clock.now,
        sleep=clock.sleep,
        **kwargs,  # type: ignore[arg-type]
    )


class ClientTests(unittest.TestCase):
    def test_200_follow_sends_bearer(self) -> None:
        seen: dict[str, str] = {}

        def _handler(req: object, _wfile: object, _url: object) -> None:
            seen["auth"] = req.headers.get("Authorization", "")  # type: ignore[attr-defined]
            mock_mod.send_json(req, 200, {"name": "cats"})  # type: ignore[arg-type]

        mock = mock_mod.start_mock_mastodon(_handler)
        try:
            client = _client(mock.url, FakeClock())
            result = client.follow_tag("cats")  # type: ignore[attr-defined]
            self.assertEqual(result.kind, "followed")
            self.assertEqual(result.name, "cats")
            self.assertEqual(seen.get("auth"), "Bearer test-token")
            self.assertEqual(len(mock.calls), 1)
            self.assertEqual(mock.calls[0].path, "/api/v1/tags/cats/follow")
        finally:
            mock.close()

    def test_422_duplicate_is_already(self) -> None:
        mock = mock_mod.start_mock_mastodon(
            lambda req, _w, _u: mock_mod.send_json(
                req, 422, {"error": "Duplicate record"}
            )
        )
        try:
            result = _client(mock.url, FakeClock()).follow_tag("cats")  # type: ignore[attr-defined]
            self.assertEqual(result.kind, "already")
            self.assertEqual(result.status, 422)
        finally:
            mock.close()

    def test_422_validation_is_error(self) -> None:
        mock = mock_mod.start_mock_mastodon(
            lambda req, _w, _u: mock_mod.send_json(
                req, 422, {"error": "Validation failed"}
            )
        )
        try:
            result = _client(mock.url, FakeClock()).follow_tag("cats")  # type: ignore[attr-defined]
            self.assertEqual(result.kind, "error")
            self.assertEqual(result.status, 422)
            self.assertEqual(result.message, "Validation failed")
        finally:
            mock.close()

    def test_401_raises_fatal(self) -> None:
        mock = mock_mod.start_mock_mastodon(
            lambda req, _w, _u: mock_mod.send_json(req, 401, {"error": "unauthorized"})
        )
        try:
            client = _client(mock.url, FakeClock())
            with self.assertRaises(mastodon_client.FatalApiError) as ctx:
                client.follow_tag("cats")  # type: ignore[attr-defined]
            self.assertEqual(ctx.exception.status, 401)
            self.assertNotIn("test-token", str(ctx.exception))
        finally:
            mock.close()

    def test_403_raises_fatal(self) -> None:
        mock = mock_mod.start_mock_mastodon(
            lambda req, _w, _u: mock_mod.send_json(req, 403, {"error": "forbidden"})
        )
        try:
            with self.assertRaises(mastodon_client.FatalApiError):
                _client(mock.url, FakeClock()).follow_tag("cats")  # type: ignore[attr-defined]
        finally:
            mock.close()

    def test_500_then_200_retries(self) -> None:
        clock = FakeClock()
        calls = {"n": 0}

        def _handler(req: object, _w: object, _u: object) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                mock_mod.send_json(req, 500, {"error": "boom"})  # type: ignore[arg-type]
            else:
                mock_mod.send_json(req, 200, {"name": "cats"})  # type: ignore[arg-type]

        mock = mock_mod.start_mock_mastodon(_handler)
        try:
            client = _client(mock.url, clock)
            result = client.follow_tag("cats")  # type: ignore[attr-defined]
            self.assertEqual(result.kind, "followed")
            self.assertEqual(client.request_count(), 2)  # type: ignore[attr-defined]
            self.assertGreaterEqual(len(clock.sleeps), 1)
            self.assertGreaterEqual(clock.sleeps[0], 1000)
        finally:
            mock.close()

    def test_429_retry_after(self) -> None:
        clock = FakeClock()
        calls = {"n": 0}

        def _handler(req: object, _w: object, _u: object) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                mock_mod.send_json(req, 429, {"error": "x"}, {"Retry-After": "2"})  # type: ignore[arg-type]
            else:
                mock_mod.send_json(req, 200, {"name": "cats"})  # type: ignore[arg-type]

        mock = mock_mod.start_mock_mastodon(_handler)
        try:
            result = _client(mock.url, clock).follow_tag("cats")  # type: ignore[attr-defined]
            self.assertEqual(result.kind, "followed")
            self.assertTrue(any(s >= 2000 for s in clock.sleeps))
        finally:
            mock.close()

    def test_rate_limit_remaining_zero_sleeps(self) -> None:
        clock = FakeClock()
        calls = {"n": 0}
        future_ms = 10_000
        from datetime import datetime

        reset = datetime.fromtimestamp(future_ms / 1000, tz=UTC).isoformat()

        def _handler(req: object, _w: object, _u: object) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                mock_mod.send_json(  # type: ignore[arg-type]
                    req,
                    200,
                    {"name": "cats"},
                    {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": reset},
                )
            else:
                mock_mod.send_json(req, 200, {"name": "dogs"})  # type: ignore[arg-type]

        mock = mock_mod.start_mock_mastodon(_handler)
        try:
            client = _client(mock.url, clock)
            client.follow_tag("cats")  # type: ignore[attr-defined]
            before = len(clock.sleeps)
            client.follow_tag("dogs")  # type: ignore[attr-defined]
            self.assertGreater(len(clock.sleeps), before)
            self.assertEqual(clock.sleeps[-1], future_ms + 250)
        finally:
            mock.close()

    def test_min_delay(self) -> None:
        clock = FakeClock()
        mock = mock_mod.start_mock_mastodon(
            lambda req, _w, _u: mock_mod.send_json(req, 200, {"name": "cats"})
        )
        try:
            client = mastodon_client.create_mastodon_client(
                instance=mock.url,
                token="test-token",
                min_delay_ms=1000,
                now=clock.now,
                sleep=clock.sleep,
            )
            client.follow_tag("cats")
            client.follow_tag("dogs")
            self.assertTrue(any(s >= 1000 for s in clock.sleeps))
        finally:
            mock.close()

    def test_404_is_error(self) -> None:
        mock = mock_mod.start_mock_mastodon(
            lambda req, _w, _u: mock_mod.send_json(req, 404, {"error": "not found"})
        )
        try:
            result = _client(mock.url, FakeClock()).follow_tag("cats")  # type: ignore[attr-defined]
            self.assertEqual(result.kind, "error")
            self.assertEqual(result.status, 404)
            self.assertEqual(result.message, "not found")
        finally:
            mock.close()

    def test_request_count_counts_retries(self) -> None:
        clock = FakeClock()
        calls = {"n": 0}

        def _handler(req: object, _w: object, _u: object) -> None:
            calls["n"] += 1
            if calls["n"] <= 2:
                mock_mod.send_json(req, 500, {"error": "boom"})  # type: ignore[arg-type]
            else:
                mock_mod.send_json(req, 200, {"name": "cats"})  # type: ignore[arg-type]

        mock = mock_mod.start_mock_mastodon(_handler)
        try:
            client = _client(mock.url, clock)
            result = client.follow_tag("cats")  # type: ignore[attr-defined]
            self.assertEqual(result.kind, "followed")
            self.assertEqual(client.request_count(), 3)  # type: ignore[attr-defined]
        finally:
            mock.close()

    def test_slash_in_tag_is_percent_encoded(self) -> None:
        seen: list[str] = []

        def _http(url: str, _headers: object, _timeout: float) -> object:
            seen.append(url)
            return mastodon_client._HttpResponse(status=200, headers={}, body=b"{}")

        client = mastodon_client.create_mastodon_client(
            instance="https://example.social",
            token="t",
            min_delay_ms=0,
            http_fn=_http,  # type: ignore[arg-type]
            now=FakeClock().now,
            sleep=FakeClock().sleep,
        )
        result = client.follow_tag("a/b")
        self.assertEqual(result.kind, "followed")
        self.assertIn("/api/v1/tags/a%2Fb/follow", seen[0])
        self.assertNotIn("/api/v1/tags/a/b/follow", seen[0])

    def test_max_retries_zero_still_attempts_once(self) -> None:
        calls = {"n": 0}

        def _http(url: str, _headers: object, _timeout: float) -> object:
            calls["n"] += 1
            return mastodon_client._HttpResponse(status=200, headers={}, body=b"{}")

        client = mastodon_client.create_mastodon_client(
            instance="https://example.social",
            token="t",
            min_delay_ms=0,
            max_retries=0,
            http_fn=_http,  # type: ignore[arg-type]
            now=FakeClock().now,
            sleep=FakeClock().sleep,
        )
        result = client.follow_tag("cats")
        self.assertEqual(result.kind, "followed")
        self.assertEqual(calls["n"], 1)


if __name__ == "__main__":
    unittest.main()
