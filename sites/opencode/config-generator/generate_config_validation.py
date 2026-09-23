"""Config validation for generate-config.py: static checks plus `opencode debug config`."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

from generate_config_jsonc import agent_block
from generate_config_opencode import ANSI_ESCAPE, run_opencode


def validate_layer1(config: MutableMapping[str, Any]) -> list[str]:
    problems: list[str] = []
    if "$schema" not in config:
        problems.append("missing $schema")
    if (
        "small_model" in config
        and config["small_model"] is not None
        and not (
            isinstance(config["small_model"], str) and "/" in config["small_model"]
        )
    ):
        problems.append("small_model must be a string containing '/'")
    default_agent = config.get("default_agent")
    if default_agent is not None:
        agents = agent_block(config)
        if default_agent not in agents:
            problems.append(f"default_agent '{default_agent}' is not a defined agent")
        elif agents[default_agent].get("mode") != "primary":
            problems.append(
                f"default_agent '{default_agent}' must reference a primary-mode agent"
            )
    agents = config.get("agent", config.get("agents"))
    if agents is not None:
        if not isinstance(agents, dict):
            problems.append("agents must be an object")
        else:
            for name, agent in agents.items():
                if not isinstance(agent, dict):
                    problems.append(f"agent '{name}' is not an object")
                    continue
                if "model" in agent and not (
                    isinstance(agent["model"], str) and "/" in agent["model"]
                ):
                    problems.append(
                        f"agent '{name}' model must be a string containing '/'"
                    )
                if "mode" in agent and agent["mode"] not in (
                    "primary",
                    "subagent",
                    "all",
                ):
                    problems.append(f"agent '{name}' mode must be primary/subagent/all")
    return problems


def warn_unknown_models(
    config: MutableMapping[str, Any], models: Sequence[str]
) -> None:
    """Non-blocking warning when referenced models are not in the discovered list.

    Not blocking: `opencode models` may not list custom-provider models, and
    `opencode debug config` accepts unknown model ids, so this is advisory only.
    """
    if not models:
        return
    refs: list[tuple[str, str]] = []
    if isinstance(config.get("small_model"), str):
        refs.append(("small_model", config["small_model"]))
    for name, agent in agent_block(config).items():
        if isinstance(agent, dict) and isinstance(agent.get("model"), str):
            refs.append((f"agent '{name}'", agent["model"]))
    for label, model in refs:
        if model not in models:
            print(
                f"warning: {label} model '{model}' is not in the discovered model list"
            )


def validate_layer2(config: Mapping[str, Any]) -> bool | None:
    """Authoritative validation via `opencode debug config` (nothing written)."""
    data = json.dumps(config)
    if len(data) > 30000:
        print(
            "warning: config exceeds 30000 chars; skipping opencode validation (Windows env limit)"
        )
        return None
    try:
        result = run_opencode(["debug", "config"], timeout=60, env_override=data)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"warning: could not run `opencode debug config`: {exc}")
        return None
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    combined = ANSI_ESCAPE.sub("", combined)
    if result.returncode == 0:
        return True
    for line in combined.splitlines():
        stripped = line.strip()
        if "Configuration is invalid" in line or stripped.startswith("\u21b3"):
            print(stripped)
    return False


def validate(config: MutableMapping[str, Any]) -> str:
    problems = validate_layer1(config)
    if problems:
        print("config has problems:")
        for problem in problems:
            print(f"  - {problem}")
        choice = input("[1] edit again  [2] cancel: ").strip()
        return "edit" if choice == "1" else "cancel"
    layer2 = validate_layer2(config)
    if layer2 is True:
        return "ok"
    if layer2 is None:
        confirm = (
            input("opencode validation unavailable. write anyway? [y/N]: ")
            .strip()
            .lower()
        )
        return "ok" if confirm == "y" else "cancel"
    print("config is invalid per opencode.")
    choice = input("[1] edit again  [2] cancel: ").strip()
    return "edit" if choice == "1" else "cancel"
