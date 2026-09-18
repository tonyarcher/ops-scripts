#!/usr/bin/env python3
"""Tests for importer.py with a fake client. No network."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


state = _load("fh_state2", "state.py")
mastodon_client = _load("fh_client2", "mastodon_client.py")
importer = _load("fh_importer", "importer.py")


class FakeClient:
    def __init__(self, handler: Callable[[str], object]) -> None:
        self._handler = handler
        self.calls: list[str] = []

    def follow_tag(self, name: str) -> object:
        """Record the call and delegate to the handler."""
        self.calls.append(name)
        return self._handler(name)

    def request_count(self) -> int:
        """Return call count."""
        return len(self.calls)


def _followed(name: str) -> object:
    return mastodon_client.FollowResult(kind="followed", name=name)


class ImporterTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self) -> None:
        store = state.open_progress_store(":memory:")
        try:

            def _boom(name: str) -> object:
                raise AssertionError("follow_tag should not be called in dry-run")

            client = FakeClient(_boom)
            summary = importer.run_importer(
                config=importer.ImportConfig(apply=False),
                tags=["cats", "dogs"],
                invalid=[{"raw": "bad tag", "reason": "contains whitespace"}],
                client=client,  # type: ignore[arg-type]
                store=store,  # type: ignore[arg-type]
            )
            self.assertEqual(client.calls, [])
            self.assertEqual(summary.dry_run, 2)
            self.assertEqual(summary.followed, 0)
            self.assertEqual(store.summary().done, 0)
            self.assertEqual(store.summary().invalid, 0)
        finally:
            store.close()

    def test_apply_records_done(self) -> None:
        store = state.open_progress_store(":memory:")
        try:
            client = FakeClient(_followed)
            summary = importer.run_importer(
                config=importer.ImportConfig(apply=True),
                tags=["cats", "dogs"],
                invalid=[],
                client=client,  # type: ignore[arg-type]
                store=store,  # type: ignore[arg-type]
            )
            self.assertEqual(client.calls, ["cats", "dogs"])
            self.assertEqual(summary.followed, 2)
            self.assertEqual(store.summary().done, 2)
        finally:
            store.close()

    def test_resume_skips_done(self) -> None:
        store = state.open_progress_store(":memory:")
        try:
            store.upsert("cats", "done")
            store.upsert("dogs", "already")
            client = FakeClient(_followed)
            summary = importer.run_importer(
                config=importer.ImportConfig(apply=True),
                tags=["cats", "dogs", "birds"],
                invalid=[],
                client=client,  # type: ignore[arg-type]
                store=store,  # type: ignore[arg-type]
            )
            self.assertEqual(client.calls, ["birds"])
            self.assertEqual(summary.followed, 1)
            self.assertGreaterEqual(summary.skipped, 2)
        finally:
            store.close()

    def test_retry_failed_flag(self) -> None:
        store = state.open_progress_store(":memory:")
        try:
            store.upsert("cats", "error", "previous failure")
            no_retry = importer.run_importer(
                config=importer.ImportConfig(apply=True, retry_failed=False),
                tags=["cats"],
                invalid=[],
                client=FakeClient(_followed),  # type: ignore[arg-type]
                store=store,  # type: ignore[arg-type]
            )
            self.assertEqual(no_retry.followed, 0)
            self.assertEqual(no_retry.skipped, 1)
            retry = importer.run_importer(
                config=importer.ImportConfig(apply=True, retry_failed=True),
                tags=["cats"],
                invalid=[],
                client=FakeClient(_followed),  # type: ignore[arg-type]
                store=store,  # type: ignore[arg-type]
            )
            self.assertEqual(retry.followed, 1)
            row = store.get("cats")
            assert row is not None
            self.assertEqual(row.status, "done")
        finally:
            store.close()

    def test_max_limits(self) -> None:
        store = state.open_progress_store(":memory:")
        try:
            client = FakeClient(_followed)
            summary = importer.run_importer(
                config=importer.ImportConfig(apply=True, max=2),
                tags=["a", "b", "c", "d", "e"],
                invalid=[],
                client=client,  # type: ignore[arg-type]
                store=store,  # type: ignore[arg-type]
            )
            self.assertEqual(client.calls, ["a", "b"])
            self.assertEqual(summary.followed, 2)
            self.assertEqual(summary.skipped, 3)
        finally:
            store.close()

    def test_invalid_recorded(self) -> None:
        store = state.open_progress_store(":memory:")
        try:
            summary = importer.run_importer(
                config=importer.ImportConfig(apply=True),
                tags=["cats"],
                invalid=[{"raw": "bad tag", "reason": "contains whitespace"}],
                client=FakeClient(_followed),  # type: ignore[arg-type]
                store=store,  # type: ignore[arg-type]
            )
            self.assertEqual(summary.invalid, 1)
            row = store.get("bad tag")
            assert row is not None
            self.assertEqual(row.status, "invalid")
            self.assertEqual(row.last_error, "contains whitespace")
        finally:
            store.close()

    def test_fatal_aborts(self) -> None:
        store = state.open_progress_store(":memory:")
        try:

            def _fatal(name: str) -> object:
                raise mastodon_client.FatalApiError("unauthorized (401)", 401)

            with self.assertRaises(mastodon_client.FatalApiError):
                importer.run_importer(
                    config=importer.ImportConfig(apply=True),
                    tags=["cats"],
                    invalid=[],
                    client=FakeClient(_fatal),  # type: ignore[arg-type]
                    store=store,  # type: ignore[arg-type]
                )
        finally:
            store.close()

    def test_fatal_subclass_aborts(self) -> None:
        store = state.open_progress_store(":memory:")
        try:

            class SubFatal(mastodon_client.FatalApiError):
                pass

            def _fatal(name: str) -> object:
                raise SubFatal("forbidden (403)", 403)

            with self.assertRaises(mastodon_client.FatalApiError):
                importer.run_importer(
                    config=importer.ImportConfig(apply=True),
                    tags=["cats"],
                    invalid=[],
                    client=FakeClient(_fatal),  # type: ignore[arg-type]
                    store=store,  # type: ignore[arg-type]
                )
        finally:
            store.close()

    def test_should_stop(self) -> None:
        store = state.open_progress_store(":memory:")
        try:
            client = FakeClient(_followed)
            summary = importer.run_importer(
                config=importer.ImportConfig(apply=True),
                tags=["a", "b", "c"],
                invalid=[],
                client=client,  # type: ignore[arg-type]
                store=store,  # type: ignore[arg-type]
                should_stop=lambda: len(client.calls) >= 1,
            )
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(summary.followed, 1)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
