"""D1: English keyword blocklist (naive baseline).

Written in the style of public keyword heuristics for prompt injection
(verb x qualifier x object phrases such as "ignore previous instructions"),
re-implemented here from scratch.  It lower-cases the text and collapses
whitespace; it does NOT normalise Unicode, decode anything, or know any
language other than English.  That is the point of the baseline.

FROZEN at git tag `freeze-scanner`.  Any later edit must be recorded in CHANGELOG.md.
"""
from __future__ import annotations

import re

from nitaq_bench.defenses.base import Defense, ScreenVerdict

_VERBS = (
    "ignore", "disregard", "skip", "forget", "neglect", "overlook", "omit", "bypass",
    "pay no attention to", "do not follow", "don't follow", "do not obey", "don't obey",
)
_DETERMINERS = ("all", "any", "the", "your", "my", "these", "those", "of", "every")
_QUALIFIERS = ("prior", "previous", "preceding", "above", "foregoing", "earlier", "initial", "original")
_OBJECTS = (
    "content", "text", "instructions", "instruction", "directives", "directive", "commands",
    "command", "context", "conversation", "input", "inputs", "data", "message", "messages",
    "communication", "response", "responses", "request", "requests", "prompt", "prompts",
    "rules", "rule", "guidelines", "orders",
)
_PHRASES = (
    "system prompt", "new instructions", "you are now", "do not tell the user",
    "don't tell the user", "do not inform the user", "without telling the user",
    "without informing the user", "do not mention this to the user", "exfiltrate",
    "developer mode", "jailbreak",
)

_alt = lambda xs: "(?:" + "|".join(re.escape(x) for x in sorted(xs, key=len, reverse=True)) + ")"
_OVERRIDE_RE = re.compile(
    r"\b" + _alt(_VERBS) + r"\s+(?:" + _alt(_DETERMINERS) + r"\s+){0,3}(?:" + _alt(_QUALIFIERS)
    + r"\s+)?" + _alt(_OBJECTS) + r"\b"
)


class D1Keyword(Defense):
    name = "D1"
    kind = "scanner"
    description = "English keyword blocklist (naive baseline, no normalisation)."

    def screen(self, text: str, source: str) -> ScreenVerdict:
        low = re.sub(r"\s+", " ", text.lower())
        reasons = []
        m = _OVERRIDE_RE.search(low)
        if m:
            reasons.append({"rule": "override_phrase", "match": m.group(0)})
        for p in _PHRASES:
            if p in low:
                reasons.append({"rule": "blocklist_phrase", "match": p})
        return ScreenVerdict(bool(reasons), float(len(reasons)), reasons, self.name)
