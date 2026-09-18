#!/usr/bin/env python3
"""Tests for fetch_followed_tags and fetch_trending_tags. Loopback only."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from urllib.parse import parse_qs, urlparse
from urllib.parse import urlparse as up

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sources = _load("fh_sources_remote", ROOT / "sources.py")
mock_mod = _load("fh_mock2", TESTS / "mock_mastodon.py")


class FollowedTags(unittest.TestCase):
    def test_pagination(self) -> None:
        holder: dict[str, str] = {}

        def _handler(req: object, _w: object, url: object) -> None:
            query_str = url.query if hasattr(url, "query") else ""  # type: ignore[union-attr]
            query = dict(
                q.split("=", 1) if "=" in q else (q, "")
                for q in query_str.split("&")
                if q
            )
            path = url.path if hasattr(url, "path") else ""  # type: ignore[union-attr]
            if path == "/api/v1/followed_tags":
                if query.get("max_id") == "2":
                    mock_mod.send_json(req, 200, [{"name": "bird"}])  # type: ignore[arg-type]
                else:
                    mock_mod.send_json(  # type: ignore[arg-type]
                        req,
                        200,
                        [{"name": "Cats"}, {"name": "dogs"}],
                        {
                            "Link": f'<{holder["url"]}/api/v1/followed_tags?limit=200&max_id=2>; rel="next"'
                        },
                    )
            else:
                mock_mod.send_json(req, 404, {"error": "not found"})  # type: ignore[arg-type]

        mock = mock_mod.start_mock_mastodon(_handler)
        holder["url"] = mock.url
        try:
            names = sources.fetch_followed_tags(mock.url, "test-token")
            self.assertEqual(names, ["cats", "dogs", "bird"])
            self.assertEqual(len(mock.calls), 2)
        finally:
            mock.close()

    def test_trailing_slash(self) -> None:
        mock = mock_mod.start_mock_mastodon(
            lambda req, _w, url: (
                mock_mod.send_json(req, 200, [{"name": "cats"}])
                if urlparse(url.path).path == "/api/v1/followed_tags"  # type: ignore[union-attr]
                else mock_mod.send_json(req, 404, {"error": "x"})
            )
        )
        try:
            names = sources.fetch_followed_tags(f"{mock.url}/", "test-token")
            self.assertEqual(names, ["cats"])
        finally:
            mock.close()

    def test_off_origin_rejected(self) -> None:
        mock = mock_mod.start_mock_mastodon(
            lambda req, _w, _u: mock_mod.send_json(
                req,
                200,
                [{"name": "cats"}],
                {"Link": '<https://evil.example/collect>; rel="next"'},
            )
        )
        try:
            with self.assertRaisesRegex(RuntimeError, "off instance"):
                sources.fetch_followed_tags(mock.url, "test-token")
            self.assertEqual(len(mock.calls), 1)
        finally:
            mock.close()

    def test_non_2xx_raises(self) -> None:
        mock = mock_mod.start_mock_mastodon(
            lambda req, _w, _u: mock_mod.send_json(req, 500, {"error": "boom"})
        )
        try:
            with self.assertRaises(RuntimeError):
                sources.fetch_followed_tags(mock.url, "test-token")
        finally:
            mock.close()


class TrendingTags(unittest.TestCase):
    def test_pages_until_limit(self) -> None:
        def _handler(req: object, _w: object, _url: object) -> None:
            full = req.path  # type: ignore[attr-defined]
            offset = int(parse_qs(up(full).query).get("offset", ["0"])[0])
            parsed = up(full)
            if parsed.path == "/api/v1/trends/tags":
                tags = [{"name": f"tag{offset + i}"} for i in range(20)]
                mock_mod.send_json(req, 200, tags)  # type: ignore[arg-type]
            else:
                mock_mod.send_json(req, 404, {"error": "not found"})  # type: ignore[arg-type]

        mock = mock_mod.start_mock_mastodon(_handler)
        try:
            names = sources.fetch_trending_tags(mock.url, 25)
            self.assertEqual(len(names), 25)
            self.assertEqual(names[0], "tag0")
            self.assertEqual(names[24], "tag24")
            self.assertEqual(len(mock.calls), 2)
        finally:
            mock.close()

    def test_stops_on_empty(self) -> None:
        def _handler(req: object, _w: object, _url: object) -> None:
            full = req.path  # type: ignore[attr-defined]
            parsed = up(full)
            if parsed.path == "/api/v1/trends/tags":
                offset = int(parse_qs(parsed.query).get("offset", ["0"])[0])
                if offset == 0:
                    mock_mod.send_json(req, 200, [{"name": "only"}])  # type: ignore[arg-type]
                else:
                    mock_mod.send_json(req, 200, [])  # type: ignore[arg-type]
            else:
                mock_mod.send_json(req, 404, {"error": "not found"})  # type: ignore[arg-type]

        mock = mock_mod.start_mock_mastodon(_handler)
        try:
            names = sources.fetch_trending_tags(mock.url, 100)
            self.assertEqual(names, ["only"])
        finally:
            mock.close()


if __name__ == "__main__":
    unittest.main()
