"""`nitaq protect` / `nitaq unprotect`: OPT-IN changes to supported agents' configs.

Only documented mechanisms (docs/INTEGRATIONS.md) are used:
  * mcp-stdio-proxy  wrap stdio MCP server entries so they run behind `nitaq mcp-proxy`
  * pretooluse-hook  add a Claude Code PreToolUse command hook calling `nitaq hook claude-code`

Safety:
  * --dry-run prints the exact unified diff of every file that would change;
  * --apply needs an explicit typed confirmation, writes a timestamped backup FIRST,
    writes atomically, re-reads and validates every file, and rolls back on any error;
  * files that are not valid JSON are never modified;
  * `unprotect` restores a backup, refusing if a file changed since Nitaq wrote it
    (unless --force);
  * nothing runs automatically; nothing outside data/supported_agents.json is touched.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from nitaq import __version__
from nitaq.discover import is_our_hook, is_wrapped, read_bytes
from nitaq.policy import DEFAULT_POLICY
from nitaq.redact import display_path
from nitaq.registry import load_registry, mechanisms, resolve_locations

APPLY_WORD = "APPLY"
RESTORE_WORD = "RESTORE"


@dataclass
class Change:
    path: Path
    before: str | None
    after: str
    agent: str
    mechanism: str
    summary: list[str] = field(default_factory=list)

    def diff(self, home: Path) -> str:
        name = display_path(self.path, home)
        a = [] if self.before is None else self.before.splitlines(keepends=True)
        b = self.after.splitlines(keepends=True)
        return "".join(difflib.unified_diff(a, b, fromfile="/dev/null" if self.before is None else f"a/{name}",
                                            tofile=f"b/{name}", n=2))


@dataclass
class Plan:
    home: Path
    changes: list[Change] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    policy_path: Path | None = None


def nitaq_cmd() -> list[str]:
    return [sys.executable, "-m", "nitaq"]


def _indent_of(text: str) -> int | str:
    m = re.search(r"\n([ \t]+)\"", text)
    if not m:
        return 2
    return "\t" if m.group(1).startswith("\t") else len(m.group(1))


def _dump(doc: dict, like: str | None) -> str:
    out = json.dumps(doc, ensure_ascii=False, indent=_indent_of(like) if like else 2)
    out += "\n" if (like is None or like.endswith("\n")) else ""
    if like and "\r\n" in like:                 # keep the file's line endings (Windows)
        out = out.replace("\n", "\r\n")
    return out


def _read_exact(path: Path) -> str | None:
    """File content exactly as stored (no newline translation): what plans and backups compare."""
    return path.read_bytes().decode("utf-8") if path.exists() else None


def wrap_server(name: str, s: dict, policy_path: Path) -> dict:
    new = dict(s)
    new["command"] = nitaq_cmd()[0]
    new["args"] = nitaq_cmd()[1:] + ["mcp-proxy", "--policy", str(policy_path), "--name", name, "--",
                                     str(s["command"])] + [str(a) for a in (s.get("args") or [])]
    return new


def _wrap_all(servers: dict, policy_path: Path, prefix: str, summary: list[str]) -> bool:
    changed = False
    for n, s in list(servers.items()):
        if not isinstance(s, dict) or "url" in s or s.get("type") not in (None, "stdio") or "command" not in s:
            continue
        if is_wrapped(s):
            continue
        servers[n] = wrap_server(n, s, policy_path)
        summary.append(f"wrap MCP server {prefix}{n!r} with the Nitaq policy proxy")
        changed = True
    return changed


def hook_command(policy_path: Path, which: str = "claude-code") -> str:
    parts = nitaq_cmd() + ["hook", which, "--policy", str(policy_path)]
    return subprocess.list2cmdline(parts) if os.name == "nt" else " ".join(shlex.quote(p) for p in parts)


def make_plan(home: Path, project: Path | None = None, agents: tuple[str, ...] | None = None,
              mechs: tuple[str, ...] | None = None, policy_path: Path | None = None) -> Plan:
    from nitaq.redact import set_project
    set_project(project)
    reg = load_registry()
    policy_path = Path(policy_path or (home / ".nitaq" / "policy.json"))
    plan = Plan(home=home, policy_path=policy_path)
    roots = [home] + ([project] if project else [])
    locs = {(l.agent, l.id): l for l in resolve_locations(reg, home, project, agents)}
    for a in reg["agents"]:
        if agents and a["id"] not in agents or a.get("support") != "protect":
            continue
        for mech in mechanisms(reg, a["id"]):
            if mechs and mech["id"] not in mechs:
                continue
            for loc_id in mech["applies_to"]:
                loc = locs.get((a["id"], loc_id))
                if not loc:
                    continue
                ch = _plan_location(loc, mech["id"], policy_path, plan, roots)
                if ch:
                    plan.changes.append(ch)
    if plan.changes and not policy_path.exists():
        plan.changes.insert(0, Change(policy_path, None, json.dumps(DEFAULT_POLICY, indent=2) + "\n",
                                      "nitaq", "policy-file", ["create the default Nitaq policy (edit allowed_hosts!)"]))
    return plan


def _plan_location(loc, mech: str, policy_path: Path, plan: Plan, roots: list[Path]) -> Change | None:
    disp = display_path(loc.path, plan.home)
    if mech in ("pretooluse-hook", "posttooluse-hook"):
        event, which = ("PreToolUse", "claude-code") if mech == "pretooluse-hook" else ("PostToolUse", "claude-code-post")
        pending = next((c for c in plan.changes if c.path == loc.path), None)
        if pending is not None:
            before, doc = pending.before, json.loads(pending.after)
        elif not loc.path.exists():
            if not loc.path.parent.is_dir():
                plan.notes.append(f"{loc.agent}: {display_path(loc.path.parent, plan.home)} not found; agent not installed, skipped")
                return None
            before, doc = None, {}
        else:
            data, why = read_bytes(loc.path, roots)
            if data is None:
                plan.notes.append(f"{disp}: {why}; skipped")
                return None
            before = data.decode("utf-8", errors="strict")
            try:
                doc = json.loads(before)
            except json.JSONDecodeError:
                plan.notes.append(f"{disp}: not valid JSON; Nitaq never modifies files it cannot parse")
                return None
            if not isinstance(doc, dict):
                plan.notes.append(f"{disp}: not a JSON object; skipped")
                return None
        hooks = doc.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            plan.notes.append(f"{disp}: 'hooks' is not an object; skipped")
            return None
        groups = hooks.setdefault(event, [])
        if any(is_our_hook(str(h.get("command", "")))
               for g in groups if isinstance(g, dict) for h in g.get("hooks", []) if isinstance(h, dict)):
            plan.notes.append(f"{disp}: Nitaq {event} hook already installed")
            return None
        groups.append({"matcher": "*", "hooks": [{"type": "command", "command": hook_command(policy_path, which)}]})
        summary = (["add a PreToolUse hook (all tools) that asks the Nitaq policy before each tool call"]
                   if event == "PreToolUse" else
                   ["add a PostToolUse hook that records hosts seen in tool output (used only in taint mode)"])
        if pending is not None:
            pending.after = _dump(doc, before)
            pending.summary += summary
            pending.mechanism += "+" + mech
            return None
        return Change(loc.path, before, _dump(doc, before), loc.agent, mech, summary)
    if mech == "mcp-stdio-proxy":
        if not loc.path.exists():
            return None
        data, why = read_bytes(loc.path, roots)
        if data is None:
            plan.notes.append(f"{disp}: {why}; skipped")
            return None
        try:
            before = data.decode("utf-8")
            doc = json.loads(before)
        except (UnicodeDecodeError, json.JSONDecodeError):
            plan.notes.append(f"{disp}: not valid JSON; Nitaq never modifies files it cannot parse")
            return None
        if not isinstance(doc, dict):
            return None
        summary: list[str] = []
        changed = False
        if isinstance(doc.get("mcpServers"), dict):
            changed |= _wrap_all(doc["mcpServers"], policy_path, "", summary)
        if loc.format == "claude_json" and isinstance(doc.get("projects"), dict):
            for proj, pdata in doc["projects"].items():
                if isinstance(pdata, dict) and isinstance(pdata.get("mcpServers"), dict):
                    changed |= _wrap_all(pdata["mcpServers"], policy_path, f"[{proj}] ", summary)
        if not changed:
            return None
        if loc.format == "claude_json":
            plan.notes.append(f"{disp}: Claude Code rewrites this file while it runs; quit Claude Code before --apply")
        return Change(loc.path, before, _dump(doc, before), loc.agent, mech, summary)
    return None


def render_plan(plan: Plan) -> str:
    from nitaq.term import c, rule

    from nitaq.redact import mask_diff_line

    L = [c("Nitaq protect — DRY RUN (nothing has been changed)", "bold"), ""]
    mask = {"masked": 0}
    if not plan.changes:
        L.append(c("Nothing to change.", "green"))
    for ch in plan.changes:
        L.append(rule(f"{ch.agent} · {ch.mechanism} · {display_path(ch.path, plan.home)}"))
        for s in ch.summary:
            L.append(c(f"  • {s}", "cyan"))
        for line in ch.diff(plan.home).splitlines():
            line = mask_diff_line(line, mask)
            if line.startswith("+") and not line.startswith("+++"):
                L.append(c(line, "green"))
            elif line.startswith("-") and not line.startswith("---"):
                L.append(c(line, "red"))
            elif line.startswith("@@"):
                L.append(c(line, "magenta"))
            else:
                L.append(c(line, "dim"))
        L.append("")
    for n in plan.notes:
        L.append(c(f"note: {n}", "yellow"))
    if mask["masked"]:
        L.append(c(f"note: {mask['masked']} secret value(s) are masked in this display only; "
                   "the files keep their real values.", "yellow"))
    if plan.changes:
        L += ["", f"{len(plan.changes)} file(s) would change. To apply: "
              + c(f"nitaq protect --apply", "bold") + f" (you will be asked to type {APPLY_WORD})."]
    return "\n".join(L)


# ------------------------------------------------------------------ apply
def _sha(text: str | None) -> str | None:
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, text: str, mode: int | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".nitaq-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def backups_dir(home: Path) -> Path:
    return home / ".nitaq" / "backups"


def apply_plan(plan: Plan, confirm: str | None) -> dict:
    if confirm != APPLY_WORD:
        raise PermissionError(f"refused: --apply needs the confirmation word {APPLY_WORD}")
    if not plan.changes:
        return {"applied": 0}
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    bdir = backups_dir(plan.home) / stamp
    n = 1
    while bdir.exists():
        n += 1
        bdir = backups_dir(plan.home) / f"{stamp}-{n}"
    bdir.mkdir(parents=True)
    manifest = {"created": stamp, "nitaq_version": __version__, "home": str(plan.home), "files": []}
    # 1) verify nothing changed since planning, 2) back up everything FIRST
    for i, ch in enumerate(plan.changes):
        current = _read_exact(ch.path)
        if _sha(current) != _sha(ch.before):
            raise RuntimeError(f"{ch.path} changed after the plan was made; nothing was modified")
        entry = {"path": str(ch.path), "existed": ch.before is not None, "agent": ch.agent,
                 "mechanism": ch.mechanism, "sha256_before": _sha(ch.before), "sha256_after": _sha(ch.after),
                 "mode": (ch.path.stat().st_mode & 0o777) if ch.path.exists() else None}
        if ch.before is not None:
            entry["backup_file"] = f"{i:03d}.orig"
            (bdir / entry["backup_file"]).write_text(ch.before, encoding="utf-8", newline="")
        manifest["files"].append(entry)
    (bdir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    # 3) write atomically, validate, roll back on any failure
    done: list[Change] = []
    try:
        for ch, entry in zip(plan.changes, manifest["files"]):
            _atomic_write(ch.path, ch.after, entry["mode"])
            json.loads(_read_exact(ch.path))
            done.append(ch)
    except Exception:
        for ch in reversed(done):
            if ch.before is None:
                ch.path.unlink(missing_ok=True)
            else:
                _atomic_write(ch.path, ch.before, None)
        raise
    return {"applied": len(done), "backup": str(bdir), "backup_id": bdir.name}


def list_backups(home: Path) -> list[dict]:
    out = []
    d = backups_dir(home)
    if d.is_dir():
        for b in sorted(d.iterdir()):
            m = b / "manifest.json"
            if m.exists():
                man = json.loads(m.read_text(encoding="utf-8"))
                out.append({"id": b.name, "files": len(man["files"]), "created": man["created"]})
    return out


def plan_restore(home: Path, backup_id: str | None, force: bool = False) -> tuple[Path, list[dict], list[str]]:
    bl = list_backups(home)
    if not bl:
        raise FileNotFoundError("no Nitaq backups found")
    bid = backup_id or bl[-1]["id"]
    bdir = backups_dir(home) / bid
    if not (bdir / "manifest.json").exists():
        raise FileNotFoundError(f"backup {bid} not found")
    man = json.loads((bdir / "manifest.json").read_text(encoding="utf-8"))
    actions, problems = [], []
    for f in man["files"]:
        p = Path(f["path"])
        current = _read_exact(p)
        if _sha(current) != f["sha256_after"]:
            problems.append(f"{display_path(p, home)} changed after Nitaq wrote it")
        restored = _read_exact(bdir / f["backup_file"]) if f.get("existed") else None
        actions.append({"path": p, "current": current, "restored": restored, "mode": f.get("mode")})
    if problems and not force:
        problems.append("refusing to restore (use --force to overwrite your later edits)")
    return bdir, actions, problems


def render_restore(home: Path, actions: list[dict]) -> str:
    out = []
    for a in actions:
        name = display_path(a["path"], home)
        cur = (a["current"] or "").splitlines(keepends=True)
        new = (a["restored"] or "").splitlines(keepends=True)
        out.append("".join(difflib.unified_diff(cur, new, fromfile=f"current/{name}",
                                                tofile="/dev/null (delete)" if a["restored"] is None else f"restored/{name}", n=2)))
    return "\n".join(out)


def apply_restore(home: Path, actions: list[dict], problems: list[str], confirm: str | None, force: bool) -> int:
    if confirm != RESTORE_WORD:
        raise PermissionError(f"refused: unprotect needs the confirmation word {RESTORE_WORD}")
    if problems and not force:
        raise RuntimeError("; ".join(problems))
    for a in actions:
        if a["restored"] is None:
            a["path"].unlink(missing_ok=True)
        else:
            _atomic_write(a["path"], a["restored"], a["mode"])
    return len(actions)
