"""Config file targets, atomic writes, and backups for generate-config.py."""

from __future__ import annotations

import datetime
import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from generate_config_jsonc import render_preview, strip_jsonc


def resolve_project_target(dirpath: Path) -> Path:
    """Find the existing config in opencode's effective precedence order, else the default path.

    Verified empirically: .opencode/opencode.json wins over opencode.jsonc, which wins
    over a root opencode.json, when more than one exists.
    """
    candidates = [
        dirpath / ".opencode" / "opencode.json",
        dirpath / "opencode.jsonc",
        dirpath / "opencode.json",
    ]
    found = [c for c in candidates if c.exists()]
    if len(found) > 1:
        print(
            "warning: multiple config files found; opencode loads the first of these:"
        )
        for c in found:
            print(f"  - {c}")
    if found:
        return found[0]
    return dirpath / "opencode.json"


def atomic_write(path: Path, content: str) -> None:
    """Write content to path via a temp file + os.replace so a failed write never truncates the target."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_config(
    target: Path, config: Mapping[str, Any], schema: str, dry_run: bool
) -> None:
    content = render_preview(config, schema) + "\n"
    if dry_run:
        print("dry run: no files written")
        return
    if not target.exists():
        confirm = input(f"write {target}? [y/N]: ").strip().lower()
        if confirm != "y":
            print("cancelled; nothing written")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, content)
        print(f"wrote {target}")
        print("Restart opencode for the new config to take effect.")
        return
    print(f"target {target} already exists.")
    print("[1] replace (backs up existing)")
    print("[2] write alongside")
    print("[3] cancel")
    choice = input("choice: ").strip()
    # Local wall-clock stamp for backup names; astimezone() keeps local time, just aware.
    timestamp = datetime.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    if choice == "1":
        backup = target.with_name(f"{target.stem}.bak-{timestamp}")
        shutil.copy2(target, backup)
        print(f"backup: {backup}")
        atomic_write(target, content)
        print(f"wrote {target}")
        print("Restart opencode for the new config to take effect.")
    elif choice == "2":
        alongside = target.with_name(f"{target.stem}.generated-{timestamp}.json")
        atomic_write(alongside, content)
        print(f"wrote {alongside}")
        print(
            "note: opencode does not auto-load this file; rename or move it into place to use it."
        )
    else:
        print("cancelled; nothing written")


def load_existing_config(target: Path) -> dict[str, Any]:
    """Parse the existing target as JSONC; {} when missing, unreadable, or not an object."""
    existing: dict[str, Any] = {}
    if not target.exists():
        return existing
    try:
        parsed = json.loads(strip_jsonc(target.read_text(encoding="utf-8-sig")))
        if not isinstance(parsed, dict):
            print(
                "warning: existing config is not a JSON object; starting from defaults"
            )
            return existing
        for key in ("agents", "agent"):
            if key in parsed and not isinstance(parsed.get(key), dict):
                print(f"warning: existing '{key}' is not an object; using seed agents")
                del parsed[key]
        return parsed
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        print(
            f"warning: could not parse existing config ({exc}); starting from defaults"
        )
        return existing
