"""Defense interface.

A defense has two hooks, both optional:
  screen(text, source)  -> ScreenVerdict   content hook (scanners D1..D4)
  authorize(tool, args, manifest, is_tainted) -> Decision   action hook (guard D5)

The action hook receives a tool name, its arguments, the task manifest and a
boolean taint oracle.  It is never handed page, email, skill or tool
description text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ScreenVerdict:
    flagged: bool = False
    score: float = 0.0
    reasons: list[dict] = field(default_factory=list)
    defense: str = ""

    def to_dict(self) -> dict:
        return {"flagged": self.flagged, "score": round(self.score, 3),
                "reasons": self.reasons, "defense": self.defense}


@dataclass
class Decision:
    allowed: bool = True
    rule: str = ""
    detail: str = ""
    defense: str = ""

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "rule": self.rule, "detail": self.detail,
                "defense": self.defense}


class Defense:
    name = "D0"
    kind = "none"          # none | scanner | guard
    description = "No defense."

    def available(self) -> tuple[bool, str]:
        return True, ""

    def screen(self, text: str, source: str) -> ScreenVerdict:
        return ScreenVerdict(False, defense=self.name)

    def authorize(self, tool: str, args: dict[str, Any], manifest: Any,
                  is_tainted: Callable[[object], bool]) -> Decision:
        return Decision(True, defense=self.name)


class DefenseStack:
    """Several defenses applied together (e.g. "D2+D5")."""

    def __init__(self, defenses: list[Defense], name: str | None = None) -> None:
        self.defenses = defenses
        self.name = name or "+".join(d.name for d in defenses)

    def screen(self, text: str, source: str) -> ScreenVerdict:
        merged = ScreenVerdict(False, defense=self.name)
        for d in self.defenses:
            v = d.screen(text, source)
            if v.flagged:
                merged.flagged = True
                merged.score = max(merged.score, v.score)
                merged.reasons.extend(v.reasons)
                merged.defense = d.name
        return merged

    def authorize(self, tool: str, args: dict[str, Any], manifest: Any,
                  is_tainted: Callable[[object], bool]) -> Decision:
        for d in self.defenses:
            dec = d.authorize(tool, args, manifest, is_tainted)
            if not dec.allowed:
                return dec
        return Decision(True, defense=self.name)
