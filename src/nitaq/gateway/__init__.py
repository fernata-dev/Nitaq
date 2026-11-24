"""`nitaq gateway`: an MCP server that puts Nitaq between AI agents (including cloud agents) and your tools."""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request
from pathlib import Path

PORT = 8787


def _say(msg: str = "") -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def _admin(home: Path | None, action: str, body: dict | None = None):
    from nitaq.gateway.server import state_dir
    try:
        info = json.loads((state_dir(home) / "running.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _say("No running gateway found. Start one with: nitaq gateway")
        return None
    url = info["admin"] + "/api/" + action
    req = urllib.request.Request(url, data=json.dumps(body or {}).encode() if action != "state" else None,
                                 method="POST" if action != "state" else "GET",
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:                                  # noqa: BLE001 - shown to the user
        _say(f"Could not reach the gateway: {e}")
        return None


def config_text(info: dict) -> str:
    py = "python" if os.name == "nt" else "python3"
    stdio = {"mcpServers": {"nitaq": {"command": "nitaq", "args": ["gateway", "--stdio"]}}}
    return f"""Nitaq Gateway — how to connect an AI
=====================================

1) Cloud AI (claude.ai, ChatGPT, any remote-MCP agent)
   a. keep `nitaq gateway` running on this computer
   b. in a second terminal, open a public HTTPS tunnel to it, for example (free, no account):
        cloudflared tunnel --url http://127.0.0.1:{info['port']}
   c. add a custom connector / remote MCP server with this URL (replace the host with the tunnel's):
        https://<your-tunnel>.trycloudflare.com/mcp/{info['mcp_token']}
      claude.ai: Settings → Connectors → Add custom connector.
   The secret part of the URL is the only key: share it with nobody. Rotate it with --new-token.

2) Local MCP URL (agents on this computer, MCP Inspector, `nitaq agent --mcp`):
        {info['mcp']}

3) Local agents over stdio (Claude Desktop / Claude Code / Gemini CLI config):
{json.dumps(stdio, indent=2)}
   Claude Code:  claude mcp add nitaq -- nitaq gateway --stdio
   Gemini CLI:   put the block above in ~/.gemini/settings.json
   (if `nitaq` is not on PATH, use "command": "{py}", "args": ["-m", "nitaq", "gateway", "--stdio"])

4) Approvals dashboard (this computer only):
        {info['admin']}
   or in a terminal:  nitaq gateway approve <id>   /   nitaq gateway deny <id>

5) The Nitaq website's "Connect" panel (tests this gateway from the browser):
   start the gateway with the site's address allowed, then paste the MCP URL above into the panel:
        nitaq gateway --allow-origin https://<your-site>
   (only the MCP path answers that site; the approvals dashboard stays local-only)
"""


def main(a) -> int:
    from nitaq.agent.ui import c, init_color
    from nitaq.gateway.server import Gateway, Upstream, load_tokens, serve_http, serve_stdio, state_dir, write_info
    init_color(None if not a.stdio else False)
    home = Path(a.home).expanduser() if getattr(a, "home", None) else None
    act = a.action or "serve"
    if act in ("approve", "deny"):
        if not a.id:
            _say(f"usage: nitaq gateway {act} <id>")
            return 2
        r = _admin(home, act, {"id": a.id})
        print(("approved" if act == "approve" else "denied") + f" request {a.id}" if r and r.get("ok")
              else f"no pending request {a.id}")
        return 0 if r and r.get("ok") else 1
    if act in ("restore", "restrict", "reset"):
        r = _admin(home, act)
        print("ok" if r else "failed")
        return 0 if r else 1
    if act == "status":
        r = _admin(home, "state")
        if r is None:
            return 1
        print(json.dumps({k: r[k] for k in ("mode", "why", "permissions", "pending", "outbox")}, ensure_ascii=False,
                         indent=2))
        return 0
    d = state_dir(home)
    d.mkdir(parents=True, exist_ok=True)
    tokens = load_tokens(d, rotate=a.new_token)
    host = a.host
    info = {"port": a.port, "mcp_token": tokens["mcp"],
            "mcp": f"http://127.0.0.1:{a.port}/mcp/{tokens['mcp']}",
            "admin": f"http://127.0.0.1:{a.port}/admin/{tokens['admin']}"}
    if act == "config":
        print(config_text(info))
        return 0
    up = None
    cmd = [x for x in (a.upstream or []) if x != "--"]
    if cmd:
        up = Upstream(cmd)
    gw = Gateway(home, up)
    try:
        srv = serve_http(gw, host, a.port, tokens, tuple(getattr(a, "allow_origin", None) or ()))
    except OSError as e:
        if not a.stdio:
            _say(f"cannot listen on {host}:{a.port}: {e}. Try --port {a.port + 1}")
            return 1
        srv = None                                      # stdio still works; no dashboard
    if srv:
        write_info(d, info)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    if a.stdio:
        if srv:
            _say(f"[nitaq gateway] stdio MCP server ready; approvals dashboard: {info['admin']}")
        try:
            return serve_stdio(gw)
        finally:
            if up:
                up.close()
    _say("")
    _say("  " + c("▛▜ نِطاق Gateway", "bteal") + c("  · MCP server for AI agents (local and cloud)", "grey"))
    _say("  " + c("back end: ", "grey") + ("demo mailbox + drive (fake data)" if not up else "upstream: " + " ".join(cmd)))
    _say("  " + c("MCP URL (this computer): ", "grey") + info["mcp"])
    _say("  " + c("approvals dashboard:     ", "grey") + c(info["admin"], "bold"))
    _say("  " + c("cloud AI (claude.ai …):  ", "grey") + f"cloudflared tunnel --url http://127.0.0.1:{a.port}")
    _say("  " + c("                         then add https://<tunnel>/mcp/" + tokens["mcp"] + " as a connector", "grey"))
    for o in getattr(a, "allow_origin", None) or ():
        _say("  " + c("website connect panel:   ", "grey") + f"{o} may call the MCP URL (paste it in the panel)")
    _say("  " + c("all connection options:  nitaq gateway config", "grey"))
    _say("  " + c("Ctrl+C to stop.", "grey"))
    _say("")
    if a.open:
        import webbrowser
        webbrowser.open(info["admin"])
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
        try:
            (d / "running.json").unlink()
        except OSError:
            pass
        if up:
            up.close()
    return 0
