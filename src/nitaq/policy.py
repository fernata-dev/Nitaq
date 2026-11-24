"""Nitaq policy: decisions on tool calls, from the call's name and arguments only.

Like the benchmark's D5 guard, the policy never interprets natural-language
content: it looks at tool names, destinations (URLs, e-mail addresses, hosts
after network commands) and file paths found in arguments.  It therefore
behaves identically whatever language or encoding an injection used, and it
shares D5's limits: it cannot stop harmful content inside an allowed call.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_POLICY = {
    "version": 1,
    "mode": "enforce",
    "destination_mode": "allowlist",
    "allowed_hosts": ["localhost", "127.0.0.1", "::1"],
    "check_destinations": True,
    "deny_tools": [],
    "secret_paths": ["~/.ssh/*", "~/.aws/*", "~/.gnupg/*", "~/.config/gcloud/*", "~/.netrc",
                     "*/.env", "*.pem", "*id_rsa*", "*id_ed25519*"],
    "tool_descriptions": "hide",
    "log_file": "~/.nitaq/decisions.jsonl",
}
MODES = ("enforce", "monitor")
DEST_MODES = ("allowlist", "taint")
DESC_ACTIONS = ("hide", "warn", "off")

_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://([^/\s'\"<>@]+@)?(\[[0-9a-f:]+\]|[^/\s'\":<>?#]+)", re.I)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
_NETCMD = re.compile(r"\b(curl|wget|nc|ncat|netcat|scp|sftp|rsync|ssh|ftp|telnet|iwr|irm|Invoke-WebRequest|Invoke-RestMethod)\b", re.I)
_BAREHOST = re.compile(r"(?<![\w@/.-])((?:[a-z0-9-]+\.)+[a-z]{2,})(?::\d+)?(?![\w.-])", re.I)
_PATHTOK = re.compile(r"[~/.\w\\-][^\s'\"`;|&<>()]*")


class PolicyError(ValueError):
    pass


def load_policy(path: Path | None) -> dict:
    if path is None:
        return dict(DEFAULT_POLICY)
    try:
        pol = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(f"cannot read policy {path}: {exc}") from exc
    return validate_policy(pol)


def validate_policy(pol: dict) -> dict:
    if not isinstance(pol, dict) or pol.get("version") != 1:
        raise PolicyError("policy must be an object with \"version\": 1")
    out = dict(DEFAULT_POLICY)
    out.update(pol)
    if out["mode"] not in MODES:
        raise PolicyError(f"mode must be one of {MODES}")
    if out["destination_mode"] not in DEST_MODES:
        raise PolicyError(f"destination_mode must be one of {DEST_MODES}")
    if out["tool_descriptions"] not in DESC_ACTIONS:
        raise PolicyError(f"tool_descriptions must be one of {DESC_ACTIONS}")
    for k in ("allowed_hosts", "deny_tools", "secret_paths"):
        if not isinstance(out[k], list) or not all(isinstance(x, str) for x in out[k]):
            raise PolicyError(f"{k} must be a list of strings")
    return out


def _strings(obj, depth=0):
    if depth > 8:
        return
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(v, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v, depth + 1)


_DEST_KEY = re.compile(r"(url|uri|link|endpoint|host|domain|server|webhook|address|^to$|^cc$|^bcc$|recipient|"
                       r"email|target|dest)", re.I)
_HOSTLIKE = re.compile(r"^(?:[a-z][a-z0-9+.-]*://)?([^/\s:@?#]+\.[^/\s:@?#]+)(?::\d+)?(?:[/?#].*)?$", re.I)


def canon_host(h: str) -> str:
    """Lower-case, strip dots/brackets, canonical IP forms, IDNA for non-ASCII (never folded)."""
    import ipaddress
    import socket

    h = h.strip().strip("[]").rstrip(".").lower()
    if re.fullmatch(r"[0-9a-fx.]+", h) and not re.search(r"[g-wyz]", h) and any(ch.isdigit() for ch in h):
        try:
            return str(ipaddress.IPv4Address(socket.inet_aton(h)))       # 2130706433, 0x7f.1, 0177.0.0.1
        except (OSError, ValueError):
            pass
    try:
        return str(ipaddress.ip_address(h))
    except ValueError:
        pass
    if not h.isascii():
        try:
            return h.encode("idna").decode("ascii")                       # look-alike letters stay distinct
        except UnicodeError:
            return "xn--invalid-" + str(abs(hash(h)) % 10**8)
    return h


def _arg_views(s: str) -> list[str]:
    """What a destination argument may really say: raw, percent-decoded, Base64-decoded, invisibles removed."""
    from urllib.parse import unquote

    from nitaq_bench.defenses import d2_normalizer as N

    views = [s]
    u = unquote(s)
    if u != s:
        views.append(u)
    clean, smuggled = N.strip_invisible(s)
    views += [clean] + ([smuggled] if smuggled else [])
    for v in list(views):
        views += N.decode_b64_candidates(v)
    return list(dict.fromkeys(views))


_VALID_HOST = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)+|[0-9a-f:]+:[0-9a-f:]*")


def _valid(h: str) -> bool:
    return bool(_VALID_HOST.fullmatch(h))


def _hosts_in(s: str, netcmd: bool) -> set[str]:
    hosts = set()
    for m in _URL.finditer(s):
        hosts.add(m.group(2))
    for m in _EMAIL.finditer(s):
        hosts.add(m.group(1))
    if netcmd or _NETCMD.search(s):
        for m in _BAREHOST.finditer(s):
            hosts.add(m.group(1))
    return {c for c in (canon_host(h) for h in hosts if h) if _valid(c)}


def _keyed_strings(obj, key="", depth=0):
    if depth > 8:
        return
    if isinstance(obj, str):
        yield key, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _keyed_strings(v, str(k), depth + 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _keyed_strings(v, key, depth + 1)


def destinations(args) -> set[str]:
    hosts: set[str] = set()
    for key, s in _keyed_strings(args):
        for v in _arg_views(s):
            hosts |= _hosts_in(v, netcmd=False)
            if _DEST_KEY.search(key):
                m = _HOSTLIKE.match(v.strip())
                if m and "@" not in m.group(1) and _valid(canon_host(m.group(1))):
                    hosts.add(canon_host(m.group(1)))
    return hosts


def hosts_from_content(text: str) -> set[str]:
    """Destinations mentioned in untrusted content (tool outputs), even when obfuscated."""
    from nitaq_bench.env.taint import canonical_views

    hosts: set[str] = set()
    for v in canonical_views(text) + _arg_views(text):
        hosts |= _hosts_in(v, netcmd=True)
        for m in _BAREHOST.finditer(v):
            c = canon_host(m.group(1))
            if _valid(c):
                hosts.add(c)
    return hosts


def content_strings(obj) -> list[str]:
    return [s for _, s in _keyed_strings(obj)]


def host_allowed(host: str, allowed: list[str]) -> bool:
    host = canon_host(host)
    for a in allowed:
        a = canon_host(a.lstrip("*."))
        if host == a or host.endswith("." + a):
            return True
    return False


def host_tainted(host: str, tainted: set[str]) -> bool:
    host = canon_host(host)
    return any(host == t or host.endswith("." + t) for t in tainted)


def secret_hits(args, patterns: list[str], home: Path) -> list[str]:
    pats = [str(home) + p[1:] if p.startswith("~") else p for p in patterns]
    hits = []
    for s in _strings(args):
        for tok in _PATHTOK.findall(s):
            t = tok.rstrip(",.")
            cand = str(home) + t[1:] if t.startswith("~") else t
            cand = cand.replace("\\", "/")
            norm = os.path.normpath(cand).replace("\\", "/") if "/" in cand else cand
            for p in pats:
                pn = p.replace("\\", "/")
                if fnmatch.fnmatch(norm, pn) or fnmatch.fnmatch(cand, pn):
                    hits.append(t)
                    break
    return sorted(set(hits))


@dataclass
class Decision:
    allowed: bool
    rule: str = ""
    detail: str = ""
    would_deny: bool = False
    hosts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "rule": self.rule, "detail": self.detail,
                "would_deny": self.would_deny, "hosts": self.hosts}


def evaluate(tool: str, args, policy: dict, home: Path | None = None,
             tainted: set[str] | None = None) -> Decision:
    home = Path(home or os.path.expanduser("~"))
    deny = None
    for pat in policy["deny_tools"]:
        if fnmatch.fnmatch(tool, pat):
            deny = Decision(False, "deny_tool", f"tool {tool!r} matches deny_tools pattern {pat!r}")
            break
    hosts = sorted(destinations(args))
    if deny is None:
        hits = secret_hits(args, policy["secret_paths"], home)
        if hits:
            deny = Decision(False, "secret_path", f"argument refers to a protected path: {', '.join(hits[:3])}")
    if deny is None and policy.get("check_destinations", True):
        outside = [h for h in hosts if not host_allowed(h, policy["allowed_hosts"])]
        if policy["destination_mode"] == "taint":
            bad = [h for h in outside if host_tainted(h, tainted or set())]
            if bad:
                deny = Decision(False, "tainted_destination",
                                f"destination(s) came from untrusted tool output: {', '.join(bad[:5])}")
        elif outside:
            deny = Decision(False, "destination_not_allowed",
                            f"destination(s) not in allowed_hosts: {', '.join(outside[:5])}")
    if deny is None:
        return Decision(True, hosts=hosts)
    deny.hosts = hosts
    if policy["mode"] == "monitor":
        return Decision(True, deny.rule, deny.detail, would_deny=True, hosts=hosts)
    return deny


def log_decision(policy: dict, home: Path, record: dict) -> None:
    """Append a decision (tool name, rule, hosts; never full arguments) to the log file."""
    lf = policy.get("log_file")
    if not lf:
        return
    p = Path(str(home) + lf[1:]) if lf.startswith("~") else Path(lf)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **record},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass
