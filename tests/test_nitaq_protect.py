import io
import json

import pytest

from nitaq import protect as P
from nitaq.cli import main
from nitaq.discover import discover
from nitaq.testing.fake_home import build
from nitaq_helpers import SECRETS, tree_digest


@pytest.fixture
def fake(tmp_path):
    home, project = build(tmp_path)
    return tmp_path, home, project


def _files(root):
    return tree_digest(root, exclude=".nitaq")


def test_dry_run_changes_nothing_and_shows_exact_diff_without_secrets(fake, capsys):
    root, home, project = fake
    before = tree_digest(root)
    assert main(["protect", "--dry-run", "--home", str(home), "--project", str(project), "--no-color"]) == 0
    out = capsys.readouterr().out
    assert tree_digest(root) == before
    assert "DRY RUN" in out and "+++ b/~/.claude.json" in out and "+++ b/~/.gemini/settings.json" in out
    assert "mcp-proxy" in out and "hook claude-code" in out
    for s in SECRETS:
        assert s not in out
    assert ".cursor" not in out


def test_diff_masking_of_secret_values():
    from nitaq.redact import mask_diff_line
    st = {"masked": 0}
    assert "ghp_" not in mask_diff_line('       "GITHUB_TOKEN": "ghp_FAKEFAKEFAKEFAKEFAKEFAKEFAKE00",', st)
    assert "$KEY" in mask_diff_line('   "API_KEY": "$KEY"', st)               # a reference, not a secret
    assert "sk-" not in mask_diff_line('+        "sk-FAKEFAKEFAKEFAKEFAKEFAKE",', st)
    mask_diff_line('   "--api-key",', st)
    assert "hunter2" not in mask_diff_line('   "hunter2",', st)                # value after a secret flag
    assert mask_diff_line('   "-y",', st) == '   "-y",'
    assert st["masked"] == 3


def test_apply_requires_confirmation(fake, monkeypatch, capsys):
    root, home, project = fake
    before = tree_digest(root)
    monkeypatch.setattr("sys.stdin", io.StringIO("APPLY\n"))       # not a TTY: typed input is ignored
    assert main(["protect", "--apply", "--home", str(home), "--project", str(project)]) == 3
    assert main(["protect", "--apply", "--confirm", "yes", "--home", str(home), "--project", str(project)]) == 3
    assert tree_digest(root) == before
    with pytest.raises(PermissionError):
        P.apply_plan(P.make_plan(home, project), "apply")


def test_apply_backup_validate_idempotent_and_unprotect_restores_exactly(fake):
    root, home, project = fake
    before = _files(root)
    plan = P.make_plan(home, project)
    assert {c.mechanism for c in plan.changes} == {"policy-file", "pretooluse-hook+posttooluse-hook", "mcp-stdio-proxy"}
    res = P.apply_plan(plan, P.APPLY_WORD)
    man = json.loads((P.backups_dir(home) / res["backup_id"] / "manifest.json").read_text(encoding="utf-8"))
    assert len(man["files"]) == len(plan.changes) and all("sha256_after" in f for f in man["files"])
    cj = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    gh = cj["mcpServers"]["github"]
    assert gh["args"][-3:] == ["npx", "-y", "@modelcontextprotocol/server-github"]
    assert gh["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"].startswith("ghp_")           # env kept as is
    assert cj["mcpServers"]["docs"]["type"] == "http" and "args" not in cj["mcpServers"]["docs"]
    assert cj["numStartups"] == 12
    assert discover(home, project)["summary"]["stdio_servers_unprotected"] == 0
    assert P.make_plan(home, project).changes == []                                 # idempotent
    bdir, actions, problems = P.plan_restore(home, None)
    assert problems == []
    P.apply_restore(home, actions, problems, P.RESTORE_WORD, False)
    assert {k: v[0] for k, v in _files(root).items()} == {k: v[0] for k, v in before.items()}  # same bytes
    assert not (home / ".nitaq" / "policy.json").exists()


def test_unprotect_refuses_after_user_edits_unless_forced(fake):
    root, home, project = fake
    P.apply_plan(P.make_plan(home, project), P.APPLY_WORD)
    s = home / ".gemini" / "settings.json"
    s.write_text(s.read_text(encoding="utf-8").replace("Default", "Dark"), encoding="utf-8")
    bdir, actions, problems = P.plan_restore(home, None)
    assert any("changed after Nitaq wrote it" in p for p in problems)
    with pytest.raises(RuntimeError):
        P.apply_restore(home, actions, problems, P.RESTORE_WORD, False)
    bdir, actions, problems = P.plan_restore(home, None, force=True)
    P.apply_restore(home, actions, problems, P.RESTORE_WORD, True)
    assert "Default" in s.read_text(encoding="utf-8")


def test_unparseable_and_unsupported_files_are_never_modified(fake):
    root, home, project = fake
    g = home / ".gemini" / "settings.json"
    g.write_text('{"mcpServers": {"w": {"command": "node"}}, // comment\n}', encoding="utf-8")
    cursor_before = (home / ".cursor" / "mcp.json").read_bytes()
    plan = P.make_plan(home, project)
    assert all(c.path != g for c in plan.changes)
    assert any("not valid JSON" in n for n in plan.notes)
    P.apply_plan(plan, P.APPLY_WORD)
    assert g.read_text(encoding="utf-8").startswith('{"mcpServers": {"w": {"command": "node"}}, // comment')
    assert (home / ".cursor" / "mcp.json").read_bytes() == cursor_before


