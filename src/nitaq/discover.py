"""`nitaq discover`: READ-ONLY discovery of supported agents' assets.

Guarantees (tested against a fake HOME):
  * only paths from data/supported_agents.json are looked at;
  * files are opened read-only in binary mode, up to MAX_BYTES; nothing is written;
  * symlinks that resolve outside the scanned home/project are not read;
  * no network; secrets (env values, headers, secret-looking args) are never output.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
from pathlib import Path

from nitaq import __version__
from nitaq.redact import SECRET_NAME, display_path, redact_args
from nitaq.registry import Location, current_os, load_registry, resolve_locations

MAX_BYTES = 5_000_000
MAX_SKILL_FILES = 500
UNPINNED_LAUNCHERS = {"npx", "bunx", "pnpx", "uvx"}
_SEV = {"info": 0, "low": 1, "medium": 2, "high": 3}


def _inside(p: Path, roots: list[Path]) -> bool:
    try:
        real = Path(os.path.realpath(p))
    except OSError:
        return False
    for r in roots:
        try:
            real.relative_to(Path(os.path.realpath(r)))
            return True
        except ValueError:
            continue
    return False


def read_bytes(p: Path, roots: list[Path]) -> tuple[bytes | None, str]:
    """Read-only, size-capped, symlink-safe read."""
    try:
        if p.is_symlink() and not _inside(p, roots):
            return None, "symlink points outside the scanned folders: not read"
        if not p.is_file():
            return None, "not a regular file"
        with open(p, "rb") as fh:            # read-only
            data = fh.read(MAX_BYTES + 1)
    except OSError as exc:
        return None, f"unreadable ({type(exc).__name__})"
    if len(data) > MAX_BYTES:
        return None, f"larger than {MAX_BYTES} bytes: not read"
    return data, ""


NAMES = ("nitaq",)


def is_wrapped(server: dict) -> bool:
    args = [str(a) for a in server.get("args", []) or []]
    cmd = Path(str(server.get("command", ""))).name.lower()
    return (any(n in args for n in NAMES) and "mcp-proxy" in args) or \
        (cmd.startswith(NAMES) and args[:1] == ["mcp-proxy"])


def is_our_hook(command: str) -> bool:
    c = f" {command} "
    return any(n in c for n in NAMES) and " hook " in c


def unwrap(s: dict) -> dict:
    """For a server behind the Nitaq proxy, the real server command is after '--'."""
    if not is_wrapped(s):
        return s
    args = [str(a) for a in s.get("args", []) or []]
    if "--" in args:
        i = args.index("--")
        if i + 1 < len(args):
            return dict(s, command=args[i + 1], args=args[i + 2:])
    return s


def server_risks(name: str, s: dict) -> list[dict]:
    risks = []
    wrapped = is_wrapped(s)
    s = unwrap(s)
    if "url" in s or s.get("type") in ("http", "sse"):
        host = str(s.get("url", "")).split("://")[-1].split("/")[0].split(":")[0]
        if host and host not in ("localhost", "127.0.0.1", "::1"):
            risks.append({"severity": "low", "rule": "remote_server",
                          "message": f"remote MCP server ({host}); the proxy cannot wrap remote servers"})
        if s.get("headers"):
            risks.append({"severity": "info", "rule": "headers_present",
                          "message": f"headers set ({', '.join(sorted(s['headers']))}); values not shown"})
        return risks
    cmd = Path(str(s.get("command", ""))).name.lower()
    args = [str(a) for a in s.get("args", []) or []]
    if cmd in UNPINNED_LAUNCHERS:
        pkgs = [a for a in args if not a.startswith("-")]
        pkg = pkgs[0] if pkgs else ""
        name_part = pkg[1:] if pkg.startswith("@") else pkg
        if pkg and "@" not in name_part and "==" not in pkg:
            risks.append({"severity": "medium", "rule": "unpinned_package",
                          "message": f"'{cmd} {pkg}' downloads whatever version is latest at every launch"})
    if any(seg in str(s.get("command", "")).lower() for seg in ("/tmp/", "\\temp\\", "/downloads/", "\\downloads\\")):
        risks.append({"severity": "medium", "rule": "command_in_temp_or_downloads",
                      "message": "server binary runs from a temporary or Downloads folder"})
    env = s.get("env") or {}
    secret_env = sorted(k for k in env if SECRET_NAME.search(k))
    if secret_env:
        risks.append({"severity": "info", "rule": "secrets_in_env",
                      "message": f"secrets passed via env: {', '.join(secret_env)} (values never shown)"})
    _, n = redact_args(args)
    if n:
        risks.append({"severity": "high", "rule": "secret_in_args",
                      "message": f"{n} argument(s) look like a literal secret (redacted); prefer env variables"})
    if not wrapped:
        risks.append({"severity": "info", "rule": "not_protected",
                      "message": "stdio server is not behind the Nitaq policy proxy"})
    return risks


def describe_server(name: str, s: dict, scope: str) -> dict:
    remote = "url" in s or s.get("type") in ("http", "sse")
    real = unwrap(s)
    args, _ = redact_args([str(a) for a in (real.get("args") or [])])
    d = {"name": name, "scope": scope, "transport": (s.get("type") or "http") if remote else "stdio",
         "protected": is_wrapped(s) if not remote else False,
         "env_keys": sorted((s.get("env") or {}).keys()),
         "risks": server_risks(name, s)}
    if remote:
        d["url_host"] = str(s.get("url", "")).split("://")[-1].split("/")[0]
    else:
        d["command"] = ("[nitaq proxy] " if d["protected"] else "") + \
            " ".join(shlex.quote(x) for x in [str(real.get("command", ""))] + args)
    return d


def servers_in(doc: dict, fmt: str) -> list[tuple[str, str, dict]]:
    out = []
    if isinstance(doc.get("mcpServers"), dict):
        for n, s in doc["mcpServers"].items():
            if isinstance(s, dict):
                out.append((n, "user" if fmt == "claude_json" else "file", s))
    if fmt == "claude_json" and isinstance(doc.get("projects"), dict):
        for proj, pdata in doc["projects"].items():
            if isinstance(pdata, dict) and isinstance(pdata.get("mcpServers"), dict):
                for n, s in pdata["mcpServers"].items():
                    if isinstance(s, dict):
                        out.append((n, f"local:{proj}", s))
    return out


def settings_hooks(doc: dict) -> dict:
    hooks = doc.get("hooks") if isinstance(doc.get("hooks"), dict) else {}
    counts = {ev: sum(len(g.get("hooks", [])) for g in groups if isinstance(g, dict))
              for ev, groups in hooks.items() if isinstance(groups, list)}
    nitaq = any(is_our_hook(str(h.get("command", "")))
                for g in hooks.get("PreToolUse", []) if isinstance(g, dict)
                for h in g.get("hooks", []) if isinstance(h, dict))
    return {"events": counts, "nitaq_hook_installed": nitaq}


def scan_skill_dir(d: Path, roots: list[Path], home: Path) -> list[dict]:
    from nitaq_bench.skillscan.scanner import scan_text

    found = []
    for dirpath, dirnames, filenames in os.walk(d, followlinks=False):
        depth = len(Path(dirpath).relative_to(d).parts)
        if depth >= 3:
            dirnames[:] = []
        for fn in filenames:
            if fn.lower() != "skill.md":
                continue
            p = Path(dirpath) / fn
            data, why = read_bytes(p, roots)
            entry = {"path": display_path(p, home), "skill": Path(dirpath).name}
            if data is None:
                entry.update({"read": False, "note": why})
            else:
                rep = scan_text(data.decode("utf-8", errors="replace"), str(p))
                others = sorted(x for x in os.listdir(dirpath) if x != fn)[:20]
                entry.update({"read": True, "sha256": hashlib.sha256(data).hexdigest(),
                              "verdict": rep["verdict"], "summary": rep["summary"],
                              "other_files": others,
                              "findings": [{k: f[k] for k in ("severity", "rule", "line", "message", "evidence")}
                                           | ({"decoded": f["decoded"]} if f.get("decoded") else {})
                                           for f in rep["findings"] if f["severity"] in ("high", "medium")]})
            found.append(entry)
            if len(found) >= MAX_SKILL_FILES:
                return found
    return found


def discover(home: Path | None = None, project: Path | None = None,
             agents: tuple[str, ...] | None = None) -> dict:
    from nitaq.registry import default_home

    from nitaq.redact import set_project
    set_project(project)
    home = Path(home or default_home())
    reg = load_registry()
    roots = [home] + ([project] if project else [])
    result = {"tool": "nitaq discover", "nitaq_version": __version__, "read_only": True,
              "os": current_os(), "home": str(home), "project": str(project) if project else None,
              "supported_agents": [a["id"] for a in reg["agents"]],
              "not_supported": reg.get("not_supported", []), "agents": []}
    by_agent: dict[str, dict] = {}
    for loc in resolve_locations(reg, home, project, agents):
        a = by_agent.setdefault(loc.agent, {"id": loc.agent, "name": loc.agent_name, "assets": []})
        a["assets"].append(_asset(loc, roots, home))
    result["agents"] = list(by_agent.values())
    result["summary"] = _summary(result)
    return result


def _asset(loc: Location, roots: list[Path], home: Path) -> dict:
    asset = {"location": loc.id, "scope": loc.scope, "kind": loc.kind, "path": display_path(loc.path, home),
             "exists": loc.path.exists()}
    if not asset["exists"]:
        return asset
    if loc.kind == "skills_dir":
        asset["skills"] = scan_skill_dir(loc.path, roots, home) if loc.path.is_dir() else []
        return asset
    data, why = read_bytes(loc.path, roots)
    if data is None:
        asset.update({"read": False, "note": why})
        return asset
    asset.update({"read": True, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        asset.update({"parsed": False, "note": f"not valid JSON ({type(exc).__name__}); Nitaq will not modify it"})
        return asset
    asset["parsed"] = isinstance(doc, dict)
    if not isinstance(doc, dict):
        return asset
    if loc.kind == "mcp_config":
        asset["mcp_servers"] = [describe_server(n, s, sc) for n, sc, s in servers_in(doc, loc.format or "mcpServers")]
    if loc.kind == "settings":
        asset["hooks"] = settings_hooks(doc)
    return asset


def _summary(res: dict) -> dict:
    s = {"assets_found": 0, "skills_scanned": 0, "skills_high_risk": 0, "mcp_servers": 0,
         "stdio_servers_unprotected": 0, "high": 0, "medium": 0}
    for a in res["agents"]:
        for asset in a["assets"]:
            if not asset["exists"]:
                continue
            s["assets_found"] += 1
            for sk in asset.get("skills", []):
                if sk.get("read"):
                    s["skills_scanned"] += 1
                    s["skills_high_risk"] += sk["verdict"] == "high-risk"
                    s["high"] += sk["summary"]["high"]
                    s["medium"] += sk["summary"]["medium"]
            for srv in asset.get("mcp_servers", []):
                s["mcp_servers"] += 1
                s["stdio_servers_unprotected"] += srv["transport"] == "stdio" and not srv["protected"]
                for r in srv["risks"]:
                    s["high"] += r["severity"] == "high"
                    s["medium"] += r["severity"] == "medium"
    return s


def render(res: dict) -> str:
    from nitaq.term import c, rule, sev

    L = [c("Nitaq discover", "bold") + c(f"  v{res['nitaq_version']} · read-only · no network · os={res['os']}", "dim"),
         c(f"home: {res['home']}" + (f"   project: {res['project']}" if res["project"] else ""), "dim"), ""]
    for a in res["agents"]:
        L.append(rule(a["name"]))
        for asset in a["assets"]:
            mark = c("●", "green") if asset["exists"] else c("○", "grey")
            line = f" {mark} {asset['path']}"
            if not asset["exists"]:
                L.append(c(line + "  (not present)", "grey"))
                continue
            if asset.get("read") is False:
                L.append(line + "  " + c(asset.get("note", ""), "yellow"))
                continue
            if asset.get("parsed") is False:
                L.append(line + "  " + c(asset.get("note", ""), "yellow"))
                continue
            L.append(line + c(f"  [{asset['kind']}]", "dim"))
            if "hooks" in asset:
                h = asset["hooks"]
                ev = ", ".join(f"{k}:{v}" for k, v in h["events"].items()) or "none"
                L.append(f"     hooks: {ev}   nitaq hook: " +
                         (c("installed", "green") if h["nitaq_hook_installed"] else c("not installed", "yellow")))
            for srv in asset.get("mcp_servers", []):
                prot = c("protected", "green") if srv["protected"] else (
                    c("unprotected", "yellow") if srv["transport"] == "stdio" else c("remote", "cyan"))
                target = srv.get("command") or srv.get("url_host", "")
                L.append(f"     MCP {c(srv['name'], 'bold')} [{srv['transport']}, {srv['scope']}] {prot}")
                L.append(c(f"         {target}", "dim"))
                for r in srv["risks"]:
                    if r["rule"] != "not_protected":
                        L.append(f"         {sev(r['severity'])} {r['message']}")
            for sk in asset.get("skills", []):
                if not sk.get("read"):
                    L.append(f"     skill {sk['skill']}: " + c(sk.get("note", ""), "yellow"))
                    continue
                v = {"high-risk": c("HIGH RISK", "bred"), "review": c("review", "byellow"),
                     "no-major-findings": c("ok", "bgreen")}[sk["verdict"]]
                L.append(f"     skill {c(sk['skill'], 'bold')}: {v}  " +
                         c(" ".join(f"{k}={n}" for k, n in sk["summary"].items() if n), "dim"))
                for f in sk["findings"][:6]:
                    L.append(f"         {sev(f['severity'])} L{f['line']} {f['rule']}")
                    if f.get("decoded"):
                        L.append(c(f"                decoded: {f['decoded'][:90]}", "magenta"))
                if len(sk["findings"]) > 6:
                    L.append(c(f"         … {len(sk['findings']) - 6} more (use --json)", "dim"))
        L.append("")
    s = res["summary"]
    L.append(rule("summary"))
    L.append(f" assets found: {s['assets_found']}   skills scanned: {s['skills_scanned']} "
             f"({c(str(s['skills_high_risk']) + ' high-risk', 'bred' if s['skills_high_risk'] else 'green')})   "
             f"MCP servers: {s['mcp_servers']} ({s['stdio_servers_unprotected']} stdio unprotected)")
    L.append(f" findings: {c(str(s['high']) + ' high', 'bred' if s['high'] else 'green')}, "
             f"{c(str(s['medium']) + ' medium', 'byellow' if s['medium'] else 'green')}")
    L.append(c(" not covered: " + ", ".join(x["id"] for x in res["not_supported"]) +
               "  (see docs/INTEGRATIONS.md; scan any file with `nitaq scan PATH`)", "dim"))
    L.append(c(" Nothing was modified. Next: `nitaq protect --dry-run` to preview opt-in protection.", "dim"))
    return "\n".join(L)
