"""Agent interface.  An agent drives an Episode by calling `episode.call(tool, args)`."""
from __future__ import annotations


class Agent:
    name = "agent"
    simulated = False
    label = ""

    def info(self) -> dict:
        return {"name": self.name, "simulated": self.simulated, "label": self.label,
                "model": None, "version": None, "temperature": None, "endpoint": None}

    def run(self, episode) -> None:  # pragma: no cover - interface
        raise NotImplementedError
