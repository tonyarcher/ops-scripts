#!/usr/bin/env python3
"""Brewfile must stay a Mac client tool list. No CUDA, no Docker Desktop."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BREWFILE = ROOT / "Brewfile"
FORMULA_RE = re.compile(r'^brew "([^"]+)"\s*$')
CASK_RE = re.compile(r'^cask "([^"]+)"\s*$')

REQUIRED = frozenset(
    {
        "git",
        "node",
        "python",
        "gh",
        "ripgrep",
        "eza",
        "zoxide",
        "jq",
        "bat",
        "fd",
        "p7zip",
        "lazygit",
        "uv",
        "opencode",
        "ffmpeg",
        "vim",
        "go",
        "openjdk@21",
        "rustup",
        "fzf",
        "bun",
        "wireguard-tools",
        "gitleaks",
        "git-delta",
        "ast-grep",
        "osv-scanner",
    }
)
FORBIDDEN = frozenset(
    {
        "docker",
        "docker-desktop",
        "nvidia-cuda",
        "cuda",
        "colima",
        "rancher",
        "wireguard",
    }
)


def formulae(text: str) -> set[str]:
    found: set[str] = set()
    for line in text.splitlines():
        match = FORMULA_RE.match(line.strip())
        if match:
            found.add(match.group(1))
    return found


def casks(text: str) -> set[str]:
    found: set[str] = set()
    for line in text.splitlines():
        match = CASK_RE.match(line.strip())
        if match:
            found.add(match.group(1))
    return found


class BrewfileContents(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = BREWFILE.read_text(encoding="utf-8")
        cls.formulae = formulae(cls.text)
        cls.casks = casks(cls.text)

    def test_required_formulae(self) -> None:
        missing = REQUIRED - self.formulae
        self.assertEqual(missing, set(), f"missing {sorted(missing)}")

    def test_no_casks(self) -> None:
        self.assertEqual(self.casks, set())

    def test_no_forbidden_names(self) -> None:
        names = self.formulae | self.casks
        self.assertEqual(names & FORBIDDEN, set())

    def test_says_not_cuda_host(self) -> None:
        self.assertIn("Not a CUDA host", self.text)


class InstallScript(unittest.TestCase):
    def test_does_not_pass_invalid_brew_bundle_flags(self) -> None:
        script = (ROOT / "install-tools.sh").read_text(encoding="utf-8")
        self.assertNotIn("--no-lock", script)
        self.assertNotRegex(script, r"brew bundle install.*--dry-run")
        self.assertIn("would brew bundle install", script)

    def test_usage_range_skips_set_e(self) -> None:
        script = (ROOT / "install-tools.sh").read_text(encoding="utf-8")
        self.assertIn("sed -n '2,10p'", script)

    def test_puts_uv_tools_on_path(self) -> None:
        script = (ROOT / "install-tools.sh").read_text(encoding="utf-8")
        self.assertIn('export PATH="$HOME/.local/bin:$PATH"', script)


if __name__ == "__main__":
    unittest.main()
