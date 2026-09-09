#!/usr/bin/env python3
"""Offline tests for install-agents path math and place(). No home writes."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("install_agents", ROOT / "install-agents.py")
assert _spec is not None and _spec.loader is not None
install_agents = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(install_agents)


class Paths(unittest.TestCase):
    def test_linux_canonical(self) -> None:
        home = Path("/home/tony")
        got = install_agents.canonical_path(home=home, appdata=None, win32=False)
        self.assertEqual(got, home / ".config" / "agents" / "AGENTS.md")

    def test_windows_canonical_uses_appdata(self) -> None:
        home = Path("C:/Users/tony")
        got = install_agents.canonical_path(
            home=home,
            appdata="C:/Users/tony/AppData/Roaming",
            win32=True,
        )
        self.assertEqual(got, Path("C:/Users/tony/AppData/Roaming/agents/AGENTS.md"))

    def test_windows_requires_appdata(self) -> None:
        with self.assertRaises(SystemExit):
            install_agents.canonical_path(home=Path("C:/Users/tony"), appdata=None, win32=True)

    def test_opencode_is_xdg_on_both(self) -> None:
        home = Path("/home/tony")
        self.assertEqual(
            install_agents.opencode_path(home),
            home / ".config" / "opencode" / "AGENTS.md",
        )


class Place(unittest.TestCase):
    def test_install_links_opencode_to_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "src" / "AGENTS.md"
            source.parent.mkdir()
            source.write_text("# hi\n", encoding="utf-8")
            canonical = root / "agents" / "AGENTS.md"
            opencode = root / "opencode" / "AGENTS.md"
            rc = install_agents.install(
                source=source,
                canonical=canonical,
                opencode=opencode,
                force=False,
                dry_run=False,
            )
            self.assertEqual(rc, 0)
            self.assertTrue(canonical.is_file())
            self.assertTrue(opencode.is_file())
            self.assertEqual(canonical.read_text(encoding="utf-8"), "# hi\n")
            self.assertEqual(opencode.read_text(encoding="utf-8"), "# hi\n")
            if opencode.is_symlink():
                self.assertEqual(opencode.resolve(), canonical.resolve())

    def test_skip_when_already_linked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "src" / "AGENTS.md"
            source.parent.mkdir()
            source.write_text("# hi\n", encoding="utf-8")
            canonical = root / "agents" / "AGENTS.md"
            opencode = root / "opencode" / "AGENTS.md"
            install_agents.install(
                source=source,
                canonical=canonical,
                opencode=opencode,
                force=False,
                dry_run=False,
            )
            rc = install_agents.install(
                source=source,
                canonical=canonical,
                opencode=opencode,
                force=False,
                dry_run=False,
            )
            self.assertEqual(rc, 0)

    def test_missing_source_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            rc = install_agents.install(
                source=root / "nope.md",
                canonical=root / "c.md",
                opencode=root / "o.md",
                force=False,
                dry_run=False,
            )
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
