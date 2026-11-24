"""Per-session store of hosts seen in untrusted tool output (Claude Code taint mode).

Stores ONLY host names (never content), one small JSON file per session under
~/.nitaq/taint/, keyed by a hash of the session id; files older than 24 h are
removed.  Written only when the policy's destination_mode is "taint".
Assumption (not stated explicitly in the docs read): `session_id` is the same
for all hook events of one Claude Code session; if it is not, taint simply does
not carry over (the policy then behaves like taint mode with an empty set).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

MAX_AGE_S = 24 * 3600
MAX_HOSTS = 5000


def _dir(home: Path) -> Path:
    return home / ".nitaq" / "taint"


def _file(home: Path, session_id: str) -> Path:
    return _dir(home) / (hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24] + ".json")


def load(home: Path, session_id: str) -> set[str]:
    p = _file(home, session_id or "no-session")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if time.time() - d.get("updated", 0) > MAX_AGE_S:
        return set()
    return set(d.get("hosts", []))


def add(home: Path, session_id: str, hosts: set[str]) -> None:
    if not hosts:
        return
    d = _dir(home)
    d.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for f in d.glob("*.json"):
        try:
            if now - f.stat().st_mtime > MAX_AGE_S:
                f.unlink()
        except OSError:
            pass
    cur = load(home, session_id)
    merged = sorted(cur | hosts)[:MAX_HOSTS]
    p = _file(home, session_id or "no-session")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"updated": now, "hosts": merged}), encoding="utf-8")
    os.replace(tmp, p)
