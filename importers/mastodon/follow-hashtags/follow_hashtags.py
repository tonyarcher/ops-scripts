#!/usr/bin/env python3
"""Bulk-follow Mastodon hashtags from a file, another account, or trends.

Default dry-run. Pass --apply to POST.

Run:
  python importers/mastodon/follow-hashtags/follow_hashtags.py --file tags.txt
  python importers/mastodon/follow-hashtags/follow_hashtags.py --help

Env: MASTODON_INSTANCE, MASTODON_ACCESS_TOKEN,
     MASTODON_SOURCE_INSTANCE, MASTODON_SOURCE_TOKEN

Token needs write:follows (and read:follows to copy source follows).
Never commit tokens. State in tmp/follow-hashtags.db.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from importer import ImportConfig, ImportSummary, run_importer
from mastodon_client import FollowResult, MastodonClient, create_mastodon_client
from sources import (
    fetch_followed_tags,
    fetch_trending_tags,
    merge_tag_lists,
    read_tags_from_file,
)
from state import open_progress_store

USAGE_EXAMPLES = """examples:
  python follow_hashtags.py --file sample-tags.txt
  python follow_hashtags.py --instance https://example.social --file sample-tags.txt --apply
"""


@dataclass
class CliOptions:
    instance: str | None
    token: str | None
    file: str | None
    source_instance: str | None
    source_token: str | None
    trends: int | None
    delay_ms: int
    max: int | None
    apply: bool
    state: str
    retry_failed: bool
    batch_size: int


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    p = argparse.ArgumentParser(
        description="Bulk-follow Mastodon hashtags (dry-run default)."
    )
    p.add_argument("--instance", default=os.environ.get("MASTODON_INSTANCE"))
    p.add_argument("--token", default=os.environ.get("MASTODON_ACCESS_TOKEN"))
    p.add_argument("--file", default=None)
    p.add_argument(
        "--source-instance", default=os.environ.get("MASTODON_SOURCE_INSTANCE")
    )
    p.add_argument("--source-token", default=os.environ.get("MASTODON_SOURCE_TOKEN"))
    p.add_argument("--trends", type=int, default=None)
    p.add_argument("--delay-ms", type=int, default=1500)
    p.add_argument("--max", type=int, default=None)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--state", default="tmp/follow-hashtags.db")
    p.add_argument("--retry-failed", action="store_true")
    p.add_argument("--batch-size", type=int, default=25)
    return p


def parse_cli(argv: list[str] | None = None) -> CliOptions:
    """Parse argv into CliOptions."""
    args = build_parser().parse_args(argv)
    return CliOptions(
        instance=args.instance,
        token=args.token,
        file=args.file,
        source_instance=args.source_instance,
        source_token=args.source_token,
        trends=args.trends,
        delay_ms=args.delay_ms,
        max=args.max,
        apply=bool(args.apply),
        state=args.state,
        retry_failed=bool(args.retry_failed),
        batch_size=args.batch_size,
    )


def validate_cli(opts: CliOptions) -> str | None:
    """Return an error string, or None when options are valid."""
    if not opts.file and not opts.source_instance and opts.trends is None:
        return "need at least one of --file, --source-instance, --trends"
    if opts.apply and (not opts.instance or not opts.token):
        return "--apply requires --instance and --token"
    if opts.source_instance and not opts.source_token:
        return "--source-instance requires --source-token"
    if opts.trends is not None and not opts.instance:
        return "--trends requires --instance"
    if opts.trends is not None and opts.trends < 1:
        return "--trends must be a positive integer"
    if opts.delay_ms < 0:
        return "--delay-ms must be an integer >= 0"
    if opts.batch_size < 1:
        return "--batch-size must be an integer >= 1"
    if opts.max is not None and opts.max < 0:
        return "--max must be an integer >= 0"
    return None


def print_summary(summary: ImportSummary) -> None:
    """Print a human-readable import summary."""
    print("summary:")
    print(f"  followed:   {summary.followed}")
    print(f"  already:    {summary.already}")
    print(f"  skipped:    {summary.skipped}")
    print(f"  failed:     {summary.failed}")
    print(f"  dryRun:     {summary.dry_run}")
    print(f"  invalid:    {summary.invalid}")
    print(f"  durationMs: {summary.duration_ms}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    opts = parse_cli(argv)
    error = validate_cli(opts)
    if error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    tag_lists: list[list[str]] = []
    invalid: list[dict[str, str]] = []
    if opts.file:
        result = read_tags_from_file(opts.file)
        tag_lists.append(result.tags)
        invalid.extend([{"raw": s.raw, "reason": s.reason} for s in result.skipped])
    if opts.source_instance:
        followed = fetch_followed_tags(opts.source_instance, opts.source_token or "")
        tag_lists.append(followed)
    if opts.trends is not None:
        trending = fetch_trending_tags(opts.instance or "", opts.trends, opts.token)
        tag_lists.append(trending)
    tags = merge_tag_lists(*tag_lists)
    print(f"loaded {len(tags)} tags, skipped {len(invalid)} invalid")
    store = open_progress_store(opts.state)
    stopped = False

    def _on_sigint(_signum: int, _frame: object) -> None:
        nonlocal stopped
        stopped = True

    old_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, _on_sigint)
    try:
        if opts.apply:
            client: MastodonClient | _DryRunClient = create_mastodon_client(
                instance=opts.instance or "",
                token=opts.token or "",
                min_delay_ms=float(opts.delay_ms),
            )
        else:
            client = _DryRunClient()
        summary = run_importer(
            config=ImportConfig(
                apply=opts.apply,
                max=opts.max,
                retry_failed=opts.retry_failed,
                batch_size=opts.batch_size,
            ),
            tags=tags,
            invalid=invalid,
            client=client,
            store=store,
            log=print,
            should_stop=lambda: stopped,
        )
        print_summary(summary)
        if stopped:
            return 130
        if summary.failed > 0:
            return 1
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI top level converts any failure to exit 1
        if stopped:
            return 130
        print(f"fatal: {exc}", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGINT, old_handler)
        store.close()


class _DryRunClient:
    """Placeholder that fails if follow_tag is called in dry-run."""

    def follow_tag(self, _name: str) -> FollowResult:
        """Raise because dry-run must never POST."""
        raise RuntimeError("follow_tag called in dry-run mode")

    def request_count(self) -> int:
        """Return zero for dry-run."""
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
