#!/usr/bin/env python3
"""Tag sources for the Mastodon follow-hashtags importer.

Pure helpers (normalize, parse, merge) plus HTTP fetchers for
followed_tags and trending tags. HTTP uses stdlib urllib.

Run:  python importers/mastodon/follow-hashtags/follow_hashtags.py --help
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

MAX_TAG_LENGTH = 30
MAX_FOLLOWED_PAGES = 100
REQUEST_TIMEOUT = 30

_WHITESPACE_RE = re.compile(r"\s")
_NEXT_REL_RE = re.compile(r"""^rel\s*=\s*"?next"?$""", re.IGNORECASE)


@dataclass
class SkippedTag:
    raw: str
    reason: str


@dataclass
class SourceResult:
    tags: list[str]
    skipped: list[SkippedTag]


def normalize_tag(raw: str) -> tuple[bool, str]:
    """Return (True, name) or (False, reason). Strips # and lowercases."""
    name = raw.strip()
    while name.startswith("#"):
        name = name[1:]
    name = name.lower()
    if not name:
        return (False, "empty after normalization")
    if _WHITESPACE_RE.search(name):
        return (False, "contains whitespace")
    if len(name) > MAX_TAG_LENGTH:
        return (False, f"longer than {MAX_TAG_LENGTH} chars")
    return (True, name)


def parse_tag_list(text: str) -> SourceResult:
    """Parse one-hashtag-per-line text. Comments start with // ; or '# '."""
    tags: list[str] = []
    skipped: list[SkippedTag] = []
    seen: set[str] = set()
    for line in text.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        if trimmed.startswith(("//", ";")):
            continue
        if len(trimmed) > 1 and trimmed.startswith("#") and trimmed[1] in (" ", "\t"):
            continue
        ok, value = normalize_tag(trimmed)
        if not ok:
            skipped.append(SkippedTag(raw=line, reason=value))
            continue
        if value not in seen:
            seen.add(value)
            tags.append(value)
    return SourceResult(tags=tags, skipped=skipped)


def read_tags_from_file(path: str) -> SourceResult:
    """Read a tag list file and parse it."""
    with open(path, encoding="utf-8") as fh:
        return parse_tag_list(fh.read())


def parse_next_link(link_header: str | None) -> str | None:
    """Extract rel=next URL from an HTTP Link header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        sections = part.split(";")
        if not sections:
            continue
        match = re.match(r"^\s*<([^>]+)>\s*$", sections[0].strip())
        if not match:
            continue
        rels = [s.strip() for s in sections[1:]]
        if any(_NEXT_REL_RE.match(r) for r in rels):
            return match.group(1)
    return None


def _collect_names(payload: object) -> list[str]:
    if not isinstance(payload, list):
        return []
    names: list[str] = []
    for item in payload:
        if isinstance(item, dict):
            raw = item.get("name")
            if isinstance(raw, str):
                ok, value = normalize_tag(raw)
                if ok:
                    names.append(value)
    return names


def _fetch_json(url: str, token: str | None) -> tuple[object, dict[str, str]]:
    import urllib.error
    from contextlib import suppress

    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            status = resp.status
            if status < 200 or status >= 300:
                raise RuntimeError(f"request to {url} failed with status {status}")
            body = resp.read().decode("utf-8")
            link = resp.headers.get("Link")
            return json.loads(body), {"link": link or ""}
    except urllib.error.HTTPError as exc:
        try:
            raise RuntimeError(
                f"request to {url} failed with status {exc.code}"
            ) from exc
        finally:
            with suppress(OSError):
                exc.close()


def _assert_same_origin(next_url: str, base: str) -> str:
    resolved = urllib.parse.urljoin(base, next_url)
    base_origin = urllib.parse.urlparse(base).netloc.lower()
    next_origin = urllib.parse.urlparse(resolved).netloc.lower()
    base_scheme = urllib.parse.urlparse(base).scheme.lower()
    next_scheme = urllib.parse.urlparse(resolved).scheme.lower()
    if (next_origin != base_origin) or (next_scheme != base_scheme):
        raise RuntimeError(
            f"refusing to follow pagination link off instance ({resolved})"
        )
    return resolved


def fetch_followed_tags(instance: str, token: str) -> list[str]:
    """Fetch all followed_tags names, following Link rel=next pages."""
    base = instance.rstrip("/")
    names: list[str] = []
    next_url: str | None = f"{base}/api/v1/followed_tags?limit=200"
    pages = 0
    while next_url:
        pages += 1
        if pages > MAX_FOLLOWED_PAGES:
            raise RuntimeError(
                f"fetch_followed_tags exceeded {MAX_FOLLOWED_PAGES} pages"
            )
        payload, headers = _fetch_json(next_url, token)
        names.extend(_collect_names(payload))
        link = parse_next_link(headers.get("link") or None)
        next_url = _assert_same_origin(link, base) if link else None
    return names


def fetch_trending_tags(
    instance: str, limit: int, token: str | None = None
) -> list[str]:
    """Page trends/tags until limit reached or an empty page appears."""
    base = instance.rstrip("/")
    names: list[str] = []
    offset = 0
    while len(names) < limit:
        url = f"{base}/api/v1/trends/tags?limit=20&offset={offset}"
        payload, _ = _fetch_json(url, token)
        page = _collect_names(payload)
        names.extend(page)
        if not page:
            break
        offset += len(page)
    return names[:limit]


def merge_tag_lists(*lists: list[str]) -> list[str]:
    """Dedupe tag lists keeping first occurrence order."""
    seen: set[str] = set()
    out: list[str] = []
    for items in lists:
        for name in items:
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out
