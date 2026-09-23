#!/usr/bin/env python3
"""Verify entry point: run every formatter and linter in check mode.

Run: `python3 verify.py [--fix] [--strict]` (usually `python verify.py` on
Windows). Covers every format this repo owns: Python (ruff, mypy), shell
(shfmt, shellcheck), TOML (taplo), Dockerfile (hadolint), PowerShell
(PSScriptAnalyzer) and the JSON/YAML/MD docs (prettier). `--fix` applies the
formatters instead of checking. `--strict` treats a missing tool as a failure
rather than a skip.

Only stdlib is used (subprocess, sys, pathlib, shutil).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HELP = """Run every formatter and linter in check mode.

Usage:
  python verify.py [--fix] [--strict]

Also:
  python verify.py --fix     apply the formatters instead of checking
  python verify.py --strict  a missing tool is a failure, not a skip

Tools: ruff, mypy, shfmt, shellcheck, taplo, hadolint, prettier,
pwsh (PSScriptAnalyzer). Installed by windows/scripts/install-tools.ps1,
dotfiles/setup.sh --install-tools, and macos/install-tools.sh.
""".strip()

# Generated and vendored trees. Anything with one of these path parts is
# skipped, so caches never get linted as if they were source.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".idea",
        ".mypy_cache",
        ".ruff_cache",
        "__pycache__",
        "node_modules",
        "tmp",
        "var",
    }
)

# Rough ceiling on one command line. A .bat/.cmd shim routes through cmd.exe,
# which caps near 8k characters, so paths are packed by length not by count.
BUDGET = 5000

PYTHON = (".py", ".pyi")
SHELL = (".sh",)
TOML = (".toml",)
YAML = (".yml", ".yaml")
POWERSHELL = (".ps1", ".psm1")
SOURCE_SUFFIXES = frozenset(
    {
        ".py",
        ".pyi",
        ".sh",
        ".ps1",
        ".psm1",
        ".ts",
        ".js",
        ".mjs",
        ".json",
        ".yml",
        ".yaml",
        ".toml",
        ".md",
    }
)

Check = tuple[str, str, list[str]]

# Shared file-length budget. Only oxlint (`max-lines`) and detekt
# (`LargeClass`) can express it natively; ruff, pylint's C0302, and ktlint
# are either absent or cannot, so this check covers every source file.
MAX_FILE_LINES = 500


def collect(root: Path) -> list[Path]:
    """Every file in the repo minus generated and vendored trees."""
    kept: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if set(path.relative_to(root).parts) & SKIP_DIRS:
            continue
        kept.append(path)
    return kept


def by_suffix(files: list[Path], suffixes: tuple[str, ...]) -> list[str]:
    """Absolute paths of the files carrying one of the given suffixes."""
    return [str(path) for path in files if path.suffix.lower() in suffixes]


def named(files: list[Path], names: tuple[str, ...]) -> list[str]:
    """Absolute paths of the files whose base name is one of the given names."""
    return [str(path) for path in files if path.name in names]


def quote(path: str) -> str:
    """Single-quote a path for an inline PowerShell string literal."""
    return "'" + path.replace("'", "''") + "'"


def analyzer_argv(paths: list[str], settings: str | None) -> list[str]:
    """One pwsh invocation that analyses every PowerShell file at once."""
    listed = ", ".join(quote(path) for path in paths)
    extra = " -Settings " + quote(settings) if settings else ""
    call = " | ForEach-Object { Invoke-ScriptAnalyzer -Path $_" + extra + " }); "
    scan = "$r = @(" + listed + call
    report = (
        "$r | Format-Table RuleName,Severity,ScriptName,Line -AutoSize | Out-String "
    )
    script = scan + report + "| Write-Host; if ($r.Count -gt 0) { exit 1 }; exit 0"
    return ["pwsh", "-NoProfile", "-Command", script]


def analyzer_settings(root: Path) -> str | None:
    """The repo's PSScriptAnalyzer settings file, when it has one."""
    for candidate in (
        root / "PSScriptAnalyzerSettings.psd1",
        root / "windows" / "PSScriptAnalyzerSettings.psd1",
    ):
        if candidate.exists():
            return str(candidate)
    return None


