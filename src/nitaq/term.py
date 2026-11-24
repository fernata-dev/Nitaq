"""Tiny terminal helpers: colours (respecting NO_COLOR / --no-color / non-TTY)."""
from __future__ import annotations

import os
import sys

_ON = True


def set_color(enabled: bool | None) -> None:
    global _ON
    if enabled is None:
        enabled = sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
    _ON = bool(enabled)


def c(text: str, *styles: str) -> str:
    if not _ON:
        return text
    codes = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33", "blue": "34",
             "magenta": "35", "cyan": "36", "grey": "90", "bred": "1;31", "bgreen": "1;32", "byellow": "1;33"}
    seq = ";".join(codes[s] for s in styles if s in codes)
    return f"\033[{seq}m{text}\033[0m" if seq else text


SEV_STYLE = {"high": ("bred",), "medium": ("byellow",), "low": ("cyan",), "info": ("grey",)}


def sev(s: str) -> str:
    return c(s.upper().ljust(6), *SEV_STYLE.get(s, ()))


def rule(title: str = "") -> str:
    line = "─" * 72
    return c(f"── {title} " + line[len(title) + 4:], "dim") if title else c(line, "dim")
