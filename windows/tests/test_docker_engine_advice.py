#!/usr/bin/env python3
"""Deploy wrappers must point at Rancher Desktop, never Docker Desktop.

The repo standardises on Rancher Desktop for local engine work on Windows and
macOS (see AGENTS.md); Docker Desktop is in no supported setup. These three
files carry the install guidance a user hits first, so pin the wording.

The rule is clause-level rather than verb-level: a line may name Docker
Desktop only to forbid or remove it. Naming it as the thing to install, start,
update or require is the regression being guarded, whatever the verb. Clauses
are split on sentence punctuation so that "not found. Install Docker Desktop."
is still flagged -- the "not" belongs to the missing-engine clause, not to the
advice. This is a heuristic, not English comprehension: "installing Docker
Desktop instead of Rancher" would slip through.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SH = ROOT / "sites" / "opencode" / "docker-image" / "deploy.sh"
DEPLOY_PS1 = ROOT / "windows" / "scripts" / "deploy-opencode-docker.ps1"
README = ROOT / "sites" / "opencode" / "docker-image" / "README.md"
GUARDED = (DEPLOY_SH, DEPLOY_PS1, README)

MENTION = "docker desktop"
CLAUSE = re.compile(r"[.;!?]")
# Words that turn a mention into a prohibition. "\bnot\b" will not match inside
# "cannot", so "cannot connect" does not release advice.
PROHIBITION = re.compile(
    r"\b(?:not|never|avoid|instead|without|uninstall\w*|remov\w*)\b|n't",
    re.IGNORECASE,
)
# The engine-missing guidance, which has to name the engine we install.
MISSING = re.compile(r"not found|not connected|cannot connect", re.IGNORECASE)


def offenders(path: Path) -> list[str]:
    """Lines whose clause names Docker Desktop without forbidding it."""
    bad: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if MENTION not in line.lower():
            continue
        flagged = any(
            MENTION in clause.lower() and not PROHIBITION.search(clause)
            for clause in CLAUSE.split(line)
        )
        if flagged:
            bad.append(line.strip())
    return bad


class EngineAdvice(unittest.TestCase):
    def test_no_docker_desktop_advice(self) -> None:
        """No wrapper or doc tells the user to install Docker Desktop."""
        for path in GUARDED:
            with self.subTest(path=path.name):
                bad = offenders(path)
                self.assertFalse(bad, f"{path.name}: {bad}")

    def test_missing_engine_message_names_rancher(self) -> None:
        """The missing-engine guidance names the engine we actually install."""
        for path in GUARDED:
            with self.subTest(path=path.name):
                lines = path.read_text(encoding="utf-8").splitlines()
                hits = [
                    line
                    for line in lines
                    if MISSING.search(line) and "Rancher Desktop" in line
                ]
                self.assertTrue(
                    hits, f"{path.name}: no missing-engine line names Rancher Desktop"
                )


if __name__ == "__main__":
    unittest.main()
