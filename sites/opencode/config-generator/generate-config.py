#!/usr/bin/env python3
"""Interactive opencode.json generator wizard.

Walks you through picking a small_model, default_agent, and editing the agent
list, then validates the result with `opencode debug config` before writing.
Existing configs are parsed as JSONC (comments allowed) and merged on top of
default-agents.json; replaced files are backed up first.

Run:  python sites/opencode/config-generator/generate-config.py [--global] [--dir PATH] [--dry-run]

--global targets ~/.config/opencode/opencode.json, --dir targets a project
directory (default: cwd). --dry-run previews and validates but writes nothing.
Restart opencode after changes take effect.
"""

import argparse
import copy
import datetime
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import select
    import termios
    import tty

CONFIG_SCHEMA = "https://opencode.ai/config.json"
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_jsonc(text):
    """Remove // and /* */ comments from JSONC text, respecting strings."""
    out = []
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


def run_opencode(args, timeout=60, env_override=None):
    """Run opencode with an explicit argv list. Resolves the Windows shim."""
    env = None
    if env_override is not None:
        env = os.environ.copy()
        env["OPENCODE_CONFIG_CONTENT"] = env_override

    def _run(cmd):
        return subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)

    try:
        result = _run(["opencode"] + args)
    except FileNotFoundError:
        exe = shutil.which("opencode")
        if exe is None:
            raise
        result = _run([exe] + args)
    result.stdout = result.stdout.decode("utf-8", errors="replace")
    result.stderr = result.stderr.decode("utf-8", errors="replace")
    return result


def discover_models():
    """Return the deduped, ordered list of provider/model ids from `opencode models`."""
    try:
        result = run_opencode(["models"], timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"warning: could not run `opencode models`: {exc}")
        return []
    if result.returncode != 0:
        print("warning: `opencode models` failed")
        return []
    models = []
    seen = set()
    for line in result.stdout.splitlines():
        line = ANSI_ESCAPE.sub("", line).strip()
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", line) or line in seen:
            continue
        seen.add(line)
        models.append(line)
    return models


def group_models(models):
    """Group model ids into an ordered dict provider -> [model ids]."""
    groups = {}
    for model in models:
        provider, _, model_id = model.partition("/")
        groups.setdefault(provider, []).append(model_id)
    return groups


