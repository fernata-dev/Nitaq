"""Claude Code PreToolUse hook (documented: https://code.claude.com/docs/en/hooks).

stdin: JSON with tool_name and tool_input.  To deny, print ONLY
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
 "permissionDecisionReason": ...}} and exit 0.  To allow, print nothing and exit 0
(the normal permission flow applies).  A broken policy fails CLOSED (deny).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from nitaq import taintstore
from nitaq.policy import PolicyError, content_strings, evaluate, hosts_from_content, load_policy, log_decision


def _deny(reason: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                              "permissionDecisionReason": reason}})


def run(stdin_text: str, policy_path: Path | None, home: Path | None = None) -> tuple[str, int]:
    home = Path(home or os.path.expanduser("~"))
    try:
        policy = load_policy(policy_path)
    except PolicyError as exc:
        return _deny(f"Nitaq: policy could not be loaded ({exc}); blocking to stay safe."), 0
    try:
        event = json.loads(stdin_text or "{}")
    except json.JSONDecodeError:
        return _deny("Nitaq: hook input was not valid JSON; blocking to stay safe."), 0
    tool = str(event.get("tool_name", ""))
    tainted = taintstore.load(home, str(event.get("session_id", ""))) if policy["destination_mode"] == "taint" else None
    d = evaluate(tool, event.get("tool_input", {}), policy, home, tainted)
    log_decision(policy, home, {"source": "claude-code-hook", "tool": tool, **d.to_dict()})
    if d.allowed:
        return "", 0
    return _deny(f"Blocked by Nitaq policy ({d.rule}): {d.detail}"), 0


def run_post(stdin_text: str, policy_path: Path | None, home: Path | None = None) -> tuple[str, int]:
    """PostToolUse: record hosts found in the tool's output (taint mode only). Never blocks, prints nothing."""
    home = Path(home or os.path.expanduser("~"))
    try:
        policy = load_policy(policy_path)
        event = json.loads(stdin_text or "{}")
    except (PolicyError, json.JSONDecodeError):
        return "", 0
    if policy["destination_mode"] != "taint":
        return "", 0
    hosts: set[str] = set()
    for text in content_strings(event.get("tool_response", {})):
        hosts |= hosts_from_content(text)
    try:
        taintstore.add(home, str(event.get("session_id", "")), hosts)
    except OSError:
        pass
    return "", 0


def main(policy_path: str | None, event: str = "pre") -> int:
    if event == "post":
        out, code = run_post(sys.stdin.read(), Path(policy_path) if policy_path else None)
        return code
    out, code = run(sys.stdin.read(), Path(policy_path) if policy_path else None)
    if out:
        sys.stdout.write(out)
        sys.stdout.flush()
    return code
