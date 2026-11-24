"""Tiny MCP client over Streamable HTTP (JSON or SSE replies), so `nitaq agent --mcp URL` can use remote tools."""
from __future__ import annotations

import json
import urllib.request

KEEP = {"type", "description", "properties", "required", "enum", "items", "format", "nullable"}


def gemini_schema(node):
    """MCP inputSchema (JSON Schema) -> the OpenAPI subset Gemini function declarations accept."""
    if isinstance(node, list):
        return [gemini_schema(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for k, v in node.items():
        if k not in KEEP:
            continue
        if k == "properties" and isinstance(v, dict):
            out[k] = {pk: gemini_schema(pv) for pk, pv in v.items()}
        elif k == "type" and isinstance(v, list):
            out[k] = next((t for t in v if t != "null"), "string")
        else:
            out[k] = gemini_schema(v)
    if "properties" in out and "type" not in out:
        out["type"] = "object"
    if out.get("type") == "object" and not out.get("properties"):
        out.pop("required", None)
    return out


class McpClient:
    def __init__(self, url: str, timeout: float = 60) -> None:
        self.url = url
        self.timeout = timeout
        self.session = None
        self.n = 0
        self.info = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                "clientInfo": {"name": "nitaq-agent", "version": "1"}})
        self.notify("notifications/initialized")
        self.tools = self.request("tools/list", {}).get("tools", [])

    def _post(self, msg: dict):
        headers = {"content-type": "application/json", "accept": "application/json, text/event-stream",
                   "mcp-protocol-version": "2025-06-18"}
        if self.session:
            headers["mcp-session-id"] = self.session
        req = urllib.request.Request(self.url, data=json.dumps(msg).encode("utf-8"), method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            self.session = r.headers.get("mcp-session-id") or self.session
            body = r.read().decode("utf-8")
            ctype = r.headers.get("content-type", "")
        if not body.strip():
            return None
        if "text/event-stream" in ctype:
            for line in body.splitlines():
                if line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    if isinstance(data, dict) and data.get("id") == msg.get("id"):
                        return data
            return None
        return json.loads(body)

    def notify(self, method: str) -> None:
        self._post({"jsonrpc": "2.0", "method": method})

    def request(self, method: str, params: dict) -> dict:
        self.n += 1
        resp = self._post({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params})
        if not resp:
            raise RuntimeError(f"no reply to {method}")
        if "error" in resp:
            raise RuntimeError(resp["error"].get("message", "MCP error"))
        return resp.get("result") or {}

    def declarations(self) -> list[dict]:
        out = []
        for t in self.tools:
            schema = gemini_schema(t.get("inputSchema") or {"type": "object"})
            decl = {"name": t["name"], "description": (t.get("description") or t["name"])[:1000]}
            if schema.get("properties"):
                decl["parameters"] = schema
            out.append(decl)
        return out

    def call(self, name: str, args: dict) -> tuple[str, bool]:
        res = self.request("tools/call", {"name": name, "arguments": args})
        text = "\n".join(str(c.get("text", "")) for c in res.get("content", []) if c.get("type") == "text")
        return text, bool(res.get("isError"))
