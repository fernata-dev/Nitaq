"""Build defenses by name.  "A+B" builds a stack applying both."""
from __future__ import annotations

from nitaq_bench.defenses.base import Defense, DefenseStack


def _single(name: str, llm_client=None) -> Defense:
    if name == "D0":
        from nitaq_bench.defenses.d0_none import D0None
        return D0None()
    if name == "D1":
        from nitaq_bench.defenses.d1_keyword import D1Keyword
        return D1Keyword()
    if name == "D2":
        from nitaq_bench.defenses.d2_scanner import D2Scanner
        return D2Scanner()
    if name == "D3":
        from nitaq_bench.defenses.d3_llm_judge import D3LLMJudge
        return D3LLMJudge(llm_client)
    if name == "D4":
        from nitaq_bench.defenses.d4_cpt import D4CharsPerToken
        return D4CharsPerToken()
    if name in ("D5", "D5-tools", "D5-args", "D5-taint", "D6"):
        from nitaq_bench.defenses.d5_guard import D5Guard
        return D5Guard.variant(name)
    raise KeyError(f"unknown defense: {name}")


def build(name: str, llm_client=None) -> DefenseStack:
    parts = [p.strip() for p in name.split("+") if p.strip()]
    return DefenseStack([_single(p, llm_client) for p in parts], name=name)


def availability(name: str, llm_client=None) -> tuple[bool, str]:
    try:
        stack = build(name, llm_client)
    except (KeyError, ImportError) as exc:
        return False, str(exc)
    for d in stack.defenses:
        ok, why = d.available()
        if not ok:
            return False, f"{d.name}: {why}"
    return True, ""


# Defenses the worst-case simulator runs by default.  D3 needs a real model
# and D4 needs a tokenizer; both are attempted only when available.
SIM_DEFAULT = ("D0", "D1", "D2", "D4", "D5-tools", "D5-args", "D5-taint", "D5", "D2+D5", "D6")
LLM_DEFAULT = ("D0", "D1", "D2", "D5")