def overlong(files: list[Path], limit: int = MAX_FILE_LINES) -> list[tuple[str, int]]:
    """Source files over the shared length budget, longest first.

    Counts non-blank lines so the number matches oxlint `max-lines` with
    `skipBlankLines: true`; two checkers must not report different counts.
    """
    tall = [
        (
            str(path),
            sum(
                1
                for line in path.open(encoding="utf-8", errors="replace")
                if line.strip()
            ),
        )
        for path in files
        if path.suffix.lower() in SOURCE_SUFFIXES
    ]
    return sorted((x for x in tall if x[1] > limit), key=lambda x: -x[1])


def multi(label: str, tool: str, head: list[str], paths: list[str]) -> list[Check]:
    """One check per batch of paths, so no single command line overflows."""
    if not paths:
        return []
    fixed = sum(len(part) for part in head)
    groups: list[list[str]] = []
    current: list[str] = []
    used = fixed
    for path in paths:
        if current and used + len(path) > BUDGET:
            groups.append(current)
            current = []
            used = fixed
        current.append(path)
        used += len(path) + 1
    if current:
        groups.append(current)
    total = len(groups)
    return [
        (label if total == 1 else f"{label}[{index}]", tool, [*head, *group])
        for index, group in enumerate(groups, start=1)
    ]


def specs(root: Path, files: list[Path], fix: bool) -> list[Check]:
    """Label, executable and argv for each check, in run order."""
    flag = ["--fix"] if fix else []
    edit = ["-w"] if fix else ["-d"]
    entries: list[Check] = [
        ("ruff-check", "ruff", ["ruff", "check", *flag, "."]),
        ("ruff-format", "ruff", ["ruff", "format", *([] if fix else ["--check"]), "."]),
        ("prettier", "prettier", ["prettier", "--write" if fix else "--check", "."]),
    ]
    entries += multi("mypy", "mypy", ["mypy", "--strict"], by_suffix(files, PYTHON))
    entries += multi("shfmt", "shfmt", ["shfmt", *edit], by_suffix(files, SHELL))
    entries += multi(
        "shellcheck", "shellcheck", ["shellcheck"], by_suffix(files, SHELL)
    )
    entries += multi(
        "hadolint", "hadolint", ["hadolint"], named(files, ("Dockerfile",))
    )
    entries += multi("yamllint", "yamllint", ["yamllint"], by_suffix(files, YAML))
    if fix:
        entries += multi("taplo", "taplo", ["taplo", "fmt"], by_suffix(files, TOML))
    else:
        entries += multi(
            "taplo", "taplo", ["taplo", "fmt", "--check"], by_suffix(files, TOML)
        )
    # Check-only tools run in both modes: --fix applies formatters but still
    # reports what it cannot fix, instead of exiting 0 unchecked.
    powershell = by_suffix(files, POWERSHELL)
    if powershell:
        entries.append(
            (
                "psscriptanalyzer",
                "pwsh",
                analyzer_argv(powershell, analyzer_settings(root)),
            )
        )
    return entries


def execute(argv: list[str], root: Path) -> tuple[int, str]:
    """Run one tool and report its exit code plus trimmed output.

    argv[0] is a bare name; CreateProcess does not apply PATHEXT the way
    shutil.which does, so the .cmd/.bat shim has to be passed explicitly.
    """
    resolved = shutil.which(argv[0]) or argv[0]
    result = subprocess.run(
        [resolved, *argv[1:]],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode, (result.stdout + result.stderr).strip()


def main(argv: list[str]) -> int:
    """Run every check and summarise pass, fail and skip."""
    if any(arg in ("-h", "--help") for arg in argv):
        print(HELP)
        return 0
    fix = "--fix" in argv
    strict = "--strict" in argv
    root = Path(__file__).resolve().parent
    missing: list[str] = []
    failed: list[str] = []
    sources = collect(root)
    long = overlong(sources)
    if long:
        print(f"FAIL max-lines (over {MAX_FILE_LINES} non-blank lines)")
        failed.append("max-lines")
        for path, lines in long:
            print(f"  {lines:5d}  {path}")
    else:
        print(f"PASS max-lines (nothing over {MAX_FILE_LINES} non-blank lines)")
    for label, tool, command in specs(root, sources, fix):
        if shutil.which(tool) is None:
            print(f"SKIP {label} ({tool} not on PATH)")
            missing.append(label)
            continue
        code, output = execute(command, root)
        if code == 0:
            print(f"PASS {label}")
            continue
        print(f"FAIL {label}")
        failed.append(label)
        if output:
            print(output)
    print(f"\n{len(failed)} failed, {len(missing)} skipped")
    if missing:
        print("skipped (install via the installers): " + ", ".join(missing))
    if failed:
        return 1
    return 1 if (strict and missing) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
