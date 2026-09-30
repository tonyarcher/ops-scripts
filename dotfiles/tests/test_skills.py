#!/usr/bin/env python3
"""Shape check for every skill under dotfiles/agents/skills/. Stdlib only.

Run: python -m unittest discover -s dotfiles/tests -t dotfiles/tests

This exists because install-agents.py syncs that directory as one unit: it
points ~/.config/opencode/skills at this tree, so whatever ships here is the
whole skill list. Four things are checked, all of them ones a harness reads:
the file is named SKILL.md, the frontmatter parses, it carries a non-empty
name and description, and the name matches the directory in kebab-case.

Deliberately not checked: file size, binary extensions, symlinks, upstream
provenance, and whether this README names each skill. Those all guard a
vendored third-party skill, and there are none. Add a check when there is
something real to check, not before.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1] / "agents" / "skills"

# Frontmatter opens on line 1 and closes with a bare delimiter.
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$")
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

MIN_SKILLS = 1


def skill_dirs() -> list[Path]:
    """Every skill directory, sorted by name."""
    if not SKILLS.is_dir():
        return []
    return sorted(p for p in SKILLS.iterdir() if p.is_dir())


def frontmatter(skill_md: Path) -> dict[str, str]:
    """Parse a SKILL.md frontmatter block. Raises ValueError when malformed."""
    match = FRONTMATTER.match(skill_md.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError("no frontmatter block opening with --- on line 1")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        pair = KEY.match(line)
        if pair is None:
            raise ValueError(f"frontmatter line is not `key: value`: {line!r}")
        if pair.group(1) in fields:
            raise ValueError(f"duplicate frontmatter key: {pair.group(1)}")
        fields[pair.group(1)] = pair.group(2).strip()
    return fields


class SkillShape(unittest.TestCase):
    def test_every_skill_has_a_skill_md(self) -> None:
        missing = [p.name for p in skill_dirs() if not (p / "SKILL.md").is_file()]
        self.assertEqual(missing, [], f"skills without SKILL.md: {missing}")

    def test_frontmatter_has_a_name_and_a_description(self) -> None:
        for skill in skill_dirs():
            with self.subTest(skill=skill.name):
                fields = frontmatter(skill / "SKILL.md")
                self.assertIn("name", fields, f"{skill.name}: no name in frontmatter")
                self.assertIn(
                    "description",
                    fields,
                    f"{skill.name}: no description in frontmatter",
                )
                # The description is what a harness matches on to decide
                # whether to load a skill, so an empty one hides the skill
                # without looking like a missing key.
                self.assertTrue(
                    fields["description"].strip(),
                    f"{skill.name}: description is empty",
                )

    def test_name_matches_directory_and_is_kebab_case(self) -> None:
        for skill in skill_dirs():
            with self.subTest(skill=skill.name):
                name = frontmatter(skill / "SKILL.md")["name"]
                self.assertEqual(name, skill.name, f"{skill.name}: name must match dir")
                self.assertRegex(name, KEBAB, "name must be lowercase kebab-case")

    def test_tree_is_found(self) -> None:
        self.assertGreaterEqual(
            len(skill_dirs()), MIN_SKILLS, "no skills found; is the path right?"
        )


if __name__ == "__main__":
    unittest.main()
