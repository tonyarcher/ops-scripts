#!/usr/bin/env python3
"""Offline tests for android-tv debloat guards. No adb."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import debloat  # noqa: E402


class DebloatGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = debloat.load_catalog(ROOT / "packages.json")

    def test_batches_are_at_most_ten(self) -> None:
        for batch in self.catalog["batches"]:
            self.assertLessEqual(len(batch["packages"]), debloat.MAX_BATCH, batch["id"])

    def test_no_batch_package_is_protected(self) -> None:
        for batch in self.catalog["batches"]:
            for row in batch["packages"]:
                self.assertFalse(
                    debloat.is_protected(row["id"], self.catalog),
                    f"{row['id']} in {batch['id']} is protected",
                )

    def test_keyboard_substring_is_protected(self) -> None:
        self.assertTrue(
            debloat.is_protected("com.example.inputmethod.latin", self.catalog)
        )

    def test_fused_location_is_protected(self) -> None:
        self.assertTrue(debloat.is_protected("com.android.location.fused", self.catalog))

    def test_youtube_is_protected(self) -> None:
        self.assertTrue(
            debloat.is_protected("com.google.android.youtube.tv", self.catalog)
        )

    def test_apply_batch_rejects_oversized(self) -> None:
        fat = {
            "id": "too-big",
            "packages": [{"id": f"pkg.{i}", "why": "x"} for i in range(11)],
        }
        with self.assertRaises(SystemExit):
            debloat.apply_batch(self.catalog, fat)

    def test_apply_batch_accepts_factory_leftovers(self) -> None:
        batch = debloat.batch_by_id(self.catalog, "factory-leftovers")
        rows = debloat.apply_batch(self.catalog, batch)
        self.assertEqual(len(rows), 10)

    def test_unknown_batch_exits(self) -> None:
        with self.assertRaises(SystemExit):
            debloat.batch_by_id(self.catalog, "nope")

    def test_list_runs_offline(self) -> None:
        debloat.cmd_list(self.catalog)


if __name__ == "__main__":
    unittest.main()
