"""`nitaq ui`: a local, bilingual (Arabic/English) app in your browser.

Security (the UI can change agent configs, so a random website must not be able to drive it):
  * binds to 127.0.0.1 only;
  * a fresh random token per launch; every /api call must send it in the X-Nitaq-Token header
    (custom headers cannot be sent cross-site without a CORS preflight, which this server never allows);
  * the Host header must be 127.0.0.1:<port> or localhost:<port> (DNS-rebinding defence);
  * a request with a foreign Origin header is refused;
  * strict Content-Security-Policy; static files come from a fixed whitelist.
Every action calls the same functions as the CLI (discover, scan, protect, unprotect, policy).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from nitaq import __version__

WEB = Path(__file__).resolve().parent.parent / "web"      # the same app that runs on phones
CONSOLE = Path(__file__).resolve().parent / "console"     # the desktop control center (served at /console/)
_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
          ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2", ".webmanifest": "application/manifest+json",
          ".json": "application/json", ".txt": "text/plain; charset=utf-8", ".eml": "message/rfc822",
          ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def _static_files() -> dict[str, tuple[Path, str]]:
    """Fixed whitelist built once from the shipped web folder (a request path is only a dict key)."""
    files = {}
    for f in sorted(WEB.rglob("*")):
        if f.is_file() and f.suffix in _TYPES:
            files["/" + f.relative_to(WEB).as_posix()] = (f, _TYPES[f.suffix])
    if "/index.html" in files:
        files["/"] = files["/index.html"]
    for f in sorted(CONSOLE.rglob("*")):
        if f.is_file() and f.suffix in _TYPES:
            files["/console/" + f.relative_to(CONSOLE).as_posix()] = (f, _TYPES[f.suffix])
    if "/console/index.html" in files:
        files["/console/"] = files["/console/index.html"]
    return files


FILES = _static_files()
MAX_BODY = 2_000_000
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self' data:; img-src 'self' data:; connect-src 'self'; "
       "worker-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def _short(path: Path, home: Path) -> str:
    """A path for the page: ~/… under the inspected home or the real home, never a full user path."""
    for base in (home, Path.home()):
        try:
            return "~/" + Path(path).resolve().relative_to(Path(base).resolve()).as_posix()
        except ValueError:
            continue
    return Path(path).name


class Refused(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code


class App:
    """State + actions behind the HTTP API (kept separate so it can be tested directly)."""

    def __init__(self, home: Path, project: Path | None, policy_path: Path | None = None) -> None:
        self.home = Path(home)
        self.project = project
        self.policy_path = Path(policy_path or self.home / ".nitaq" / "policy.json")
        self.token = secrets.token_urlsafe(32)
        self._lock = threading.Lock()
        self._cache = None
        self._agent = None
        self._llm = None                  # tests put a scripted model here
        self.last_ping = 0.0

    # -- helpers ----------------------------------------------------------
    def _plan(self, body: dict):
        from nitaq import protect as P
        mechs = tuple(body.get("mechanisms") or ()) or None
        agents = tuple(body.get("agents") or ()) or None
        return P.make_plan(self.home, self.project, agents, mechs, self.policy_path)

    @staticmethod
    def plan_hash(plan) -> str:
        h = hashlib.sha256()
        for c in plan.changes:
            for part in (str(c.path), c.before or "\0", c.after):
                h.update(hashlib.sha256(part.encode("utf-8")).digest())
        return h.hexdigest()

    def _render_plan(self, plan) -> dict:
        from nitaq.redact import display_path, mask_diff_line
        mask = {"masked": 0}
        changes = []
        for c in plan.changes:
            diff = [mask_diff_line(l, mask) for l in c.diff(self.home).splitlines()]
            changes.append({"path": display_path(c.path, self.home), "agent": c.agent, "mechanism": c.mechanism,
                            "summary": c.summary, "diff": diff, "new_file": c.before is None})
        return {"changes": changes, "notes": plan.notes, "masked": mask["masked"], "plan_hash": self.plan_hash(plan)}

    def _policy(self) -> tuple[dict, bool, str | None]:
        from nitaq.policy import DEFAULT_POLICY, PolicyError, load_policy
        if not self.policy_path.exists():
            return dict(DEFAULT_POLICY), False, None
        try:
            return load_policy(self.policy_path), True, None
        except PolicyError as exc:
            return dict(DEFAULT_POLICY), True, str(exc)

    # -- actions ----------------------------------------------------------
    def status(self) -> dict:
        from nitaq.discover import discover
        from nitaq.protect import list_backups
        from nitaq.registry import current_os, load_registry
        from nitaq.redact import display_path
        res = discover(self.home, self.project)
        pol, exists, err = self._policy()
        reg = load_registry()
        return {"version": __version__, "os": current_os(), "home": str(self.home),
                "project": str(self.project) if self.project else None,
                "discover": res, "policy": pol, "policy_exists": exists, "policy_error": err,
                "policy_path": display_path(self.policy_path, self.home), "backups": list_backups(self.home),
                "registry": {"agents": [{k: a[k] for k in ("id", "name", "support", "docs", "mechanisms")}
                                        | {"real_cli_check": a.get("real_cli_check", {})} for a in reg["agents"]],
                             "not_supported": reg["not_supported"], "verified_on": reg["verified_on"]}}

    def scan(self, body: dict) -> dict:
        from nitaq_bench.skillscan.scanner import scan_path, scan_text
        allow = tuple(a.strip().lower() for a in str(body.get("allow", "")).split(",") if a.strip())
        if body.get("path"):
            raw = str(body["path"]).strip()
            if raw == "~":                                    # "~" means the home this app inspects
                p = self.home
            elif raw.startswith(("~/", "~\\")):
                p = self.home / raw[2:]
            else:
                p = Path(raw)
            if not p.exists():
                raise Refused(400, "path not found")
            return scan_path(p, allow)
        text = str(body.get("text", ""))[:MAX_BODY]
        if not text.strip():
            raise Refused(400, "nothing to scan")
        return scan_text(text, str(body.get("name") or "pasted text")[:120], allow)

    def plan(self, body: dict) -> dict:
        return self._render_plan(self._plan(body))

    def apply(self, body: dict) -> dict:
        from nitaq import protect as P
        if body.get("confirm") != P.APPLY_WORD:
            raise Refused(400, f"type {P.APPLY_WORD} to confirm")
        plan = self._plan(body)
        if self.plan_hash(plan) != body.get("plan_hash"):
            raise Refused(409, "the files changed since the preview; preview again")
        return P.apply_plan(plan, P.APPLY_WORD)

    def restore_plan(self, body: dict) -> dict:
        from nitaq import protect as P
        from nitaq.redact import mask_diff_line
        bdir, actions, problems = P.plan_restore(self.home, body.get("backup"), bool(body.get("force")))
        mask = {"masked": 0}
        diff = [mask_diff_line(l, mask) for l in P.render_restore(self.home, actions).splitlines()]
        return {"backup": bdir.name, "diff": diff, "problems": problems, "files": len(actions)}

    def restore(self, body: dict) -> dict:
        from nitaq import protect as P
        if body.get("confirm") != P.RESTORE_WORD:
            raise Refused(400, f"type {P.RESTORE_WORD} to confirm")
        bdir, actions, problems = P.plan_restore(self.home, body.get("backup"), bool(body.get("force")))
        try:
            n = P.apply_restore(self.home, actions, problems, P.RESTORE_WORD, bool(body.get("force")))
        except RuntimeError as exc:
            raise Refused(409, str(exc)) from exc
        return {"restored": n, "backup": bdir.name}

    def save_policy(self, body: dict) -> dict:
        from nitaq.policy import PolicyError, validate_policy
        try:
            pol = validate_policy(body.get("policy"))
        except PolicyError as exc:
            raise Refused(400, str(exc)) from exc
        backup = None
        if self.policy_path.exists():
            bdir = self.home / ".nitaq" / "backups"
            bdir.mkdir(parents=True, exist_ok=True)
            backup = bdir / f"policy-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
            backup.write_bytes(self.policy_path.read_bytes())
        self.policy_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.policy_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(pol, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, self.policy_path)
        return {"saved": True, "previous_backup": str(backup) if backup else None}

    def check(self, body: dict) -> dict:
        from nitaq.policy import evaluate
        pol = self._policy()[0] if body.get("policy") is None else body["policy"]
        from nitaq.policy import validate_policy
        pol = validate_policy(pol)
        tainted = set(body.get("tainted") or [])
        args = body.get("args") or {}
        if not isinstance(args, dict):
            raise Refused(400, "args must be an object")
        return evaluate(str(body.get("tool", "")), args, pol, self.home, tainted).to_dict()

    def activity(self) -> dict:
        pol = self._policy()[0]
        lf = pol.get("log_file") or ""
        p = Path(str(self.home) + lf[1:]) if lf.startswith("~") else Path(lf) if lf else None
        rows = []
        if p and p.exists():
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return {"rows": list(reversed(rows))}


    # -- control center ---------------------------------------------------------------------
    def _gw_dir(self) -> Path:
        from nitaq.gateway.server import state_dir
        return state_dir(self.home)

    def _gw_info(self) -> dict | None:
        try:
            return json.loads((self._gw_dir() / "running.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _gw_call(self, action: str, body: dict | None = None):
        import urllib.request
        info = self._gw_info()
        if not info:
            return None
        get = action == "state"
        req = urllib.request.Request(info["admin"] + "/api/" + action, method="GET" if get else "POST",
                                     data=None if get else json.dumps(body or {}).encode("utf-8"),
                                     headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:                                   # noqa: BLE001 - not running
            return None

    def _skills(self, res: dict) -> list[dict]:
        """Skills discover already scanned (no second scan)."""
        out = []
        for a in res.get("agents", []):
            for asset in a.get("assets", []):
                for sk in asset.get("skills") or []:
                    if not isinstance(sk, dict) or not sk.get("path"):
                        continue
                    v = sk.get("verdict", "")
                    out.append({"path": sk["path"], "name": sk.get("skill") or Path(sk["path"]).parent.name,
                                "description": "", "verdict": v if v in ("high-risk", "review") else "clean",
                                "summary": sk.get("summary", {}), "demo": False})
        return out

    def _demo_skills(self) -> list[dict]:
        """The terminal agent's demo folder, scanned live (two small files)."""
        from nitaq.redact import display_path
        from nitaq_bench.skillscan.scanner import scan_path
        out = []
        demo = self.home / "nitaq-demo" / "skills"
        if demo.is_dir():
            for f in sorted(demo.glob("*.md"))[:20]:
                try:
                    r = scan_path(f, ())
                except Exception:                           # noqa: BLE001 - one bad file does not stop the list
                    continue
                fm = r.get("front_matter") or {}
                out.append({"path": display_path(f, self.home), "name": fm.get("name") or f.stem,
                            "description": str(fm.get("description", ""))[:160], "verdict": r["verdict"]
                            if r["verdict"] in ("high-risk", "review") else "clean", "summary": r["summary"], "demo": True})
        return out

    def prefetch(self) -> None:
        """Scan the computer in the background as soon as the app starts (the first scan takes a while)."""
        threading.Thread(target=self.console, daemon=True).start()

    def console_refresh(self, body: dict) -> dict:
        with self._lock:
            self._cache = None
        return self.console()

    def gateway(self) -> dict:
        info = self._gw_info()
        state = self._gw_call("state") if info else None
        return {"running": state is not None, "mcp": (info or {}).get("mcp") if state is not None else None,
                "admin": (info or {}).get("admin") if state is not None else None, "port": (info or {}).get("port"),
                "state": state, "started_here": (self._gw_dir() / "console.pid").exists()}

    def console(self) -> dict:
        """Everything on this computer that Nitaq knows about, in one call (discover is cached; the rest is live)."""
        with self._lock:
            if self._cache is None:
                self._cache = self._console_scan()
            out = dict(self._cache)
        demo = self.home / "nitaq-demo"
        pol, exists, err = self._policy()
        from nitaq.protect import list_backups
        order = {"high-risk": 0, "review": 1, "clean": 2}
        skills = sorted(out["skills"] + self._demo_skills(), key=lambda x: (order.get(x["verdict"], 3), not x["demo"], x["path"]))
        out.update({"skills": skills, "gateway": self.gateway(), "backups": list_backups(self.home)[:10],
                    "policy": {"mode": pol.get("destination_mode"), "allowed_hosts": pol.get("allowed_hosts", []),
                               "secret_paths": pol.get("secret_paths", [])[:12], "exists": exists, "error": err},
                    "demo": {"exists": demo.is_dir(), "path": "~/nitaq-demo",
                             "files": sorted(x.name + ("/" if x.is_dir() else "") for x in demo.iterdir())[:20]
                             if demo.is_dir() else []}})
        return out

    def _console_scan(self) -> dict:
        from nitaq.discover import discover
        res = discover(self.home, self.project)
        agents = []
        for a in res.get("agents", []):
            assets = a.get("assets", [])
            mcp = [m for x in assets for m in (x.get("mcp_servers") or [])]
            agents.append({"id": a["id"], "name": a.get("name", a["id"]),
                           "configs": [{"path": x["path"], "kind": x["kind"], "exists": bool(x.get("exists"))} for x in assets],
                           "hook": any((x.get("hooks") or {}).get("nitaq_hook_installed") for x in assets),
                           "mcp": mcp, "skills": sum(len(x.get("skills") or []) for x in assets)})
        return {"version": __version__, "os": res.get("os"), "home": "~", "agents": agents,
                "not_supported": [n["id"] for n in res.get("not_supported", [])], "skills": self._skills(res),
                "scanned_at": time.strftime("%H:%M:%S")}

    def gateway_start(self, body: dict) -> dict:
        import subprocess
        import sys
        if self._gw_call("state") is not None:
            return {"running": True, "already": True}
        d = self._gw_dir()
        d.mkdir(parents=True, exist_ok=True)
        port = int(body.get("port") or 8787)
        base = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "nitaq"]
        cmd = base + ["gateway", "--port", str(port), "--home", str(self.home)]
        origin = str(body.get("allow_origin") or "").strip()
        if origin.startswith("https://") and " " not in origin:
            cmd += ["--allow-origin", origin]
        log = open(d / "console-gateway.log", "ab")
        kw = {"creationflags": 0x00000200 | 0x00000008} if os.name == "nt" else {"start_new_session": True}
        proc = subprocess.Popen(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, **kw)
        (d / "console.pid").write_text(str(proc.pid), encoding="utf-8")
        for _ in range(40):
            time.sleep(0.15)
            if self._gw_call("state") is not None:
                return {"running": True, "pid": proc.pid}
        return {"running": False, "pid": proc.pid, "note": "started; not answering yet"}

    def gateway_stop(self, body: dict) -> dict:
        import signal
        pidf = self._gw_dir() / "console.pid"
        try:
            pid = int(pidf.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            raise Refused(409, "this app did not start the gateway; stop it in its terminal (Ctrl+C)")
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        pidf.unlink(missing_ok=True)
        return {"stopped": pid}

    def shutdown_children(self) -> None:
        """Stop the Gateway process this app started (called when the app closes)."""
        try:
            self.gateway_stop({})
        except Refused:
            pass

    def gateway_act(self, body: dict) -> dict:
        action = str(body.get("action", ""))
        if action not in ("approve", "deny", "restore", "restrict", "reset"):
            raise Refused(400, "unknown action")
        r = self._gw_call(action, {"id": str(body.get("id", ""))} if action in ("approve", "deny") else {})
        if r is None:
            raise Refused(409, "the gateway is not running")
        return r

    # -- the terminal agent inside the window -------------------------------------------------
    def _session(self):
        if self._agent is None:
            raise Refused(409, "start the agent first")
        return self._agent

    def agent_start(self, body: dict) -> dict:
        from nitaq.ui.agent_bridge import AgentSession
        lang = "en" if body.get("lang") == "en" else "ar"
        if self._agent is None or body.get("reset") or self._agent.ui.lang != lang:
            if self._agent is not None and self._agent.busy:
                raise Refused(409, "the agent is busy")
            try:
                self._agent = AgentSession(self.home, lang, llm=self._llm)
            except LookupError as exc:
                raise Refused(400, str(exc)) from exc
        return self._agent.since(0)

    def settings(self) -> dict:
        from nitaq.agent.gemini import find_key, key_file
        from nitaq.redact import display_path
        key = find_key(self.home / "nitaq-demo")
        return {"version": __version__, "key_set": bool(key), "key_hint": ("…" + key[-4:]) if key else "",
                "key_file": _short(key_file(), self.home), "data_dir": "~/.nitaq", "demo_dir": "~/nitaq-demo",
                "repo": "https://github.com/fernata-dev/Nitaq", "site": "https://byhamo.bond",
                "releases": "https://github.com/fernata-dev/Nitaq/releases/latest"}

    def agent_key_remove(self, body: dict) -> dict:
        from nitaq.agent.gemini import key_file
        try:
            key_file().unlink()
        except FileNotFoundError:
            pass
        self._agent = None
        return {"removed": True}

    def agent_key(self, body: dict) -> dict:
        """Save the Gemini API key from the window (same private file as `nitaq agent --set-key`)."""
        from nitaq.agent.gemini import save_key
        key = str(body.get("key", "")).strip()
        if not (20 <= len(key) <= 200) or any(c.isspace() for c in key):
            raise Refused(400, "that does not look like a Gemini API key")
        save_key(key)
        return {"saved": True}

    def agent_send(self, body: dict) -> dict:
        ok = self._session().send(str(body.get("text", ""))[:4000])
        if not ok:
            raise Refused(409, "the agent is busy")
        return {"ok": True}

    def agent_events(self, body: dict) -> dict:
        return self._session().since(int(body.get("since") or 0))

    def agent_answer(self, body: dict) -> dict:
        return {"ok": self._session().answer(bool(body.get("yes")))}

    def ping(self) -> dict:
        self.last_ping = time.time()
        return {"ok": True}

    def demo_init(self, body: dict) -> dict:
        from nitaq.agent.app import init_demo
        init_demo(self.home / "nitaq-demo")
        return {"created": "~/nitaq-demo"}


ROUTES_GET = {"/api/status": "status", "/api/activity": "activity", "/api/console": "console", "/api/gateway": "gateway",
              "/api/ping": "ping", "/api/settings": "settings"}
ROUTES_POST = {"/api/scan": "scan", "/api/protect/plan": "plan", "/api/protect/apply": "apply",
               "/api/restore/plan": "restore_plan", "/api/restore/apply": "restore", "/api/policy": "save_policy",
               "/api/policy/check": "check", "/api/gateway/start": "gateway_start", "/api/gateway/stop": "gateway_stop",
               "/api/gateway/act": "gateway_act", "/api/demo/init": "demo_init",
               "/api/console/refresh": "console_refresh", "/api/agent/start": "agent_start", "/api/agent/send": "agent_send",
               "/api/agent/events": "agent_events", "/api/agent/answer": "agent_answer",
               "/api/agent/key": "agent_key", "/api/agent/key/remove": "agent_key_remove"}


def make_handler(app: App, port_ref: dict):
    class Handler(BaseHTTPRequestHandler):
        server_version = "nitaq-ui"

        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _guard(self, api: bool):
            port = port_ref["port"]
            host = (self.headers.get("Host") or "").lower()
            if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                raise Refused(403, "bad Host header")
            origin = self.headers.get("Origin")
            if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                raise Refused(403, "foreign origin")
            if api and not hmac.compare_digest(self.headers.get("X-Nitaq-Token", ""), app.token):
                raise Refused(403, "missing or wrong token")

        def _dispatch(self, method: str):
            path = self.path.split("?")[0].split("#")[0]
            try:
                if path in FILES and method == "GET":
                    self._guard(api=False)
                    f, ctype = FILES[path]
                    return self._send(200, f.read_bytes(), ctype)
                routes = ROUTES_GET if method == "GET" else ROUTES_POST
                if path not in routes:
                    return self._json(404, {"error": "not found"})
                self._guard(api=True)
                body = {}
                if method == "POST":
                    n = int(self.headers.get("Content-Length", "0") or 0)
                    if n > MAX_BODY:
                        raise Refused(413, "request too large")
                    try:
                        body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        raise Refused(400, "invalid JSON")
                    if not isinstance(body, dict):
                        raise Refused(400, "JSON object expected")
                fn = getattr(app, routes[path])
                return self._json(200, fn(body) if method == "POST" else fn())
            except Refused as exc:
                return self._json(exc.code, {"error": str(exc)})
            except (PermissionError, FileNotFoundError) as exc:
                return self._json(400, {"error": str(exc)})
            except Exception as exc:  # pragma: no cover - surfaced to the UI
                traceback.print_exc()
                return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

    return Handler


def make_server(app: App, port: int = 0) -> ThreadingHTTPServer:
    ref = {"port": port}
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app, ref))
    ref["port"] = srv.server_address[1]
    return srv


