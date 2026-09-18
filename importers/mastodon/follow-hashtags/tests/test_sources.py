#!/usr/bin/env python3
"""Tests for sources.py pure helpers. No network."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("fh_sources", ROOT / "sources.py")
assert _spec is not None and _spec.loader is not None
sources = importlib.util.module_from_spec(_spec)
sys.modules["fh_sources"] = sources
_spec.loader.exec_module(sources)


class NormalizeTag(unittest.TestCase):
    def test_strips_hash_and_lowercases(self) -> None:
        self.assertEqual(sources.normalize_tag("#Dogs"), (True, "dogs"))

    def test_trims_whitespace(self) -> None:
        self.assertEqual(sources.normalize_tag("  OpenSource  "), (True, "opensource"))

    def test_rejects_empty(self) -> None:
        self.assertFalse(sources.normalize_tag("")[0])
        self.assertFalse(sources.normalize_tag("   ")[0])
        self.assertFalse(sources.normalize_tag("#")[0])

    def test_rejects_too_long(self) -> None:
        ok, _ = sources.normalize_tag("a" * (sources.MAX_TAG_LENGTH + 1))
        self.assertFalse(ok)

    def test_rejects_whitespace(self) -> None:
        self.assertFalse(sources.normalize_tag("two words")[0])
        self.assertFalse(sources.normalize_tag("cats\tdogs")[0])

    def test_accepts_unicode_and_underscore(self) -> None:
        self.assertEqual(sources.normalize_tag("café"), (True, "café"))
        self.assertEqual(sources.normalize_tag("snake_case"), (True, "snake_case"))


class ParseTagList(unittest.TestCase):
    def test_skips_comments_and_blanks(self) -> None:
        text = "// x\r\n; y\r\n# note\r\n\r\n  \r\n#cats\r\ncats"
        result = sources.parse_tag_list(text)
        self.assertEqual(result.tags, ["cats"])
        self.assertEqual(result.skipped, [])

    def test_dedupes_by_normalized(self) -> None:
        result = sources.parse_tag_list("Cats\ncats\n#CATS\nDogs")
        self.assertEqual(result.tags, ["cats", "dogs"])

    def test_collects_skipped(self) -> None:
        result = sources.parse_tag_list("valid\n\nbad tag\n")
        self.assertEqual(result.tags, ["valid"])
        self.assertEqual(len(result.skipped), 1)
        self.assertEqual(result.skipped[0].raw, "bad tag")
        self.assertTrue(len(result.skipped[0].reason) > 0)


class MergeAndLink(unittest.TestCase):
    def test_merge_dedupes(self) -> None:
        self.assertEqual(
            sources.merge_tag_lists(["a", "b"], ["b", "c"], ["a"]), ["a", "b", "c"]
        )

    def test_parse_next_link(self) -> None:
        header = (
            '<https://x/api/v1/followed_tags?limit=200&max_id=2>; rel="next", '
            '<https://x/api/v1/followed_tags?limit=200&min_id=1>; rel="prev"'
        )
        self.assertEqual(
            sources.parse_next_link(header),
            "https://x/api/v1/followed_tags?limit=200&max_id=2",
        )

    def test_parse_next_link_none(self) -> None:
        self.assertIsNone(sources.parse_next_link('<https://x/page>; rel="prev"'))
        self.assertIsNone(sources.parse_next_link(None))
        self.assertIsNone(sources.parse_next_link(""))


if __name__ == "__main__":
    unittest.main()
