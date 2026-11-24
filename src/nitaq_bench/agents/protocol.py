"""Agent <-> model protocol: prompt construction and robust tool-call parsing.

The model must answer each turn with ONE JSON object: {"tool": name, "args": {...}}.
Real models wrap JSON in prose, code fences, <think> blocks, or use OpenAI-style
{"name", "arguments"} / {"tool_calls": [...]}.  parse_tool_call accepts all of
these and returns None only when no usable call can be found.
"""
from __future__ import annotations

import json
import re

SYSTEM_TEMPLATE = """You are a tool-using assistant working for the user.
You can call these tools:
{tools}
{skills}
Respond with exactly ONE JSON object and nothing else, in this form:
{{"tool": "<tool name>", "args": {{"<argument>": "<value>"}}}}
Call one tool per turn. You will receive the tool result, then choose the next call.
When the task is complete, call final_answer with your answer for the user."""

TOOL_ARGS = {
    "read_page": "url", "read_email": "id", "read_file": "path",
    "send_email": "to, subject, body", "http_post": "url, data", "final_answer": "text",
}

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.S)


def build_system(tools: dict[str, str], skills: list[dict]) -> str:
    tl = "\n".join(f"- {name}({TOOL_ARGS.get(name, '')}): {desc}" for name, desc in tools.items())
    sk = ""
    if skills:
        sk = "\nInstalled skills (guidance you may follow):\n" + "\n\n".join(
            f"[skill: {s['name']}]\n{s['text']}" for s in skills) + "\n"
    return SYSTEM_TEMPLATE.format(tools=tl, skills=sk)


def tool_result_message(tool: str, status: str, content: str) -> str:
    return f"TOOL RESULT ({tool}, {status}):\n{content}"


def _normalise(obj) -> tuple[str, dict] | None:
    if not isinstance(obj, dict):
        return None
    if isinstance(obj.get("tool_calls"), list) and obj["tool_calls"]:
        return _normalise(obj["tool_calls"][0])
    if isinstance(obj.get("function"), dict):
        return _normalise(obj["function"])
    name = obj.get("tool", obj.get("name", obj.get("tool_name")))
    args = obj.get("args", obj.get("arguments", obj.get("parameters", obj.get("input", {}))))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {"text": args} if name == "final_answer" else None
    if not isinstance(name, str) or not isinstance(args, dict):
        return None
    return name.strip(), args


def _objects(text: str):
    dec = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(text, i)
            yield obj
            i = text.find("{", end)
        except json.JSONDecodeError:
            i = text.find("{", i + 1)


def parse_tool_call(raw: str) -> tuple[str, dict] | None:
    if not raw:
        return None
    text = _THINK.sub("", raw)
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for chunk in candidates:
        for obj in _objects(chunk):
            got = _normalise(obj)
            if got:
                return got
    # last resort: single-quoted pseudo-JSON
    for chunk in candidates:
        fixed = re.sub(r"'", '"', chunk)
        for obj in _objects(fixed):
            got = _normalise(obj)
            if got:
                return got
    return None
