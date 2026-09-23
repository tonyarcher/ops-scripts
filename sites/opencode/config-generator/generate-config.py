#!/usr/bin/env python3
"""Interactive opencode.json generator wizard.

Walks you through picking a small_model, default_agent, and editing the agent
list, then validates the result with `opencode debug config` before writing.
Existing configs are parsed as JSONC (comments allowed) and merged on top of
opencode.json.example (copy of the global install seed). Replaced files are
backed up first.

Run:  python sites/opencode/config-generator/generate-config.py [--global] [--dir PATH] [--dry-run]

--global targets ~/.config/opencode/opencode.json, --dir targets a project
directory (default: cwd). --dry-run previews and validates but writes nothing.
Restart opencode after changes take effect.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import MutableMapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_config_agents import add_custom_agents, edit_agents
from generate_config_jsonc import agent_block, deep_merge, render_preview, system_field
from generate_config_opencode import discover_models, group_models
from generate_config_picker import ModelPicker
from generate_config_validation import validate, validate_layer1, warn_unknown_models
from generate_config_writer import (
    load_existing_config,
    resolve_project_target,
    write_config,
)

# Re-exported for test_opencode_example.py, which loads this file via importlib.
__all__ = [
    "agent_block",
    "system_field",
    "validate_layer1",
]

CONFIG_SCHEMA = "https://opencode.ai/config.json"
HERE = Path(__file__).resolve().parent
SEED_PATH = HERE / "opencode.json.example"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactive opencode.json generator wizard"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--global",
        dest="global_",
        action="store_true",
        help="target ~/.config/opencode/opencode.json",
    )
    group.add_argument("--dir", help="project directory (default: cwd)")
    parser.add_argument(
        "--dry-run", action="store_true", help="show preview + validate, write nothing"
    )
    return parser.parse_args()


def _choose_target(args: argparse.Namespace) -> Path:
    """Resolve the config file to write from the flags, or ask interactively."""
    if args.global_:
        return Path.home() / ".config" / "opencode" / "opencode.json"
    if args.dir:
        return resolve_project_target(Path(args.dir).expanduser())
    print("where should the config be written?")
    print("  [1] project (a directory in this repo or elsewhere)")
    print("  [2] global (~/.config/opencode/opencode.json)")
    choice = input("choice [1]: ").strip() or "1"
    if choice == "2":
        return Path.home() / ".config" / "opencode" / "opencode.json"
    directory = input(f"project directory [{os.getcwd()}]: ").strip() or os.getcwd()
    return resolve_project_target(Path(directory))


def _edit_small_model(config: MutableMapping[str, Any], models: Sequence[str]) -> None:
    """Prompt for the small_model: keep the current value or pick a replacement."""
    print("\n-- small_model --")
    current_small = config.get("small_model")
    print(f"current small_model: {current_small or '(none)'}")
    if current_small:
        answer = input("Enter to keep, or type anything to change it: ").strip()
        if answer != "":
            picked = ModelPicker(models, current_small).select()
            if picked:
                config["small_model"] = picked
    else:
        answer = input(
            "no small_model set. Enter to skip, or type anything to set one: "
        ).strip()
        if answer != "":
            picked = ModelPicker(models, None).select()
            if picked:
                config["small_model"] = picked


def _edit_default_agent(config: MutableMapping[str, Any]) -> None:
    """Prompt for default_agent: keep the current value or point it at a primary agent."""
    print("\n-- default_agent --")
    primary_agents = [
        name
        for name, agent in agent_block(config).items()
        if agent.get("mode") == "primary"
    ]
    current_default = config.get("default_agent")
    print(f"current default_agent: {current_default or '(none)'}")
    if primary_agents:
        print("primary agents:")
        for i, name in enumerate(primary_agents, 1):
            print(f"  [{i}] {name}")
    choice = input("choice (number, Enter to keep current): ").strip()
    if choice == "":
        pass
    elif choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(primary_agents):
            config["default_agent"] = primary_agents[idx]
        else:
            print("invalid choice; keeping current")
    elif choice in primary_agents:
        config["default_agent"] = choice
    else:
        print("not a primary agent; keeping current")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    target = _choose_target(args)

    print(
        f"target: {target}" + (" (exists)" if target.exists() else " (does not exist)")
    )

    models = discover_models()
    if models:
        for provider, ids in group_models(models).items():
            print(f"  {provider}: {len(ids)} models")
    else:
        print("  (no models discovered)")

    defaults = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    existing = load_existing_config(target)
    config = deep_merge(defaults, existing)
    schema = existing.get("$schema", CONFIG_SCHEMA)
    config["$schema"] = schema

    _edit_small_model(config, models)
    _edit_default_agent(config)

    while True:
        edit_agents(config, models)
        add_custom_agents(config, models)
        warn_unknown_models(config, models)
        print("\n--- preview ---")
        print(render_preview(config, schema))
        result = validate(config)
        if result == "ok":
            break
        if result == "cancel":
            print("cancelled; nothing written")
            return

    write_config(target, config, schema, args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except EOFError:
        print("aborted (stdin closed)")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\naborted")
        sys.exit(130)
