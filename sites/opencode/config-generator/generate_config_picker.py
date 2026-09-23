"""Terminal key reading and the interactive model picker for generate-config.py."""

from __future__ import annotations

import difflib
import os
import sys
from collections.abc import Sequence
from typing import Any

from generate_config_opencode import group_models

# Each of these exists on only one platform. Declaring the names as Any keeps
# mypy --strict clean whichever platform it runs on: the guarded import is the
# real binding and mypy skips whichever branch is unreachable here.
msvcrt: Any = None
select: Any = None
termios: Any = None
tty: Any = None

if sys.platform == "win32":
    import msvcrt as _msvcrt

    msvcrt = _msvcrt
else:
    import select as _select
    import termios as _termios
    import tty as _tty

    select = _select
    termios = _termios
    tty = _tty


def read_key() -> str:
    """Read one keypress; returns a control token or a printable character."""
    if sys.platform == "win32":
        return _read_key_nt()
    return _read_key_posix()


def _read_key_nt() -> str:
    """Windows half of read_key: decode one msvcrt keypress."""
    ch: str = msvcrt.getwch()
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


def _read_key_posix() -> str:
    """POSIX half of read_key: decode one stdin keypress, including escape sequences."""
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

    def __init__(self, models: Sequence[str], current: str | None = None) -> None:
        self.models = models
        self.current = current
        self.groups = group_models(models)
        self._drawn = 0

    def select(self) -> str | None:
        if not self.models:
            return self._degraded_select()
        if sys.stdin.isatty():
            return self._primary_select()
        return self._fallback_select()

    def _draw(self, lines: Sequence[str]) -> None:
        if self._drawn:
            sys.stdout.write("\x1b[1A\r\x1b[K" * self._drawn)
        for line in lines:
            sys.stdout.write(line + "\n")
        self._drawn = len(lines)
        sys.stdout.flush()

    def _picker_lines(
        self, filter_text: str, matches: list[str], cursor: int
    ) -> list[str]:
        """Build the menu lines for the current filter and cursor position."""
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
        return lines

    def _apply_key(
        self, key: str, filter_text: str, cursor: int, match_count: int
    ) -> tuple[str, int]:
        """Apply one movement/edit key; returns the updated (filter_text, cursor)."""
        if key == "up" and match_count:
            cursor = (cursor - 1) % match_count
        elif key == "down" and match_count:
            cursor = (cursor + 1) % match_count
        elif key == "backspace":
            filter_text = filter_text[:-1]
        elif len(key) == 1 and key.isprintable():
            filter_text += key
        return filter_text, cursor

    def _primary_select(self) -> str | None:
        if sys.platform == "win32":
            os.system("")
        filter_text = ""
        cursor = 0
        if self.current in self.models:
            cursor = self.models.index(self.current)
        self._drawn = 0
        old_termios: list[Any] | None = None
        use_fallback = False
        try:
            if sys.platform != "win32":
                old_termios = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
            while True:
                matches = [m for m in self.models if filter_text.lower() in m.lower()]
                if cursor >= len(matches):
                    cursor = max(0, len(matches) - 1)
                self._draw(self._picker_lines(filter_text, matches, cursor))
                key = read_key()
                if key == "enter" and matches:
                    self._draw([])
                    return matches[cursor]
                if key == "esc":
                    self._draw([])
                    use_fallback = True
                    break
                filter_text, cursor = self._apply_key(
                    key, filter_text, cursor, len(matches)
                )
        finally:
            if old_termios is not None:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_termios)
        if use_fallback:
            return self._fallback_select()
        return None

    def _fallback_select(self) -> str | None:
        while True:
            provider = self._pick_provider()
            if provider is None:
                return None
            picked = self._browse_models(provider, self.groups[provider])
            if picked is not None:
                return picked

    def _pick_provider(self) -> str | None:
        """Show the provider menu; return the chosen provider, or None to cancel."""
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
            return providers[idx - 1]

    def _browse_models(self, provider: str, model_ids: list[str]) -> str | None:
        """Page through one provider's models; None means go back to providers."""
        page = 0
        while True:
            pages, options = self._page_options(model_ids, page)
            print(f"models for {provider} (page {page + 1}/{pages}):")
            for j, (label, _) in enumerate(options, 1):
                print(f"  [{j}] {label}")
            choice = input("choice (number, blank to go back): ").strip()
            if choice == "":
                return None
            try:
                n = int(choice)
            except ValueError:
                print("invalid number")
                continue
            if not 1 <= n <= len(options):
                print("invalid number")
                continue
            _, action = options[n - 1]
            tag, index = action
            if tag == "model":
                return f"{provider}/{model_ids[index]}"
            if tag == "prev":
                page -= 1
            elif tag == "next":
                page += 1
            elif tag == "manual":
                picked = self._manual_entry()
                if picked is not None:
                    return picked
            elif tag == "back":
                return None

    def _page_options(
        self, model_ids: list[str], page: int
    ) -> tuple[int, list[tuple[str, tuple[str, int]]]]:
        """Build one page of (label, action) rows.

        The action index is only meaningful for "model" rows; the rest use 0 so
        every action is one uniform (tag, index) pair.
        """
        per_page = 20
        total = len(model_ids)
        pages = max(1, (total + per_page - 1) // per_page)
        start = page * per_page
        end = min(start + per_page, total)
        options: list[tuple[str, tuple[str, int]]] = []
        for i in range(start, end):
            options.append((f"[{i + 1}] {model_ids[i]}", ("model", i)))
        if page > 0:
            options.append(("previous page", ("prev", 0)))
        if page < pages - 1:
            options.append(("next page", ("next", 0)))
        options.append(("type a model id manually", ("manual", 0)))
        options.append(("back to providers", ("back", 0)))
        return pages, options

    def _manual_entry(self) -> str | None:
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

    def _degraded_select(self) -> str | None:
        print("warning: `opencode models` failed; the model list is empty.")
        print("type a model id manually (unvalidated):")
        return input("model: ").strip() or None


def multiline_input(label: str, current: str | None) -> str | None:
    """Read multi-line input; a line containing only '.' ends it. Empty keeps current."""
    print(f"current {label}:")
    print(current if current else "(none)")
    print(
        "enter new value; a line containing only '.' ends input (immediate '.' keeps existing)"
    )
    lines: list[str] = []
    while True:
        line = input()
        if line == ".":
            break
        lines.append(line)
    if not lines:
        return current
    return "\n".join(lines)
