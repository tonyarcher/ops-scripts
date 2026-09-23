"""JSONC parsing and config structure helpers for generate-config.py."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, MutableMapping
from typing import Any


def strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments from JSONC text, respecting strings."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            end = text.find("*/", i)
            if end == -1:
                raise ValueError("unterminated /* block comment")
            i = end + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Merge override on top of base; dicts merge recursively, others replace."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def agent_block(config: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Return the agents map. Prefer current `agent` over legacy `agents`."""
    agents = config.get("agent")
    if isinstance(agents, dict):
        return agents
    legacy = config.get("agents")
    if isinstance(legacy, dict):
        return legacy
    fresh: MutableMapping[str, Any] = {}
    config["agent"] = fresh
    return fresh


def system_field(agent: Mapping[str, Any]) -> str:
    """Current seeds use `prompt`; older seeds used `system`."""
    if "prompt" in agent:
        return "prompt"
    return "system"


def build_output(config: Mapping[str, Any], schema: str) -> dict[str, Any]:
    """Return the config dict with $schema forced as the first key."""
    output: dict[str, Any] = {"$schema": schema}
    for key, value in config.items():
        if key == "$schema":
            continue
        output[key] = value
    return output


def render_preview(config: Mapping[str, Any], schema: str) -> str:
    return json.dumps(build_output(config, schema), indent=2, ensure_ascii=False)
