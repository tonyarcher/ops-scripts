#!/usr/bin/env python3
"""Tests for state.py. No network."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("fh_state", ROOT / "state.py")
assert _spec is not None and _spec.loader is not None
state = importlib.util.module_from_spec(_spec)
sys.modules["fh_state"] = state
_spec.loader.exec_module(state)


class MemoryStore(unittest.TestCase):
    def test_upsert_get_summary(self) -> None:
        store = state.open_progress_store(":memory:")
        try:
            self.assertIsNone(store.get("cats"))
            store.upsert("cats", "pending")
            row = store.get("cats")
            assert row is not None
            self.assertEqual(row.name, "cats")
            self.assertEqual(row.status, "pending")
            self.assertEqual(row.attempts, 1)
            self.assertIsNone(row.last_error)
            store.upsert("cats", "done")
            row2 = store.get("cats")
            assert row2 is not None
            self.assertEqual(row2.status, "done")
            self.assertEqual(row2.attempts, 2)
            store.upsert("dogs", "error", "boom")
            row3 = store.get("dogs")
            assert row3 is not None
            self.assertEqual(row3.status, "error")
            self.assertEqual(row3.last_error, "boom")
            summary = store.summary()
            self.assertEqual(summary.done, 1)
            self.assertEqual(summary.error, 1)
            self.assertEqual(summary.pending, 0)
            self.assertEqual(summary.already, 0)
            self.assertEqual(summary.invalid, 0)
        finally:
            store.close()

    def test_file_persists(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db_path = str(Path(raw) / "test.db")
            store = state.open_progress_store(db_path)
            store.upsert("cats", "done")
            store.close()
            reopened = state.open_progress_store(db_path)
            try:
                row = reopened.get("cats")
                assert row is not None
                self.assertEqual(row.status, "done")
                self.assertEqual(reopened.summary().done, 1)
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
