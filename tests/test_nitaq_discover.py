import builtins
import json
import os
import socket
from pathlib import Path

import pytest

from nitaq.cli import main
from nitaq.discover import discover, render
from nitaq.registry import load_registry, resolve_locations
from nitaq.testing.fake_home import build
from nitaq_helpers import SECRETS, tree_digest


@pytest.fixture
def fake(tmp_path):
    home, project = build(tmp_path)
    return tmp_path, home, project


def test_registry_is_documented_and_shipped_copy_is_identical():
    root = Path(__file__).resolve().parents[1]
    assert (root / "data/supported_agents.json").read_bytes() == (root / "src/nitaq/_data/supported_agents.json").read_bytes()
    reg = load_registry()
    integrations = (root / "docs/INTEGRATIONS.md").read_text(encoding="utf-8")
    ids = {a["id"] for a in reg["agents"]}
    assert ids == {"claude-code", "gemini-cli"}
    assert not ids & {x["id"] for x in reg["not_supported"]}
    for a in reg["agents"]:
        assert a["docs"] and a["support"] in ("protect", "scan-only")
        for url in a["docs"]:
            assert url.startswith("https://") and url in integrations
        for m in a.get("mechanisms", []):
            assert m["doc"] in a["docs"]
        for loc in a["locations"]:
            assert loc["path"].startswith(("~/", "{project}/"))


def test_discover_is_read_only_offline_and_never_opens_unsupported_or_secret_files(fake, monkeypatch):
    root, home, project = fake
    before = tree_digest(root)
    opened = []
    real_open = builtins.open

    def guarded_open(file, mode="r", *a, **k):
        if any(ch in mode for ch in "wax+"):
            raise AssertionError(f"write attempted: {file} {mode}")
        opened.append(str(file))
        return real_open(file, mode, *a, **k)

    def no(*a, **k):
        raise AssertionError("filesystem modification attempted")

    monkeypatch.setattr(builtins, "open", guarded_open)
    for fn in ("replace", "rename", "remove", "unlink", "mkdir", "makedirs", "rmdir", "chmod"):
        monkeypatch.setattr(os, fn, no)
    monkeypatch.setattr(socket.socket, "connect", lambda *a: (_ for _ in ()).throw(AssertionError("network")))
    res = discover(home, project)
    text = render(res)
    monkeypatch.undo()
    assert tree_digest(root) == before
    assert not any(".cursor" in p or ".ssh" in p for p in opened)
    blob = json.dumps(res) + text
    for s in SECRETS:
        assert s not in blob
    assert res["read_only"] is True


def test_discover_findings(fake):
    _, home, project = fake
    res = discover(home, project)
    cc = next(a for a in res["agents"] if a["id"] == "claude-code")
    skills = {s["skill"]: s for asset in cc["assets"] for s in asset.get("skills", [])}
    assert skills["pdf-helper"]["verdict"] == "high-risk"
    assert skills["commit-helper"]["verdict"] == "no-major-findings"
    assert skills["release-notes"]["verdict"] == "no-major-findings"
    servers = {s["name"]: s for a in res["agents"] for asset in a["assets"] for s in asset.get("mcp_servers", [])}
    assert set(servers) == {"notes", "github", "docs", "sqlite", "fs", "weather"}
    rules = lambda n: {r["rule"] for r in servers[n]["risks"]}
    assert "unpinned_package" in rules("github") and "unpinned_package" not in rules("fs")
    assert "secret_in_args" in rules("sqlite") and "<redacted" in servers["sqlite"]["command"]
    assert servers["docs"]["transport"] == "http" and "remote_server" in rules("docs")
    assert servers["github"]["env_keys"] == ["GITHUB_PERSONAL_ACCESS_TOKEN"]
    assert servers["sqlite"]["scope"].startswith("local:")
    assert res["summary"]["stdio_servers_unprotected"] == 5
    assert {x["id"] for x in res["not_supported"]} >= {"cursor", "claude-desktop"}


def test_symlink_outside_and_invalid_json_and_missing_agent(tmp_path):
    home = tmp_path / "home"
    (home / ".claude" / "skills" / "x").mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("---\nname: o\ndescription: o\n---\nsecret stuff\n", encoding="utf-8")
    try:
        (home / ".claude" / "skills" / "x" / "SKILL.md").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need extra privileges on this OS")
    (home / ".gemini").mkdir()
    (home / ".gemini" / "settings.json").write_text("{ // comment\n}", encoding="utf-8")
    res = discover(home, None)
    cc = next(a for a in res["agents"] if a["id"] == "claude-code")
    sk = [s for asset in cc["assets"] for s in asset.get("skills", [])][0]
    assert sk["read"] is False and "outside" in sk["note"]
    gm = next(a for a in res["agents"] if a["id"] == "gemini-cli")
    assert gm["assets"][0]["parsed"] is False
    assert not any(asset["exists"] for asset in cc["assets"] if asset["kind"] == "mcp_config")


def test_only_home_and_project_relative_locations(fake):
    _, home, project = fake
    for loc in resolve_locations(load_registry(), home, project):
        assert str(loc.path).startswith((str(home), str(project)))
    assert all(l.scope == "user" for l in resolve_locations(load_registry(), home, None))


def test_cli_default_is_discover_and_json_out(fake, capsys, tmp_path):
    _, home, project = fake
    out = tmp_path / "report.json"
    assert main(["--home", str(home), "--project", str(project), "--no-color", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "Nitaq discover" in text and "Nothing was modified" in text
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["skills_high_risk"] == 1
    assert main(["agents", "--no-color"]) == 0
    assert "does not support 'any AI'" in capsys.readouterr().out
