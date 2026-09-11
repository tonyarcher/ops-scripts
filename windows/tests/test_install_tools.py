#!/usr/bin/env python3
"""uv tool bin (ruff) must land on PATH for OpenCode and new shells."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_ENV = ROOT / "powershell" / "profile-env.ps1"
INSTALL_TOOLS = ROOT / "scripts" / "install-tools.ps1"


class ProfileEnv(unittest.TestCase):
    def test_prepends_uv_local_bin(self) -> None:
        text = PROFILE_ENV.read_text(encoding="utf-8")
        self.assertIn(r"$HOME\.local\bin", text)
        self.assertIn("Add-PathPrefix", text)


class InstallTools(unittest.TestCase):
    def test_persists_uv_tool_bin_on_user_path(self) -> None:
        text = INSTALL_TOOLS.read_text(encoding="utf-8")
        self.assertIn("Add-UserPath", text)
        self.assertIn("tool dir --bin", text)
        self.assertIn("Ensure-UvToolPath", text)


if __name__ == "__main__":
    unittest.main()
