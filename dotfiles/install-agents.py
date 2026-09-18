#!/usr/bin/env python3
"""Install the user-wide AGENTS.md and skills, and point OpenCode at them.

Canonical:
  Windows: %APPDATA%\\agents\\AGENTS.md
  Linux:   ~/.config/agents/AGENTS.md

OpenCode reads ~/.config/opencode/AGENTS.md (also on Windows). This script
symlinks that path to the canonical file. Canonical itself is a symlink to
this repo's dotfiles/agents/AGENTS.md when the OS allows it; otherwise a copy.
Skills sync from dotfiles/agents/skills/ to ~/.config/opencode/skills/ the
same way (symlink, copy fallback).

Run:  python dotfiles/install-agents.py
      python dotfiles/install-agents.py --dry-run
      python dotfiles/install-agents.py --force
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent / "agents" / "AGENTS.md"
SKILLS_SOURCE = Path(__file__).resolve().parent / "agents" / "skills"


def opencode_skills_path(home: Path) -> Path:
    return home / ".config" / "opencode" / "skills"


def canonical_path(*, home: Path, appdata: str | None, win32: bool) -> Path:
    if win32:
        if not appdata:
            raise SystemExit(
                "APPDATA is unset; cannot place %APPDATA%\\agents\\AGENTS.md"
            )
        return Path(appdata) / "agents" / "AGENTS.md"
    return home / ".config" / "agents" / "AGENTS.md"


def opencode_path(home: Path) -> Path:
    return home / ".config" / "opencode" / "AGENTS.md"


def already_installed(dest: Path, target: Path) -> bool:
    if not (dest.exists() or dest.is_symlink()):
        return False
    try:
        if dest.resolve() == target.resolve():
            return True
    except OSError:
        pass
    if dest.is_file() and not dest.is_symlink() and target.is_file():
        return dest.read_bytes() == target.read_bytes()
    return False


def backup(path: Path) -> Path:
    dest = path.with_name(path.name + ".bak")
    n = 1
    while dest.exists() or dest.is_symlink():
        dest = path.with_name(f"{path.name}.bak.{n}")
        n += 1
    path.rename(dest)
    return dest


def try_symlink(target: Path, dest: Path) -> bool:
    try:
        dest.symlink_to(target)
        return True
    except OSError as exc:
        print(f"    symlink failed ({exc}); falling back to copy")
        return False


def place(
    target: Path, dest: Path, *, force: bool, dry_run: bool, allow_copy: bool
) -> str:
    """Point dest at target. Returns 'skip' | 'link' | 'copy' | 'place' (dry-run)."""
    if dest.exists() or dest.is_symlink():
        if already_installed(dest, target) and not force:
            return "skip"
        if dry_run:
            return "place"
        backup(dest)
    if dry_run:
        return "place"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if try_symlink(target, dest):
        return "link"
    if not allow_copy:
        raise SystemExit(f"could not symlink {dest} -> {target}")
    shutil.copy2(target, dest)
    return "copy"


def tree_entries(root: Path) -> dict[Path, str]:
    """Map relative paths to kinds without following symlinks."""
    entries: dict[Path, str] = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if path.is_symlink():
            entries[rel] = "link:" + os.readlink(path)
        elif path.is_dir():
            entries[rel] = "dir"
        elif path.is_file():
            entries[rel] = "file"
    return entries


def dirs_match(first: Path, second: Path) -> bool:
    """True when two directory trees hold identical files and links."""
    if not (first.is_dir() and second.is_dir()):
        return False
    left = tree_entries(first)
    if left != tree_entries(second):
        return False
    for rel, kind in left.items():
        if kind == "file" and (first / rel).read_bytes() != (second / rel).read_bytes():
            return False
    return True


def place_dir(target: Path, dest: Path, *, force: bool, dry_run: bool) -> str:
    """Point dest dir at target dir. Returns 'skip' | 'link' | 'copy' | 'place'."""
    if dest.exists() or dest.is_symlink():
        if already_installed(dest, target) and not force:
            return "skip"
        if not force and not dest.is_symlink() and dirs_match(target, dest):
            return "skip"
        if dry_run:
            return "place"
        backup(dest)
    if dry_run:
        return "place"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if try_symlink(target, dest):
        return "link"
    shutil.copytree(target, dest, symlinks=True)
    return "copy"


def install(
    *,
    source: Path,
    canonical: Path,
    opencode: Path,
    skills_source: Path | None = None,
    skills_dest: Path | None = None,
    force: bool,
    dry_run: bool,
) -> int:
    if not source.is_file():
        print(f"missing source: {source}", file=sys.stderr)
        return 1
    how = place(source, canonical, force=force, dry_run=dry_run, allow_copy=True)
    print(f"    canonical {how}: {canonical}")
    how_oc = place(canonical, opencode, force=force, dry_run=dry_run, allow_copy=True)
    print(f"    opencode  {how_oc}: {opencode} -> {canonical}")
    if skills_source is None or skills_dest is None:
        return 0
    if not skills_source.is_dir():
        print(f"missing skills source: {skills_source}", file=sys.stderr)
        return 1
    how_skills = place_dir(skills_source, skills_dest, force=force, dry_run=dry_run)
    print(f"    skills    {how_skills}: {skills_dest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    win32 = sys.platform == "win32"
    canonical = canonical_path(
        home=Path.home(),
        appdata=os.environ.get("APPDATA"),
        win32=win32,
    )
    opencode = opencode_path(Path.home())
    skills_dest = opencode_skills_path(Path.home())
    if args.dry_run:
        print(f"would install {SOURCE}")
        print(f"  canonical -> {canonical}")
        print(f"  opencode  -> {opencode}")
        print(f"  skills    -> {skills_dest}")
    return install(
        source=SOURCE,
        canonical=canonical,
        opencode=opencode,
        skills_source=SKILLS_SOURCE,
        skills_dest=skills_dest,
        force=args.force,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
