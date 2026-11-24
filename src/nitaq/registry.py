"""The documented list of supported agents (data/supported_agents.json)."""
from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


def load_registry() -> dict:
    """Repository copy first (a checkout), then the copy shipped in the package."""
    here = Path(__file__).resolve()
    repo = here.parents[2] / "data" / "supported_agents.json"
    if repo.exists():
        return json.loads(repo.read_text(encoding="utf-8"))
    return json.loads(resources.files("nitaq").joinpath("_data/supported_agents.json").read_text(encoding="utf-8"))


def current_os() -> str:
    s = platform.system().lower()
    return {"darwin": "macos", "windows": "windows"}.get(s, "linux")


def default_home() -> Path:
    return Path(os.path.expanduser("~"))


@dataclass(frozen=True)
class Location:
    agent: str
    agent_name: str
    id: str
    scope: str
    kind: str
    path: Path
    format: str | None


def resolve_locations(reg: dict, home: Path, project: Path | None,
                      agents: tuple[str, ...] | None = None) -> list[Location]:
    out = []
    for a in reg["agents"]:
        if agents and a["id"] not in agents:
            continue
        for loc in a["locations"]:
            raw = loc["path"]
            if raw.startswith("{project}"):
                if project is None:
                    continue
                p = project / raw[len("{project}/"):]
            elif raw.startswith("~/"):
                p = home / raw[2:]
            else:
                continue  # only home- or project-relative paths are allowed
            out.append(Location(a["id"], a["name"], loc["id"], loc["scope"], loc["kind"], p, loc.get("format")))
    return out


def mechanisms(reg: dict, agent: str) -> list[dict]:
    for a in reg["agents"]:
        if a["id"] == agent:
            return a.get("mechanisms", [])
    return []