def _app_browser() -> str | None:
    """A Chromium-family browser that can open a page as its own app window (--app=URL)."""
    import shutil
    names = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "brave", "brave-browser",
             "microsoft-edge", "microsoft-edge-stable", "vivaldi", "msedge", "chrome")
    for n in names:
        exe = shutil.which(n)
        if exe:
            return exe
    for cand in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                 "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                 os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                 os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
                 os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                 os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")):
        if os.path.isfile(cand):
            return cand
    return None


def open_window(url: str) -> str:
    """Open the control center in its own app window if possible, otherwise in the default browser."""
    import subprocess
    exe = _app_browser()
    if exe:
        try:
            subprocess.Popen([exe, f"--app={url}", "--window-size=1440,920"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                             **({"start_new_session": True} if os.name != "nt" else {}))
            return "app window"
        except OSError:
            pass
    webbrowser.open(url)
    return "browser"


def serve(home: Path, project: Path | None, port: int = 8777, open_browser: bool = True, classic: bool = False) -> int:
    app = App(home, project)
    try:
        srv = make_server(app, port)
    except OSError:
        srv = make_server(app, 0)          # port busy: pick a free one
    page = "/" if classic else "/console/"
    if not classic:
        app.prefetch()
    url = f"http://127.0.0.1:{srv.server_address[1]}{page}#token={app.token}"
    print("Nitaq UI is running on this computer only.", flush=True)
    print(f"Open: {url}", flush=True)
    print("Press Ctrl+C to stop. (The link contains a one-time secret; do not share it.)", flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: open_window(url)).start()
    if not classic:
        def watchdog():                    # the page pings every few seconds; no ping for a while = window closed
            while True:
                time.sleep(5)
                if app.last_ping and time.time() - app.last_ping > 40:
                    print("The window was closed; Nitaq UI stopped.", flush=True)
                    srv.shutdown()
                    return
        threading.Thread(target=watchdog, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
