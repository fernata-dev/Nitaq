import json

import pytest

from nitaq_bench.agents.fake_llm_server import FAKE_MODEL, start
from nitaq_bench.agents.llm_adapter import LLMAgent, OllamaClient, OpenAICompatClient
from nitaq_bench.agents.protocol import build_system, parse_tool_call
from nitaq_bench.cli import main
from nitaq_bench.eval import runner
from nitaq_bench.eval.pilot import _public_endpoint


@pytest.mark.parametrize("raw,expected", [
    ('{"tool": "read_page", "args": {"url": "u"}}', ("read_page", {"url": "u"})),
    ('Sure!\n```json\n{"tool": "send_email", "args": {"to": "a@test.local"}}\n```', ("send_email", {"to": "a@test.local"})),
    ('<think>{"tool": "x", "args": {}} hmm</think>{"tool": "final_answer", "args": {"text": "تم"}}', ("final_answer", {"text": "تم"})),
    ('{"name": "read_file", "arguments": "{\\"path\\": \\"notes/a\\"}"}', ("read_file", {"path": "notes/a"})),
    ('{"tool_calls": [{"function": {"name": "read_email", "arguments": "{\\"id\\": \\"inbox-1\\"}"}}]}', ("read_email", {"id": "inbox-1"})),
    ("{'tool': 'final_answer', 'args': {'text': 'ok'}}", ("final_answer", {"text": "ok"})),
    ('{"note": 1} then {"tool": "read_page", "args": {"url": "v"}}', ("read_page", {"url": "v"})),
    ('{"tool": "final_answer", "args": "plain text answer"}', ("final_answer", {"text": "plain text answer"})),
])
def test_parse_tool_call_variants(raw, expected):
    assert parse_tool_call(raw) == expected


@pytest.mark.parametrize("raw", ["", "I will read the page now.", "{broken json", '{"tool": 5, "args": {}}'])
def test_parse_tool_call_rejects_garbage(raw):
    assert parse_tool_call(raw) is None


def test_system_prompt_includes_tools_and_skills():
    s = build_system({"read_page": "Fetch."}, [{"name": "fmt", "text": "مهارة"}])
    assert "read_page(url)" in s and "[skill: fmt]" in s and "مهارة" in s


def test_clients_report_unreachable_endpoints_without_crashing(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    chk = OllamaClient("m").check()
    assert chk["ok"] is False and "not reachable" in chk["reason"]
    for v in ("NITAQ_BASE_URL", "BASE_URL"):
        monkeypatch.delenv(v, raising=False)
    assert OpenAICompatClient("m").check()["ok"] is False


@pytest.fixture
def fake_endpoint(monkeypatch, tmp_path):
    srv, url = start()
    monkeypatch.setenv("BASE_URL", url)
    monkeypatch.setenv("MODEL", FAKE_MODEL)
    monkeypatch.setenv("API_KEY", "dummy")
    yield url
    srv.shutdown()


def test_llm_agent_end_to_end_with_scripted_endpoint(fake_endpoint, tmp_path):
    client = OpenAICompatClient(raw_dir=tmp_path, max_calls=500)
    assert client.check()["ok"]
    agent = LLMAgent(client)
    cases = runner.build_cases("dev", langs=("en",), encodings=("none", "b64"), sources=("email",),
                               intents=("wrong_recipient",))
    rows, st = runner.run_matrix(cases, ["D0", "D5"], agent, repeats=3, llm_client=client)
    assert len(rows) == len(cases) * 2 * 3
    by = {(r["encoding"], r["defense"]): r for r in rows if r["kind"] == "attack"}
    assert by[("none", "D0")]["success"] is True            # plain address: scripted responder obeys
    assert by[("b64", "D0")]["success"] is False            # it cannot decode
    assert by[("none", "D5")]["success"] is False and by[("none", "D5")]["attempted"] is True
    raw = list(tmp_path.glob("*.jsonl"))
    assert raw and all("response" in json.loads(l) or "error" in json.loads(l)
                       for l in raw[0].read_text(encoding="utf-8").splitlines())
    res = runner.package_results(rows, st, agent, split="dev", seed=1, repeats=3)
    assert res["meta"]["agent"]["model"] == FAKE_MODEL and res["meta"]["agent"]["temperature"] == 0
    assert res["tables"]["nondeterminism"]["max_repeats"] == 3


def test_max_calls_is_a_hard_cap(fake_endpoint, tmp_path):
    client = OpenAICompatClient(raw_dir=None, max_calls=5)
    cases = runner.build_cases("dev", langs=("en",), encodings=("none",), kinds=("attack",))
    rows, st = runner.run_matrix(cases, ["D0"], LLMAgent(client), repeats=3, llm_client=client,
                                 stop=client.exhausted)
    assert client.calls <= 5 and "_partial" in st


def test_pilot_records_not_run_when_no_model(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("NITAQ_ROOT", str(tmp_path))
    (tmp_path / "data").mkdir()
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    assert main(["pilot", "--agent", "ollama"]) == 0
    st = json.loads((tmp_path / "results" / "pilot_status.json").read_text(encoding="utf-8"))
    assert st["status"] == "not run" and st["reason"]


def test_public_endpoint_strips_paths_and_secrets():
    assert _public_endpoint("https://user:key@api.example.test:8443/v1?key=abc") == "https://api.example.test:8443"


def test_pilot_authors_filter_and_empty_student_set(fake_endpoint, monkeypatch, capsys):
    monkeypatch.setenv("BASE_URL", fake_endpoint)
    assert main(["pilot", "--agent", "openai", "--authors", "student", "--dry-run"]) == 2
    assert "student_written" in capsys.readouterr().out
    assert main(["pilot", "--agent", "openai", "--authors", "ai-draft", "--dry-run"]) == 0
    assert "cases=" in capsys.readouterr().out