def deep_merge(base, override):
    """Merge override on top of base; dicts merge recursively, others replace."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def resolve_project_target(dirpath):
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
        print("warning: multiple config files found; opencode loads the first of these:")
        for c in found:
            print(f"  - {c}")
    if found:
        return found[0]
    return dirpath / "opencode.json"


def read_key():
    """Read one keypress; returns a control token or a printable character."""
    if os.name == "nt":
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            special = msvcrt.getwch()
            return {"H": "up", "P": "down"}.get(special, "")
        if ch == "\r":
            return "enter"
        if ch == "\x1b":
            return "esc"
        if ch in ("\x08", "\x7f"):
            return "backspace"
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch == "\x10":
            return "up"
        if ch == "\x0e":
            return "down"
        return ch
    ch = sys.stdin.read(1)
    if ch == "":
        raise EOFError
    if ch == "\x1b":
        if select.select([sys.stdin], [], [], 0.05)[0]:
            seq = sys.stdin.read(2)
            if seq == "[A":
                return "up"
            if seq == "[B":
                return "down"
        return "esc"
    if ch in ("\r", "\n"):
        return "enter"
    if ch in ("\x08", "\x7f"):
        return "backspace"
    if ch == "\x03":
        raise KeyboardInterrupt
    if ch == "\x10":
        return "up"
    if ch == "\x0e":
        return "down"
    return ch


class ModelPicker:
    """Pick a model id from the discovered list. Returns only known ids except
    in degraded mode (empty model list), where typed input is unvalidated."""

    def __init__(self, models, current=None):
        self.models = models
        self.current = current
        self.groups = group_models(models)
        self._drawn = 0

    def select(self):
        if not self.models:
            return self._degraded_select()
        if sys.stdin.isatty():
            return self._primary_select()
        return self._fallback_select()

    def _draw(self, lines):
        if self._drawn:
            sys.stdout.write("\x1b[1A\r\x1b[K" * self._drawn)
        for line in lines:
            sys.stdout.write(line + "\n")
        self._drawn = len(lines)
        sys.stdout.flush()

    def _primary_select(self):
        if os.name == "nt":
            os.system("")
        filter_text = ""
        cursor = 0
        if self.current in self.models:
            cursor = self.models.index(self.current)
        self._drawn = 0
        old_termios = None
        use_fallback = False
        try:
            if os.name != "nt":
                old_termios = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
            while True:
                matches = [m for m in self.models if filter_text.lower() in m.lower()]
                if cursor >= len(matches):
                    cursor = max(0, len(matches) - 1)
                lines = [f"filter: {filter_text}  ({len(matches)}/{len(self.models)} matches)"]
                if not matches:
                    lines.append("no matches")
                else:
                    start = 0
                    if len(matches) > 15:
                        start = max(0, min(cursor - 7, len(matches) - 15))
                    window = matches[start : start + 15]
                    for i, model in enumerate(window):
                        marker = ">" if start + i == cursor else " "
                        lines.append(f"{marker} {model}")
                lines.append("type to filter · up/down move · Enter select · Esc numbered menu")
                self._draw(lines)
                key = read_key()
                if key == "enter":
                    if matches:
                        self._draw([])
                        return matches[cursor]
                elif key == "esc":
                    self._draw([])
                    use_fallback = True
                    break
                elif key == "up":
                    if matches:
                        cursor = (cursor - 1) % len(matches)
                elif key == "down":
                    if matches:
                        cursor = (cursor + 1) % len(matches)
                elif key == "backspace":
                    filter_text = filter_text[:-1]
                elif len(key) == 1 and key.isprintable():
                    filter_text += key
        finally:
            if old_termios is not None:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_termios)
        if use_fallback:
            return self._fallback_select()

    def _fallback_select(self):
        while True:
            providers = [p for p, ids in self.groups.items() if ids]
            print("select provider:")
            for i, provider in enumerate(providers, 1):
                print(f"  [{i}] {provider}")
            choice = input("choice (number, blank to cancel): ").strip()
            if choice == "":
                return None
            try:
                idx = int(choice)
            except ValueError:
                print("invalid number")
                continue
            if not 1 <= idx <= len(providers):
                print("invalid number")
                continue
            provider = providers[idx - 1]
            model_ids = self.groups[provider]
            page = 0
            per_page = 20
            while True:
                total = len(model_ids)
                pages = max(1, (total + per_page - 1) // per_page)
                start = page * per_page
                end = min(start + per_page, total)
                print(f"models for {provider} (page {page + 1}/{pages}):")
                options = []
                for i in range(start, end):
                    options.append((f"[{i + 1}] {model_ids[i]}", ("model", i)))
                if page > 0:
                    options.append(("previous page", ("prev",)))
                if page < pages - 1:
                    options.append(("next page", ("next",)))
                options.append(("type a model id manually", ("manual",)))
                options.append(("back to providers", ("back",)))
                for j, (label, _) in enumerate(options, 1):
                    print(f"  [{j}] {label}")
                choice = input("choice (number, blank to go back): ").strip()
                if choice == "":
                    break
                try:
                    n = int(choice)
                except ValueError:
                    print("invalid number")
                    continue
                if not 1 <= n <= len(options):
                    print("invalid number")
                    continue
                _, action = options[n - 1]
                if action[0] == "model":
                    return f"{provider}/{model_ids[action[1]]}"
                if action[0] == "prev":
                    page -= 1
                elif action[0] == "next":
                    page += 1
                elif action[0] == "manual":
                    picked = self._manual_entry()
                    if picked is not None:
                        return picked
                elif action[0] == "back":
                    break

    def _manual_entry(self):
        while True:
            typed = input("type a model id (exact, e.g. provider/model): ").strip()
            if typed == "":
                return None
            if typed in self.models:
                return typed
            suggestions = difflib.get_close_matches(typed, self.models, n=5)
            print(f"'{typed}' is not a known model.")
            if suggestions:
                print("did you mean:")
                for i, suggestion in enumerate(suggestions, 1):
                    print(f"  [{i}] {suggestion}")
            print("pick a suggestion number, retype, or blank to go back to menus")
            choice = input("> ").strip()
            if choice == "":
                return None
            try:
                n = int(choice)
            except ValueError:
                continue
            if 1 <= n <= len(suggestions):
                return suggestions[n - 1]

    def _degraded_select(self):
        print("warning: `opencode models` failed; the model list is empty.")
        print("type a model id manually (unvalidated):")
        return input("model: ").strip() or None


def multiline_input(label, current):
    """Read multi-line input; a line containing only '.' ends it. Empty keeps current."""
    print(f"current {label}:")
    print(current if current else "(none)")
    print("enter new value; a line containing only '.' ends input (immediate '.' keeps existing)")
    lines = []
    while True:
        line = input()
        if line == ".":
            break
        lines.append(line)
    if not lines:
        return current
    return "\n".join(lines)


def print_agent_summary(name, agent):
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


def edit_one_agent(config, name, models):
    agent = config["agent"][name]
    print_agent_summary(name, agent)
    choice = input(
        f"[{name}] [1] keep  [2] edit model  [3] edit description  [4] edit prompt  [5] remove (Enter=keep): "
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
        prompt = multiline_input("prompt", agent.get("prompt"))
        if prompt is not None:
            agent["prompt"] = prompt
    elif choice == "5":
        confirm = input(f"remove agent '{name}'? [y/N]: ").strip().lower()
        if confirm == "y":
            del config["agent"][name]
    else:
        print("invalid choice")


def edit_agents(config, models):
    while True:
        for name in list(config.get("agent", {}).keys()):
            if name in config["agent"]:
                edit_one_agent(config, name, models)
        answer = input("edit another agent? (number/name, blank to continue): ").strip()
        if answer == "":
            break
        names = list(config.get("agent", {}).keys())
        if answer.isdigit():
            idx = int(answer) - 1
            if 0 <= idx < len(names):
                edit_one_agent(config, names[idx], models)
                continue
        elif answer in config.get("agent", {}):
            edit_one_agent(config, answer, models)
            continue
        print("no such agent")


def add_custom_agents(config, models):
    while True:
        answer = input("add a custom agent? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            break
        while True:
            name = input("agent name (kebab-case): ").strip()
            if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
                print("name must be kebab-case (lowercase letters, digits, single hyphens)")
                continue
            if name in config.get("agent", {}):
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
        prompt = multiline_input("prompt", None)
        agent = {"mode": mode, "model": picked}
        if description:
            agent["description"] = description
        if prompt:
            agent["prompt"] = prompt
        config.setdefault("agent", {})[name] = agent


def build_output(config, schema):
    """Return the config dict with $schema forced as the first key."""
    output = {"$schema": schema}
    for key, value in config.items():
        if key == "$schema":
            continue
        output[key] = value
    return output


def render_preview(config, schema):
    return json.dumps(build_output(config, schema), indent=2, ensure_ascii=False)


def validate_layer1(config):
    problems = []
    if "$schema" not in config:
        problems.append("missing $schema")
    if "small_model" in config and config["small_model"] is not None:
        if not (isinstance(config["small_model"], str) and "/" in config["small_model"]):
            problems.append("small_model must be a string containing '/'")
    default_agent = config.get("default_agent")
    if default_agent is not None:
        agents = config.get("agent") or {}
        if not isinstance(agents, dict) or default_agent not in agents:
            problems.append(f"default_agent '{default_agent}' is not a defined agent")
        elif agents[default_agent].get("mode") != "primary":
            problems.append(f"default_agent '{default_agent}' must reference a primary-mode agent")
    agents = config.get("agent")
    if agents is not None:
        if not isinstance(agents, dict):
            problems.append("agent must be an object")
        else:
            for name, agent in agents.items():
                if not isinstance(agent, dict):
                    problems.append(f"agent '{name}' is not an object")
                    continue
                if "model" in agent and not (
                    isinstance(agent["model"], str) and "/" in agent["model"]
                ):
                    problems.append(f"agent '{name}' model must be a string containing '/'")
                if "mode" in agent and agent["mode"] not in ("primary", "subagent", "all"):
                    problems.append(f"agent '{name}' mode must be primary/subagent/all")
    return problems


def warn_unknown_models(config, models):
    """Non-blocking warning when referenced models are not in the discovered list.

    Not blocking: `opencode models` may not list custom-provider models, and
    `opencode debug config` accepts unknown model ids, so this is advisory only.
    """
    if not models:
        return
    refs = []
    if isinstance(config.get("small_model"), str):
        refs.append(("small_model", config["small_model"]))
    for name, agent in (config.get("agent") or {}).items():
        if isinstance(agent, dict) and isinstance(agent.get("model"), str):
            refs.append((f"agent '{name}'", agent["model"]))
    for label, model in refs:
        if model not in models:
            print(f"warning: {label} model '{model}' is not in the discovered model list")


def validate_layer2(config):
    """Authoritative validation via `opencode debug config` (nothing written)."""
    data = json.dumps(config)
    if len(data) > 30000:
        print("warning: config exceeds 30000 chars; skipping opencode validation (Windows env limit)")
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


def validate(config):
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
        confirm = input("opencode validation unavailable. write anyway? [y/N]: ").strip().lower()
        return "ok" if confirm == "y" else "cancel"
    print("config is invalid per opencode.")
    choice = input("[1] edit again  [2] cancel: ").strip()
    return "edit" if choice == "1" else "cancel"


def atomic_write(path, content):
    """Write content to path via a temp file + os.replace so a failed write never truncates the target."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_config(target, config, schema, dry_run):
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
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
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
        print("note: opencode does not auto-load this file; rename or move it into place to use it.")
    else:
        print("cancelled; nothing written")


