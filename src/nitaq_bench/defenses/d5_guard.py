"""D5: task-bound capability guard.

The guard decides on ACTIONS, not on text.  `authorize` receives:
  tool      the tool name the agent wants to call
  args      the call's arguments
  manifest  the task's permission manifest (written by the task author)
  is_tainted a boolean oracle: "did this exact value come from untrusted content?"
It never receives page, email, skill or tool-description text, so its decision
cannot depend on the language, dialect, script or encoding of an injection.
(tests/test_guard.py checks this structurally and behaviourally.)

Rules (each can be switched on separately for ablation):
  tools  tool must be in manifest.allowed_tools
  args   arguments must satisfy manifest.arg_constraints (in / equals / prefix);
         path-like values are normalised first, so "notes/../secrets" fails "notes/"
  taint  destination/resource arguments (TAINT_PROTECTED_ARGS) must not be
         values that appear only in untrusted content

What it cannot do (measured as residual risk, never hidden):
  * stop the model from being fooled or from following the injection;
  * stop harmful content inside an allowed call (in_scope_tamper);
  * restore the user's task after a hijack (availability is not protected).
"""
from __future__ import annotations

import posixpath
from typing import Any, Callable

from nitaq_bench.defenses.base import Decision, Defense
from nitaq_bench.env.tasks import TAINT_PROTECTED_ARGS, Manifest

VARIANTS = {
    "D5-tools": ("tools",),
    "D5-args": ("tools", "args"),
    "D5-taint": ("tools", "taint"),
    "D5": ("tools", "args", "taint"),
    # m13: taint after undoing character-level obfuscation (see env/taint.py; designed after
    # D5-taint's dev AND test numbers were visible, so its test result is not held-out evidence)
    "D6": ("tools", "ntaint"),
}


def _norm_path(v: str) -> str | None:
    if "\\" in v or v.startswith("/") or "\x00" in v:
        return None
    n = posixpath.normpath(v)
    if n.startswith("..") or "/../" in f"/{n}/":
        return None
    return n


def check_constraint(value: Any, c: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, str):
        return False, "argument is not a string"
    if "equals" in c:
        return (value == c["equals"]), f"must equal {c['equals']!r}"
    if "in" in c:
        return (value in c["in"]), f"must be one of {list(c['in'])!r}"
    if "prefix" in c:
        n = _norm_path(value)
        ok = n is not None and n == value.rstrip("/") and n.startswith(c["prefix"])
        return ok, f"must be a normalised path under {c['prefix']!r}"
    return False, "unknown constraint"


class D5Guard(Defense):
    kind = "guard"

    def __init__(self, rules: tuple[str, ...] = ("tools", "args", "taint"), name: str = "D5") -> None:
        self.rules = rules
        self.name = name
        self.description = "Capability guard: " + " + ".join(
            {"tools": "task tool allowlist", "args": "argument constraints",
             "taint": "untrusted values cannot pick destinations",
             "ntaint": "untrusted values cannot pick destinations, even when obfuscated"}[r] for r in rules)

    @classmethod
    def variant(cls, name: str) -> "D5Guard":
        return cls(VARIANTS[name], name)

    def authorize(self, tool: str, args: dict[str, Any], manifest: Manifest,
                  is_tainted: Callable[[object], bool]) -> Decision:
        if "tools" in self.rules and tool not in manifest.allowed_tools:
            return Decision(False, "tool_not_allowed",
                            f"{tool} not in {list(manifest.allowed_tools)}", self.name)
        if "args" in self.rules:
            for arg, c in manifest.arg_constraints.get(tool, {}).items():
                ok, why = check_constraint(args.get(arg), c)
                if not ok:
                    return Decision(False, "arg_constraint", f"{tool}.{arg} {why}", self.name)
        if "taint" in self.rules or "ntaint" in self.rules:
            check = getattr(is_tainted, "normalized", is_tainted) if "ntaint" in self.rules else is_tainted
            for arg in TAINT_PROTECTED_ARGS.get(tool, ()):
                if check(args.get(arg)):
                    return Decision(False, "tainted_arg",
                                    f"{tool}.{arg} was supplied by untrusted content", self.name)
        return Decision(True, "", "", self.name)
