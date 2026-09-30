#!/usr/bin/env python3
"""The tracked opencode config must match the one opencode actually loads.

dotfiles/opencode/opencode.json is a recovery copy, not a live symlink, so it
drifts silently the next time anything edits ~/.config/opencode/opencode.json.
This fails loudly instead.

Run:  python dotfiles/tests/test_config_sync.py
Skip: set SKIP_CONFIG_SYNC=1 (CI, or a machine with no opencode config).
"""

from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
TRACKED = REPO / "dotfiles" / "opencode" / "opencode.json"
LIVE = Path.home() / ".config" / "opencode" / "opencode.json"

# A credential appears either as a JSON value under a key, or glued to a prefix.
# Token characters exclude "-" so ordinary hyphenated words cannot match.
SECRET_PATTERNS: dict[str, str] = {
    "api key": r'api[_-]?key"?\s*[:=]\s*"?[\w]{16,}',
    "password": r'passw\w*"?\s*[:=]\s*"?[\w]{12,}',
    "bearer": r"bearer\W{0,4}[\w]{16,}",
    "github token": r"gh[pousr]_\w{16,}",
    "secret key": r"\bsk-[A-Za-z0-9]{16,}",
}

# Every shape each pattern must catch, so a broken quantifier fails a test
# rather than passing vacuously.
SECRET_SHAPES: dict[str, tuple[str, ...]] = {
    "api key": (
        '{"api_key": "abcdefghijklmnop1234"}',
        '{"API-KEY":"abcdefghijklmnop"}',
    ),
    "password": ('{"password": "hunter2hunter2"}', '{"password":"supersecretvalue1"}'),
    "bearer": (
        '"bearer": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"',
        "Bearer abcdefghijklmnopqrstuvwx",
    ),
    "github token": ("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",),
    "secret key": ("sk-abcdefgh12345678ijkl",),
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def opted_out() -> bool:
    return os.environ.get("SKIP_CONFIG_SYNC") == "1"


@unittest.skipIf(opted_out(), "SKIP_CONFIG_SYNC=1")
class ConfigSync(unittest.TestCase):
    @unittest.skipUnless(LIVE.is_file(), f"no live config at {LIVE}")
    def test_tracked_matches_live(self) -> None:
        """Commit dotfiles/opencode/opencode.json after editing the live one."""
        self.assertEqual(
            load(TRACKED),
            load(LIVE),
            "dotfiles/opencode/opencode.json is stale. Copy the live config:\n"
            "  Copy-Item ~/.config/opencode/opencode.json "
            "dotfiles/opencode/opencode.json",
        )

    def test_no_secrets_in_tracked(self) -> None:
        """The committed copy must not carry credentials."""
        raw = TRACKED.read_text(encoding="utf-8")
        for name, pattern in SECRET_PATTERNS.items():
            with self.subTest(credential=name):
                self.assertIsNone(
                    re.search(pattern, raw, re.IGNORECASE),
                    f"{name!r} found in the tracked config; do not commit it",
                )

    def test_secret_patterns_match_real_shapes(self) -> None:
        """Each pattern must match the shape it claims, or it is dead code.

        A malformed quantifier (e.g. doubled braces) compiles fine and silently
        never matches, which is how three of these patterns once passed every
        JSON-shaped leak. Assert against SECRET_PATTERNS itself, not a copy.
        """
        for name, pattern in SECRET_PATTERNS.items():
            for shape in SECRET_SHAPES[name]:
                with self.subTest(credential=name, shape=shape):
                    self.assertIsNotNone(
                        re.search(pattern, shape, re.IGNORECASE),
                        f"the {name!r} pattern does not match {shape!r}",
                    )

    def test_secret_patterns_spare_ordinary_text(self) -> None:
        """Real config prose must not trip a credential pattern."""
        raw = TRACKED.read_text(encoding="utf-8")
        for name, pattern in SECRET_PATTERNS.items():
            with self.subTest(credential=name):
                self.assertIsNone(
                    re.search(pattern, raw, re.IGNORECASE),
                    f"{name!r} false-fires on the tracked config",
                )

    def test_jev_mcp_not_disabled(self) -> None:
        """A recovery copy with jev-mcp off would restore a broken config."""
        config = load(TRACKED)
        servers = config.get("mcp", {}).get("servers", {})
        assert isinstance(servers, dict)
        self.assertIn("jev-mcp", servers, "tracked config lost the jev-mcp server")
        jev = servers["jev-mcp"]
        assert isinstance(jev, dict)
        self.assertIsNot(jev.get("enabled"), False)


if __name__ == "__main__":
    unittest.main()
