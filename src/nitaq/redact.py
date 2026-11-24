"""Never print secrets: env values, headers and secret-looking arguments are redacted."""
from __future__ import annotations

import re
from pathlib import Path

_SECRET_PATTERNS = [
    re.compile(r"^(sk|pk|rk)-[A-Za-z0-9_-]{16,}$"),          # API keys (sk-..., sk-ant-...)
    re.compile(r"^gh[pousr]_[A-Za-z0-9]{20,}$"),               # GitHub tokens
    re.compile(r"^xox[abpr]-[A-Za-z0-9-]{10,}$"),              # Slack tokens
    re.compile(r"^AKIA[0-9A-Z]{16}$"),                         # AWS access key id
    re.compile(r"^AIza[0-9A-Za-z_-]{30,}$"),                   # Google API key
    re.compile(r"^eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
    re.compile(r"^[A-Fa-f0-9]{32,}$"),                         # long hex
    re.compile(r"^[A-Za-z0-9+/_-]{40,}={0,2}$"),               # long base64-ish
]
_SECRET_FLAG = re.compile(r"(token|secret|password|passwd|api[-_]?key|auth|credential|bearer)", re.I)
SECRET_NAME = re.compile(r"(token|secret|password|passwd|key|auth|credential|cookie|session)", re.I)


def looks_secret(value: str) -> bool:
    v = value.strip()
    if len(v) < 16 or "/" in v and not v.startswith(("ey", "sk-")) and v.count("/") > 2:
        return False
    return any(p.match(v) for p in _SECRET_PATTERNS)


def redact_args(args: list) -> tuple[list[str], int]:
    """Redact secret-looking arguments and values that follow a --token style flag."""
    out, n, prev_flag = [], 0, False
    for a in args:
        s = str(a)
        key, sep, val = s.partition("=")
        if prev_flag or looks_secret(s):
            out.append(f"<redacted:{len(s)} chars>")
            n += 1
        elif sep and s.startswith("-") and _SECRET_FLAG.search(key):
            out.append(f"{key}=<redacted:{len(val)} chars>")
            n += 1
        elif sep and looks_secret(val):
            out.append(f"{key}=<redacted:{len(val)} chars>")
            n += 1
        else:
            out.append(s)
        prev_flag = s.startswith("-") and not sep and bool(_SECRET_FLAG.search(s))
    return out, n


_PROJECT: list[Path] = []


def set_project(project: Path | None) -> None:
    _PROJECT[:] = [Path(project)] if project else []


def display_path(p: Path, home: Path) -> str:
    for proj in _PROJECT:
        try:
            return "<project>/" + str(Path(p).relative_to(proj)).replace("\\", "/")
        except ValueError:
            pass
    try:
        return "~/" + str(Path(p).relative_to(home)).replace("\\", "/")
    except ValueError:
        return str(p)


_KV = re.compile(r'^(?P<pre>[ +\-]?\s*)"(?P<key>[^"]+)"(?P<mid>\s*:\s*)"(?P<val>(?:[^"\\]|\\.)*)"(?P<post>,?\s*)$')
_ITEM = re.compile(r'^(?P<pre>[ +\-]?\s*)"(?P<val>(?:[^"\\]|\\.)*)"(?P<post>,?\s*)$')


def mask_diff_line(line: str, state: dict) -> str:
    """Mask secret values in one line of a JSON diff (display only)."""
    m = _KV.match(line)
    if m:
        key, val = m.group("key"), m.group("val")
        state["prev_flag"] = False
        if (SECRET_NAME.search(key) and not val.startswith("$")) or looks_secret(val):
            state["masked"] += 1
            return f'{m.group("pre")}"{key}"{m.group("mid")}"<redacted:{len(val)} chars>"{m.group("post")}'
        return line
    m = _ITEM.match(line)
    if m:
        val = m.group("val")
        flagged = state.get("prev_flag", False)
        state["prev_flag"] = val.startswith("-") and bool(_SECRET_FLAG.search(val))
        if flagged or looks_secret(val):
            state["masked"] += 1
            return f'{m.group("pre")}"<redacted:{len(val)} chars>"{m.group("post")}'
    return line
