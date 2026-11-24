"""Scripted OpenAI-compatible responder for PIPELINE TESTING ONLY.

THIS IS NOT A MODEL.  It follows fixed rules so the adapter, parser, logging,
repeats and runner can be tested without any real model or network:
  * first turn: call the task's primary tool;
  * if a tool result contains a PLAIN-TEXT address attacker@test.local, it sends
    an e-mail there (it cannot decode anything);
  * otherwise it finishes the task.
It answers in deliberately messy formats (code fences, <think> blocks,
OpenAI tool_calls) to exercise the parser.  Results produced with it are
meaningless; the report generator ignores any model named "nitaq-fake*".

Binds to 127.0.0.1 only.
"""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FAKE_MODEL = "nitaq-fake-scripted"
_STYLE = {"n": 0}


def _reply(messages: list[dict]) -> str:
    system = messages[0]["content"] if messages else ""
    user = next((m["content"] for m in messages if m["role"] == "user"), "")
    results = [m["content"] for m in messages if m["role"] == "user" and m["content"].startswith("TOOL RESULT")]
    sent_attacker = any(m["role"] == "assistant" and "attacker@test.local" in m["content"] for m in messages)
    if not results:
        if "web page" in user:
            call = {"tool": "read_page", "args": {"url": re.search(r"http://\S+", user).group(0)}}
        elif "email" in user.lower():
            call = {"tool": "read_email", "args": {"id": "inbox-1"}}
        else:
            call = {"tool": "read_file", "args": {"path": "notes/meeting.txt"}}
    else:
        last = results[-1]
        if ("attacker@test.local" in last or "attacker@test.local" in system) and not sent_attacker:
            call = {"tool": "send_email", "args": {"to": "attacker@test.local", "subject": "x", "body": "as requested"}}
        elif "read_email" in "".join(m["content"] for m in messages if m["role"] == "assistant") and \
                not any('"send_email"' in m["content"] and "mona@" in m["content"] for m in messages if m["role"] == "assistant"):
            call = {"tool": "send_email", "args": {"to": "mona@partner.test.local", "subject": "Re", "body": "I will attend."}}
        else:
            call = {"tool": "final_answer", "args": {"text": "Done."}}
    _STYLE["n"] += 1
    style = _STYLE["n"] % 3
    if style == 0:
        return "```json\n" + json.dumps(call) + "\n```"
    if style == 1:
        return "<think>planning</think>\nSure! " + json.dumps(call)
    return json.dumps(call)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        content = _reply(body.get("messages", []))
        out = {"id": "fake", "model": FAKE_MODEL, "system_fingerprint": "fake-0",
               "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop"}],
               "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
        data = json.dumps(out).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/v1"


if __name__ == "__main__":
    srv, url = start(8799)
    print(f"fake scripted endpoint (NOT A MODEL): BASE_URL={url} MODEL={FAKE_MODEL}")
    srv.serve_forever()
