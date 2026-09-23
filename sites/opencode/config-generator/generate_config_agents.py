"""Agent editing prompts for generate-config.py."""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

from generate_config_jsonc import agent_block, system_field
from generate_config_picker import ModelPicker, multiline_input


def print_agent_summary(name: str, agent: Mapping[str, Any]) -> None:
    print(f"--- agent: {name} ---")
    print(f"  mode: {agent.get('mode', '(unset)')}")
    print(f"  model: {agent.get('model', '(unset)')}")
    print(f"  variant: {agent.get('variant', '(unset)')}")
    if "temperature" in agent:
        print(f"  temperature: {agent['temperature']}")
    description = agent.get("description", "")
    if description:
        truncated = description[:100]
        if len(description) > 100:
            truncated += "..."
        print(f"  description: {truncated}")


def edit_one_agent(
    config: MutableMapping[str, Any], name: str, models: Sequence[str]
) -> None:
    agents = agent_block(config)
    agent = agents[name]
    field = system_field(agent)
    print_agent_summary(name, agent)
    choice = input(
        f"[{name}] [1] keep  [2] edit model  [3] edit description  [4] edit {field}  [5] remove (Enter=keep): "
    ).strip()
    if choice in ("", "1"):
        return
    if choice == "2":
        picked = ModelPicker(models, agent.get("model")).select()
        if picked:
            agent["model"] = picked
    elif choice == "3":
        description = multiline_input("description", agent.get("description"))
        if description is not None:
            agent["description"] = description
    elif choice == "4":
        text = multiline_input(field, agent.get(field))
        if text is not None:
            agent[field] = text
    elif choice == "5":
        confirm = input(f"remove agent '{name}'? [y/N]: ").strip().lower()
        if confirm == "y":
            del agents[name]
    else:
        print("invalid choice")


def edit_agents(config: MutableMapping[str, Any], models: Sequence[str]) -> None:
    while True:
        agents = agent_block(config)
        for name in list(agents.keys()):
            if name in agents:
                edit_one_agent(config, name, models)
        answer = input("edit another agent? (number/name, blank to continue): ").strip()
        if answer == "":
            break
        names = list(agent_block(config).keys())
        if answer.isdigit():
            idx = int(answer) - 1
            if 0 <= idx < len(names):
                edit_one_agent(config, names[idx], models)
                continue
        elif answer in agent_block(config):
            edit_one_agent(config, answer, models)
            continue
        print("no such agent")


def add_custom_agents(config: MutableMapping[str, Any], models: Sequence[str]) -> None:
    while True:
        answer = input("add a custom agent? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            break
        while True:
            name = input("agent name (kebab-case): ").strip()
            if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
                print(
                    "name must be kebab-case (lowercase letters, digits, single hyphens)"
                )
                continue
            if name in agent_block(config):
                print("an agent with that name already exists")
                continue
            break
        while True:
            print("mode: [1] primary  [2] subagent  [3] all")
            mode_choice = input("choice [1]: ").strip() or "1"
            mode = {"1": "primary", "2": "subagent", "3": "all"}.get(mode_choice)
            if mode:
                break
            print("invalid choice")
        picked = ModelPicker(models, None).select()
        if not picked:
            print("no model selected; skipping this agent")
            continue
        description = input("description (single line, Enter for none): ").strip()
        prompt = multiline_input("system", None)
        agent: dict[str, str | None] = {"mode": mode, "model": picked}
        if description:
            agent["description"] = description
        if prompt:
            agent["prompt"] = prompt
        agent_block(config)[name] = agent
