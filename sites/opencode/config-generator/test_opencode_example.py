#!/usr/bin/env python3
"""Offline tests for the opencode config seed and generator key handling.

Checks that sites/opencode/config-generator/opencode.json.example matches
the schema the installed opencode validates (flat `mcp`, singular `agent`,
`prompt`, `permission`) with Jev gated off globally and enabled per-agent
on build only. Also covers the generator's preference for the
current keys over legacy ones. No home writes, no network.

Run:  python sites/opencode/config-generator/test_opencode_example.py
"""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SEED_PATH = HERE / "opencode.json.example"
_spec = importlib.util.spec_from_file_location(
    "generate_config", HERE / "generate-config.py"
)
assert _spec is not None and _spec.loader is not None
generate_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generate_config)

JEV_AGENTS = {"build"}


def load_seed() -> dict[str, Any]:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


class SeedShape(unittest.TestCase):
    def test_valid_json_with_schema(self) -> None:
        config = load_seed()
        self.assertEqual(config["$schema"], "https://opencode.ai/config.json")

    def test_no_legacy_keys(self) -> None:
        config = load_seed()
        self.assertNotIn("agents", config)
        self.assertNotIn("permissions", config)
        assert isinstance(config.get("mcp"), dict)
        self.assertNotIn("servers", config["mcp"])
        raw = SEED_PATH.read_text(encoding="utf-8")
        self.assertNotIn('"system"', raw)
        self.assertNotIn('"disabled"', raw)

    def test_jev_mcp_flat_and_off(self) -> None:
        config = load_seed()
        assert isinstance(config.get("mcp"), dict)
        jev = config["mcp"].get("jev-mcp")
        assert isinstance(jev, dict)
        self.assertEqual(jev["type"], "local")
        assert isinstance(jev.get("command"), list)
        self.assertIn("jev-mcp", " ".join(jev["command"]))
        self.assertIs(jev["enabled"], False)

    def test_jev_gated_off_globally(self) -> None:
        config = load_seed()
        assert isinstance(config.get("tools"), dict)
        self.assertIs(config["tools"].get("jev-mcp_*"), False)

    def test_jev_enabled_only_on_build(self) -> None:
        config = load_seed()
        agents = config["agent"]
        assert isinstance(agents, dict)
        for name, agent in agents.items():
            assert isinstance(agent, dict)
            tools = agent.get("tools", {})
            assert isinstance(tools, dict)
            if name in JEV_AGENTS:
                self.assertIs(tools.get("jev-mcp_*"), True)
            else:
                self.assertNotIn("jev-mcp_*", tools)

    def test_agents_use_current_keys(self) -> None:
        config = load_seed()
        agents = config["agent"]
        assert isinstance(agents, dict)
        for agent in agents.values():
            assert isinstance(agent, dict)
            self.assertIn(agent.get("mode"), ("primary", "subagent", "all"))
            model = agent.get("model")
            assert isinstance(model, str)
            self.assertIn("/", model)
            self.assertIn("description", agent)
            # `general` and `explore` ship without a prompt (upstream
            # default); the rule is that no agent uses legacy `system`.
            self.assertNotIn("system", agent)
            self.assertNotIn("permissions", agent)

    def test_default_agent_is_primary(self) -> None:
        config = load_seed()
        agents = config["agent"]
        assert isinstance(agents, dict)
        default = config["default_agent"]
        assert isinstance(default, str)
        self.assertEqual(agents[default].get("mode"), "primary")

    def test_no_small_model_jev_chat_unverified(self) -> None:
        config = load_seed()
        self.assertNotIn("small_model", config)


class GeneratorKeys(unittest.TestCase):
    def test_agent_block_prefers_agent(self) -> None:
        config: dict[str, object] = {"agent": {"a": {}}, "agents": {"b": {}}}
        self.assertIn("a", generate_config.agent_block(config))

    def test_agent_block_creates_agent(self) -> None:
        config: dict[str, object] = {}
        self.assertEqual(generate_config.agent_block(config), {})
        self.assertIn("agent", config)

    def test_system_field_prefers_prompt(self) -> None:
        self.assertEqual(
            generate_config.system_field({"prompt": "x", "system": "y"}), "prompt"
        )
        self.assertEqual(generate_config.system_field({"system": "y"}), "system")

    def test_validate_layer1_accepts_seed(self) -> None:
        self.assertEqual(generate_config.validate_layer1(load_seed()), [])

    def test_validate_layer1_flags_bad_default(self) -> None:
        config = copy.deepcopy(load_seed())
        config["default_agent"] = "nope"
        problems = generate_config.validate_layer1(config)
        self.assertTrue(any("default_agent" in p for p in problems))

    def test_validate_layer1_flags_bad_mode(self) -> None:
        config = copy.deepcopy(load_seed())
        agents = config["agent"]
        assert isinstance(agents, dict)
        build = agents["build"]
        assert isinstance(build, dict)
        build["mode"] = "bogus"
        problems = generate_config.validate_layer1(config)
        self.assertTrue(any("build" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
