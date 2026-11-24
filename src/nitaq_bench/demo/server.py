"""`python -m nitaq_bench demo`: local single-page Arabic UI (stdlib http.server).

Binds to 127.0.0.1 by default.  JSON API only; no file paths are accepted from
the browser; request bodies are capped.  All computation goes through
nitaq_bench.demo.api, which calls the evaluator's own functions.
"""
from __future__ import annotations

import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from nitaq_bench.demo import api

STATIC = Path(__file__).parent / "static"
MAX_BODY = 1_000_000


class Handler(BaseHTTPRequestHandler):
    server_version = "nitaq-demo"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?")[0]
        try:
            if path in ("/", "/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/api/meta":
                return self._json(200, api.meta())
            if path == "/api/results":
                return self._json(200, api.results())
            if path == "/api/fixtures":
                return self._json(200, api.fixtures())
            return self._json(404, {"error": "not found"})
        except Exception as exc:  # pragma: no cover - surfaced to the UI
            traceback.print_exc()
            return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        if n > MAX_BODY:
            return self._json(413, {"error": "request too large"})
        try:
            req = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._json(400, {"error": "invalid JSON"})
        path = self.path.split("?")[0]
        try:
            if path == "/api/run":
                return self._json(200, api.run(req))
            if path == "/api/scan-skill":
                return self._json(200, api.scan_skill(req))
            return self._json(404, {"error": "not found"})
        except api.BadRequest as exc:
            return self._json(400, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})


def make_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str = "127.0.0.1", port: int = 8765) -> int:
    srv = make_server(host, port)
    print(f"Nitaq demo on http://{host}:{srv.server_address[1]}/  (Ctrl+C to stop)")
    print("Agent in the demo: worst-case simulated agent, not a real model.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