def test_apply_rolls_back_on_failure(fake, monkeypatch):
    root, home, project = fake
    before = _files(root)
    calls = {"n": 0}
    real = P._atomic_write

    def flaky(path, text, mode):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("disk full (simulated)")
        return real(path, text, mode)
    monkeypatch.setattr(P, "_atomic_write", flaky)
    with pytest.raises(OSError):
        P.apply_plan(P.make_plan(home, project), P.APPLY_WORD)
    assert {k: v[0] for k, v in _files(root).items()} == {k: v[0] for k, v in before.items()}


def test_apply_refuses_if_file_changed_after_planning(fake):
    root, home, project = fake
    plan = P.make_plan(home, project)
    (home / ".claude.json").write_text('{"mcpServers": {}}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="changed after the plan"):
        P.apply_plan(plan, P.APPLY_WORD)
    assert (home / ".claude.json").read_text(encoding="utf-8") == '{"mcpServers": {}}\n'


def test_hook_only_when_agent_installed_and_not_duplicated(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    assert P.make_plan(home, None).changes == []                  # no agent installed: nothing to do
    (home / ".claude").mkdir()
    plan = P.make_plan(home, None, mechs=("pretooluse-hook",))
    assert [c.mechanism for c in plan.changes] == ["policy-file", "pretooluse-hook"]
    P.apply_plan(plan, P.APPLY_WORD)
    settings = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))
    hook = settings["hooks"]["PreToolUse"][0]
    assert hook["matcher"] == "*" and hook["hooks"][0]["type"] == "command"
    assert "nitaq hook claude-code --policy" in hook["hooks"][0]["command"]
    assert P.make_plan(home, None, mechs=("pretooluse-hook",)).changes == []


def test_discover_sees_through_the_proxy_after_protect(fake):
    """Regression: wrapping must not hide the real server's risks or add false ones."""
    root, home, project = fake
    def risks():
        res = discover(home, project)
        return {s["name"]: ({r["rule"] for r in s["risks"]} - {"not_protected"}, s["command"] if "command" in s else "")
                for a in res["agents"] for asset in a["assets"] for s in asset.get("mcp_servers", [])}
    before = risks()
    P.apply_plan(P.make_plan(home, project), P.APPLY_WORD)
    after = risks()
    assert {n: r for n, (r, _) in after.items()} == {n: r for n, (r, _) in before.items()}
    assert "unpinned_package" in after["github"][0]
    assert after["github"][1].startswith("[nitaq proxy] npx -y @modelcontextprotocol/server-github")


def test_wrapped_servers_and_hooks_are_recognised(tmp_path):
    from nitaq.discover import is_our_hook, is_wrapped
    old = {"command": "/usr/bin/python3", "args": ["-m", "nitaq", "mcp-proxy", "--policy", "p", "--name", "x", "--", "npx", "pkg"]}
    assert is_wrapped(old) and is_wrapped({"command": "/x/bin/nitaq", "args": ["mcp-proxy", "--", "node"]})
    assert not is_wrapped({"command": "npx", "args": ["-y", "mcp-proxy-server"]})
    assert is_our_hook("python3 -m nitaq hook claude-code --policy p") and is_our_hook("nitaq hook claude-code")
    assert not is_our_hook("./scripts/hook-lint.sh")



def test_claude_settings_get_pre_and_post_hooks_once(fake):
    root, home, project = fake
    P.apply_plan(P.make_plan(home, project), P.APPLY_WORD)
    hooks = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))["hooks"]
    assert "hook claude-code --policy" in hooks["PreToolUse"][0]["hooks"][0]["command"]
    assert "hook claude-code-post --policy" in hooks["PostToolUse"][0]["hooks"][0]["command"]
    assert P.make_plan(home, project).changes == []


def test_crlf_files_are_handled_and_keep_their_line_endings(fake):
    """Regression (found by Windows CI): CRLF configs made --apply refuse with 'changed after the plan'."""
    root, home, project = fake
    for p in (home / ".claude" / "settings.json", home / ".claude.json", home / ".gemini" / "settings.json"):
        p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    before = {k: v[0] for k, v in tree_digest(root, exclude=".nitaq").items()}
    plan = P.make_plan(home, project)
    gem = next(c for c in plan.changes if c.path.name == "settings.json" and ".gemini" in str(c.path))
    assert "\r\n" in gem.after and "\n" not in gem.after.replace("\r\n", "")
    assert len([l for l in gem.diff(home).splitlines() if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]) < 25
    P.apply_plan(plan, P.APPLY_WORD)
    assert (home / ".claude.json").read_bytes().count(b"\r\n") > 5
    bdir, actions, problems = P.plan_restore(home, None)
    assert problems == []
    P.apply_restore(home, actions, problems, P.RESTORE_WORD, False)
    assert {k: v[0] for k, v in tree_digest(root, exclude=".nitaq").items()} == before
