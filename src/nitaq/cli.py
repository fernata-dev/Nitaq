"""`nitaq` command line.  With no arguments it runs `discover` (read-only)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nitaq import __version__

COMMANDS = ("discover", "agents", "scan", "protect", "unprotect", "policy", "mcp-proxy", "hook", "bench", "demo", "ui", "shortcut", "agent", "gateway")


def _home(a) -> Path:
    from nitaq.registry import default_home
    return Path(a.home).expanduser().resolve() if a.home else default_home()


def _project(a) -> Path | None:
    if getattr(a, "no_project", False):
        return None
    return Path(a.project).expanduser().resolve() if a.project else Path.cwd()


def _agents(a):
    return tuple(x.strip() for x in a.agent.split(",")) if getattr(a, "agent", None) else None


def cmd_discover(a) -> int:
    from nitaq.discover import discover, render
    res = discover(_home(a), _project(a), _agents(a))
    if a.out:
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else render(res))
    if a.out and not a.json:
        print(f"\nJSON report written to {a.out}")
    return 0


def cmd_agents(a) -> int:
    from nitaq.registry import load_registry
    from nitaq.term import c
    reg = load_registry()
    print(c(f"Supported agents (verified against official docs on {reg['verified_on']}):", "bold"))
    for ag in reg["agents"]:
        mech = ", ".join(m["id"] for m in ag.get("mechanisms", [])) or "scan-only"
        print(f"  {c(ag['id'], 'bgreen'):<22} {ag['name']}  [{ag['support']}: {mech}]")
        for d in ag["docs"]:
            print(c(f"      {d}", "dim"))
    print(c("Not supported:", "bold"))
    for ns in reg["not_supported"]:
        print(f"  {c(ns['id'], 'yellow'):<22} {ns['reason']}")
    print(c("Nitaq does not support 'any AI'. Details: docs/INTEGRATIONS.md", "dim"))
    return 0


def cmd_scan(a) -> int:
    from nitaq_bench.cli import main as bench_main
    argv = ["scan-skill", a.path] + (["--json"] if a.json else []) + (["--sarif"] if a.sarif else []) + \
        (["--allow", a.allow] if a.allow else []) + (["--fail-on", a.fail_on] if a.fail_on else [])
    return bench_main(argv)


def _confirm(word: str, given: str | None) -> str | None:
    if given is not None:
        return given
    if not sys.stdin.isatty():
        return None
    try:
        return input(f"Type {word} to continue (anything else cancels): ").strip()
    except EOFError:
        return None


def cmd_protect(a) -> int:
    from nitaq import protect as P
    home = _home(a)
    mechs = tuple(x.strip() for x in a.mechanism.split(",")) if a.mechanism else None
    plan = P.make_plan(home, _project(a), _agents(a), mechs, Path(a.policy).expanduser() if a.policy else None)
    print(P.render_plan(plan))
    if not a.apply:
        return 0
    if not plan.changes:
        return 0
    word = _confirm(P.APPLY_WORD, a.confirm)
    try:
        res = P.apply_plan(plan, word)
    except PermissionError as exc:
        print(f"\n{exc}. Nothing was changed.")
        return 3
    except Exception as exc:
        print(f"\nFAILED and rolled back: {exc}")
        return 4
    print(f"\nApplied {res['applied']} change(s). Backup: {res['backup']}")
    print(f"Undo with: nitaq unprotect --backup {res['backup_id']}")
    return 0


def cmd_unprotect(a) -> int:
    from nitaq import protect as P
    home = _home(a)
    if a.list:
        for b in P.list_backups(home):
            print(f"{b['id']}  files={b['files']}")
        return 0
    try:
        bdir, actions, problems = P.plan_restore(home, a.backup, a.force)
    except FileNotFoundError as exc:
        print(exc)
        return 1
    print(f"Restore from backup {bdir.name}:\n")
    print(P.render_restore(home, actions) or "(files already identical to the backup)")
    for p in problems:
        print(f"warning: {p}")
    if a.dry_run:
        print("\ndry run: nothing changed.")
        return 0
    word = _confirm(P.RESTORE_WORD, a.confirm)
    try:
        n = P.apply_restore(home, actions, problems, word, a.force)
    except (PermissionError, RuntimeError) as exc:
        print(f"\n{exc}. Nothing was changed.")
        return 3
    print(f"\nRestored {n} file(s) from {bdir}.")
    return 0


def cmd_policy(a) -> int:
    from nitaq.policy import DEFAULT_POLICY, evaluate, load_policy
    pol = load_policy(Path(a.policy).expanduser()) if a.policy else dict(DEFAULT_POLICY)
    if a.action == "show":
        print(json.dumps(pol, indent=2))
        return 0
    d = evaluate(a.tool, json.loads(a.args or "{}"), pol, _home(a))
    print(json.dumps(d.to_dict(), indent=2))
    return 0 if d.allowed else 1


def cmd_mcp_proxy(a) -> int:
    from nitaq.mcp_proxy import main
    cmd = a.server[1:] if a.server[:1] == ["--"] else a.server
    return main(a.policy, a.name, cmd)


def cmd_hook(a) -> int:
    from nitaq.hook_claude import main
    return main(a.policy, "post" if a.agent == "claude-code-post" else "pre")


def cmd_bench(a) -> int:
    from nitaq_bench.cli import main as bench_main
    return bench_main(a.rest or ["--help"])


def cmd_ui(a) -> int:
    from nitaq.ui.server import serve
    return serve(_home(a), _project(a), a.port, not a.no_browser, getattr(a, "classic", False))


def cmd_shortcut(a) -> int:
    from nitaq.shortcut import run
    return run(_home(a), "remove" if a.remove else "install", a.dry_run)


def cmd_demo(a) -> int:
    from nitaq_bench.cli import main as bench_main
    return bench_main(["demo", "--port", str(a.port)])


def cmd_agent(a) -> int:
    from nitaq.agent.app import main
    return main(a)


def cmd_gateway(a) -> int:
    from nitaq.gateway import main
    return main(a)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nitaq", description="Nitaq: discover, scan and (opt-in) protect AI agent "
                                "setups. Runs `discover` (read-only) when called without a command.")
    p.add_argument("--version", action="version", version=f"nitaq {__version__}")
    p.add_argument("--no-color", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    def common(s, project=True):
        s.add_argument("--home", help="home directory to inspect (default: yours); used by tests with a fake HOME")
        if project:
            s.add_argument("--project", help="project directory (default: current directory)")
            s.add_argument("--no-project", action="store_true")
        s.add_argument("--agent", help="limit to agent ids, e.g. claude-code,gemini-cli")

    s = sub.add_parser("discover", help="READ-ONLY: find supported agents' configs, skills and MCP servers")
    common(s)
    s.add_argument("--json", action="store_true"); s.add_argument("--out", help="also write the JSON report here")
    s.set_defaults(fn=cmd_discover)

    s = sub.add_parser("agents", help="list supported agents and their official doc sources")
    s.set_defaults(fn=cmd_agents)

    s = sub.add_parser("scan", help="scan a SKILL.md / tool manifest / folder (reads text only)")
    s.add_argument("path"); s.add_argument("--json", action="store_true"); s.add_argument("--sarif", action="store_true")
    s.add_argument("--allow"); s.add_argument("--fail-on", choices=("low", "medium", "high"))
    s.set_defaults(fn=cmd_scan)

    s = sub.add_parser("protect", help="OPT-IN: preview (--dry-run, default) or --apply protection")
    common(s)
    g = s.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="show the exact diff (default)")
    g.add_argument("--apply", action="store_true", help="apply after typed confirmation; backup first")
    s.add_argument("--confirm", help="non-interactive confirmation word (APPLY)")
    s.add_argument("--mechanism", help="mcp-stdio-proxy,pretooluse-hook")
    s.add_argument("--policy", help="policy file (default ~/.nitaq/policy.json)")
    s.set_defaults(fn=cmd_protect)

    s = sub.add_parser("unprotect", help="restore a protect backup")
    s.add_argument("--home"); s.add_argument("--backup"); s.add_argument("--list", action="store_true")
    s.add_argument("--dry-run", action="store_true"); s.add_argument("--confirm"); s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_unprotect)

    s = sub.add_parser("policy", help="show the policy or test a decision")
    s.add_argument("action", choices=("show", "check")); s.add_argument("--policy"); s.add_argument("--home")
    s.add_argument("--tool", default=""); s.add_argument("--args")
    s.set_defaults(fn=cmd_policy)

    s = sub.add_parser("mcp-proxy", help="run an MCP stdio server behind the Nitaq policy")
    s.add_argument("--policy"); s.add_argument("--name", default="server")
    s.add_argument("server", nargs=argparse.REMAINDER)
    s.set_defaults(fn=cmd_mcp_proxy)

    s = sub.add_parser("hook", help="agent hook entry points (documented mechanisms only)")
    s.add_argument("agent", choices=("claude-code", "claude-code-post")); s.add_argument("--policy")
    s.set_defaults(fn=cmd_hook)

    s = sub.add_parser("bench", help="the Nitaq research benchmark (needs a checkout of the repository)")
    s.add_argument("rest", nargs=argparse.REMAINDER)
    s.set_defaults(fn=cmd_bench)

    s = sub.add_parser("ui", help="open the Nitaq control center (local only; its own app window when possible)")
    common(s)
    s.add_argument("--port", type=int, default=8777)
    s.add_argument("--no-browser", action="store_true", help="only print the link")
    s.add_argument("--classic", action="store_true", help="open the phone-style app instead of the control center")
    s.set_defaults(fn=cmd_ui)

    s = sub.add_parser("shortcut", help="add Nitaq to your app menu (Linux; opt-in)")
    s.add_argument("--home"); s.add_argument("--remove", action="store_true"); s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_shortcut)

    s = sub.add_parser("agent", help="light AI agent for the terminal (Gemini), guarded by Nitaq")
    s.add_argument("-p", "--prompt", help="run one request and exit")
    s.add_argument("--workspace", help="folder the agent works in (default: current folder)")
    s.add_argument("--model", help="Gemini model (default: gemini-3.5-flash-lite, with fallbacks)")
    s.add_argument("--lang", choices=("ar", "en"), default="ar")
    s.add_argument("--allow", action="append", help="extra allowed host (repeatable)")
    s.add_argument("--no-guard", action="store_true", help="unprotected comparison mode (network only simulated)")
    s.add_argument("--init", metavar="DIR", help="create the demo workspace (two test skills, fake data) and exit")
    s.add_argument("--set-key", action="store_true", help="save your Gemini API key (asked without echo)")
    s.add_argument("--mcp", action="append", metavar="URL", help="also use the tools of an MCP server (e.g. nitaq gateway)")
    s.add_argument("--demo", choices=("1", "2", "3"), help="start with a prepared demo request (1: skill1, 2: skill2, 3: e-mail via --mcp)")
    s.set_defaults(fn=cmd_agent)

    s = sub.add_parser("gateway", help="MCP server that guards AI agents (local or cloud) and your tools")
    s.add_argument("action", nargs="?", choices=("serve", "config", "status", "approve", "deny", "restore",
                                                 "restrict", "reset"), default="serve")
    s.add_argument("id", nargs="?", help="request id for approve / deny")
    s.add_argument("--stdio", action="store_true", help="speak MCP on stdin/stdout (Claude Desktop, Gemini CLI...)")
    s.add_argument("--host", default="127.0.0.1", help="address to listen on (default 127.0.0.1)")
    s.add_argument("--port", type=int, default=8787)
    s.add_argument("--new-token", action="store_true", help="make a new secret URL")
    s.add_argument("--open", action="store_true", help="open the approvals dashboard in the browser")
    s.add_argument("--home", help=argparse.SUPPRESS)
    s.add_argument("--allow-origin", action="append", metavar="URL",
                   help="let this website call the MCP URL from the browser (e.g. the Nitaq site's connect panel)")
    s.add_argument("--upstream", nargs=argparse.REMAINDER, help="-- CMD ARGS: guard another MCP stdio server")
    s.set_defaults(fn=cmd_gateway)

    s = sub.add_parser("demo", help="local Arabic demo UI of the benchmark")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(fn=cmd_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    no_color = "--no-color" in argv and "--" not in argv[:argv.index("--no-color")]
    if no_color:
        argv.remove("--no-color")
    if not any(x in COMMANDS for x in argv) and not any(x in ("-h", "--help", "--version") for x in argv):
        argv = ["discover"] + argv          # discover is the default first step
    p = build_parser()
    a = p.parse_args(argv)
    from nitaq.term import set_color
    set_color(False if (a.no_color or no_color) else None)
    if not a.cmd:
        a = p.parse_args(["discover"])
    return int(a.fn(a) or 0)