def parse_args():
    parser = argparse.ArgumentParser(description="Interactive opencode.json generator wizard")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--global",
        dest="global_",
        action="store_true",
        help="target ~/.config/opencode/opencode.json",
    )
    group.add_argument("--dir", help="project directory (default: cwd)")
    parser.add_argument("--dry-run", action="store_true", help="show preview + validate, write nothing")
    return parser.parse_args()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    if args.global_:
        target = Path.home() / ".config" / "opencode" / "opencode.json"
    elif args.dir:
        target = resolve_project_target(Path(args.dir).expanduser())
    else:
        print("where should the config be written?")
        print("  [1] project (a directory in this repo or elsewhere)")
        print("  [2] global (~/.config/opencode/opencode.json)")
        choice = input("choice [1]: ").strip() or "1"
        if choice == "2":
            target = Path.home() / ".config" / "opencode" / "opencode.json"
        else:
            directory = input(f"project directory [{os.getcwd()}]: ").strip() or os.getcwd()
            target = resolve_project_target(Path(directory))

    print(f"target: {target}" + (" (exists)" if target.exists() else " (does not exist)"))

    models = discover_models()
    if models:
        for provider, ids in group_models(models).items():
            print(f"  {provider}: {len(ids)} models")
    else:
        print("  (no models discovered)")

    defaults = json.loads((Path(__file__).parent / "default-agents.json").read_text(encoding="utf-8"))
    existing = {}
    if target.exists():
        try:
            parsed = json.loads(strip_jsonc(target.read_text(encoding="utf-8-sig")))
            if not isinstance(parsed, dict):
                print("warning: existing config is not a JSON object; starting from defaults")
            else:
                if not isinstance(parsed.get("agent"), dict) and "agent" in parsed:
                    print("warning: existing 'agent' is not an object; using default agents")
                    del parsed["agent"]
                existing = parsed
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            print(f"warning: could not parse existing config ({exc}); starting from defaults")
    config = deep_merge(defaults, existing)
    schema = existing.get("$schema", CONFIG_SCHEMA)
    config["$schema"] = schema

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
        answer = input("no small_model set. Enter to skip, or type anything to set one: ").strip()
        if answer != "":
            picked = ModelPicker(models, None).select()
            if picked:
                config["small_model"] = picked

    print("\n-- default_agent --")
    primary_agents = [
        name
        for name, agent in config.get("agent", {}).items()
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