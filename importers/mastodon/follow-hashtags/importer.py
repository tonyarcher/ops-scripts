#!/usr/bin/env python3
"""Batch runner for the follow-hashtags importer.

Skips done/already/invalid rows, honors max and retry_failed,
and aborts on FatalApiError. Uses stdlib only.

Run:  python importers/mastodon/follow-hashtags/follow_hashtags.py --help
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class FollowResultLike(Protocol):
    kind: str
    message: str | None


class MastodonClientLike(Protocol):
    def follow_tag(self, name: str) -> FollowResultLike: ...


class TagRowLike(Protocol):
    status: str


class ProgressStoreLike(Protocol):
    def get(self, name: str) -> TagRowLike | None: ...
    def upsert(self, name: str, status: str, error: str | None = ...) -> None: ...


@dataclass
class ImportConfig:
    apply: bool
    batch_size: int = 25
    max: int | None = None
    retry_failed: bool = False


@dataclass
class ImportSummary:
    followed: int = 0
    already: int = 0
    skipped: int = 0
    failed: int = 0
    dry_run: int = 0
    invalid: int = 0
    duration_ms: int = 0


def _is_skipped(status: str, retry_failed: bool) -> bool:
    """Return True when a stored row means skip this tag."""
    if status in ("done", "already", "invalid"):
        return True
    return status == "error" and not retry_failed


def _select_work(
    tags: list[str],
    store: ProgressStoreLike,
    config: ImportConfig,
    summary: ImportSummary,
) -> list[str]:
    """Filter tags to fresh work, counting skips in summary."""
    work: list[str] = []
    for name in tags:
        row = store.get(name)
        if row is not None and _is_skipped(row.status, config.retry_failed):
            summary.skipped += 1
            continue
        work.append(name)
    return work


def _apply_max(
    work: list[str], config: ImportConfig, summary: ImportSummary
) -> list[str]:
    """Cap work at config.max, counting the remainder as skipped."""
    if config.max is not None and config.max >= 0 and len(work) > config.max:
        summary.skipped += len(work) - config.max
        return work[: config.max]
    return work


def _process_one(
    name: str,
    config: ImportConfig,
    client: MastodonClientLike,
    store: ProgressStoreLike,
    summary: ImportSummary,
    emit: Callable[[str], None],
) -> None:
    """Process a single tag in apply or dry-run mode."""
    if not config.apply:
        emit(f"dry-run would follow #{name}")
        summary.dry_run += 1
        return
    try:
        result = client.follow_tag(name)
    except Exception as exc:
        if any(base.__name__ == "FatalApiError" for base in type(exc).__mro__):
            raise
        store.upsert(name, "error", str(exc))
        summary.failed += 1
        return
    if result.kind == "followed":
        store.upsert(name, "done")
        summary.followed += 1
    elif result.kind == "already":
        store.upsert(name, "already")
        summary.already += 1
    else:
        store.upsert(name, "error", result.message)
        summary.failed += 1


def run_importer(
    config: ImportConfig,
    tags: list[str],
    invalid: list[dict[str, str]],
    client: MastodonClientLike,
    store: ProgressStoreLike,
    log: Callable[[str], None] | None = None,
    now: Callable[[], float] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> ImportSummary:
    """Run the import loop. Returns a summary. Reraises fatal auth errors."""
    emit = log or (lambda _msg: None)
    clock = now or (lambda: time.time() * 1000)
    stop = should_stop or (lambda: False)
    start = clock()
    summary = ImportSummary(invalid=len(invalid))
    if config.apply:
        for item in invalid:
            store.upsert(item["raw"], "invalid", item["reason"])
    work = _apply_max(_select_work(tags, store, config, summary), config, summary)
    total = len(work)
    for processed, name in enumerate(work, start=1):
        if stop():
            break
        _process_one(name, config, client, store, summary, emit)
        if processed % config.batch_size == 0:
            emit(
                f"batch {processed}/{total} followed={summary.followed} "
                f"already={summary.already} failed={summary.failed} "
                f"dryRun={summary.dry_run}"
            )
    summary.duration_ms = int(clock() - start)
    return summary
