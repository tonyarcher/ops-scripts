"""`opencode` CLI bridge and model discovery for generate-config.py."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Iterable, Sequence

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def run_opencode(
    args: Sequence[str],
    timeout: float = 60,
    env_override: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run opencode with an explicit argv list. Resolves the Windows shim."""
    env: dict[str, str] | None = None
    if env_override is not None:
        env = os.environ.copy()
        env["OPENCODE_CONFIG_CONTENT"] = env_override

    def _run(cmd: list[str]) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            cmd, capture_output=True, timeout=timeout, env=env, check=False
        )

    try:
        result = _run(["opencode", *args])
    except FileNotFoundError:
        exe = shutil.which("opencode")
        if exe is None:
            raise
        result = _run([exe, *args])
    # capture_output=True always yields bytes; the Optional type still needs narrowing.
    stdout = (result.stdout or b"").decode("utf-8", errors="replace")
    stderr = (result.stderr or b"").decode("utf-8", errors="replace")
    return subprocess.CompletedProcess(result.args, result.returncode, stdout, stderr)


def discover_models() -> list[str]:
    """Return the deduped, ordered list of provider/model ids from `opencode models`."""
    try:
        result = run_opencode(["models"], timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"warning: could not run `opencode models`: {exc}")
        return []
    if result.returncode != 0:
        print("warning: `opencode models` failed")
        return []
    models: list[str] = []
    seen: set[str] = set()
    for line in (result.stdout or "").splitlines():
        line = ANSI_ESCAPE.sub("", line).strip()
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", line) or line in seen:
            continue
        seen.add(line)
        models.append(line)
    return models


def group_models(models: Iterable[str]) -> dict[str, list[str]]:
    """Group model ids into an ordered dict provider -> [model ids]."""
    groups: dict[str, list[str]] = {}
    for model in models:
        provider, _, model_id = model.partition("/")
        groups.setdefault(provider, []).append(model_id)
    return groups
