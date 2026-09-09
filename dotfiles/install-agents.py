#!/usr/bin/env python3
"""Install the user-wide AGENTS.md and point OpenCode at it.

Canonical:
  Windows: %APPDATA%\\agents\\AGENTS.md
  Linux:   ~/.config/agents/AGENTS.md

OpenCode reads ~/.config/opencode/AGENTS.md (also on Windows). This script
symlinks that path to the canonical file. Canonical itself is a symlink to
this repo's dotfiles/agents/AGENTS.md when the OS allows it; otherwise a copy.

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


def canonical_path(*, home: Path, appdata: str | None, win32: bool) -> Path:
    if win32:
        if not appdata:
            raise SystemExit("APPDATA is unset; cannot place %APPDATA%\\agents\\AGENTS.md")
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
        print(f"    symlink failed ({exc}); will copy if this is the canonical file")
        return False


def place(target: Path, dest: Path, *, force: bool, dry_run: bool, allow_copy: bool) -> str:
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


def install(
    *,
    source: Path,
    canonical: Path,
    opencode: Path,
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
    if args.dry_run:
        print(f"would install {SOURCE}")
        print(f"  canonical -> {canonical}")
        print(f"  opencode  -> {opencode}")
    return install(
        source=SOURCE,
        canonical=canonical,
        opencode=opencode,
        force=args.force,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
