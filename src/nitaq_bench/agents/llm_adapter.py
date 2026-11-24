"""Real-model adapters: Ollama and any OpenAI-compatible endpoint.

Configuration (environment variables; nothing is sent anywhere unless set):
  OpenAI-compatible:  BASE_URL (e.g. http://localhost:8000/v1), API_KEY, MODEL
  Ollama:             OLLAMA_HOST (default http://127.0.0.1:11434), MODEL
NITAQ_BASE_URL / NITAQ_API_KEY / NITAQ_MODEL take precedence if set.

Every request/response is appended to results/raw/<run>.jsonl.  Temperature is
0 and a fixed seed is sent; repeats (N=3 by default) measure what
nondeterminism remains.  --max-calls is a hard cap.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from nitaq_bench.agents.base import Agent
from nitaq_bench.agents.protocol import build_system, parse_tool_call, tool_result_message
from nitaq_bench.util import DEFAULT_SEED, now_iso

CALLS_PER_EPISODE = 4        # typical: read, (maybe extra), answer, + 1 retry budget


class LLMError(RuntimeError):
    pass


def _env(*names: str, default: str | None = None) -> str | None:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default


class LLMClient:
    kind = "base"
    sec_per_call = 3.0

    def __init__(self, model: str | None, raw_dir: Path | None = None, max_calls: int = 2000,
                 temperature: float = 0.0, seed: int = DEFAULT_SEED, timeout: float = 120.0) -> None:
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self.timeout = timeout
        self.max_calls = max_calls
        self.calls = 0
        self.errors = 0
        self.seconds = 0.0
        self.version: str | None = None
        self.context: dict = {}
        self.raw_path = None
        if raw_dir is not None:
            raw_dir.mkdir(parents=True, exist_ok=True)
            stamp = now_iso().replace(":", "").replace("-", "")
            slug = "".join(c if c.isalnum() else "-" for c in f"{self.kind}_{model}")
            self.raw_path = raw_dir / f"{slug}_{stamp}.jsonl"

    # -- interface -------------------------------------------------------
    def endpoint(self) -> str:
        raise NotImplementedError

    def _request(self, messages: list[dict]) -> tuple[str, dict]:
        raise NotImplementedError

    def check(self) -> dict:
        raise NotImplementedError

    # -- shared ----------------------------------------------------------
    def exhausted(self) -> bool:
        return self.calls >= self.max_calls

    def chat(self, messages: list[dict], purpose: str = "agent") -> str:
        if self.exhausted():
            raise LLMError(f"--max-calls={self.max_calls} reached")
        self.calls += 1
        t0 = time.time()
        try:
            text, meta = self._request(messages)
        except Exception as exc:
            self.errors += 1
            self._log({"purpose": purpose, "error": f"{type(exc).__name__}: {exc}", "messages": messages})
            raise
        dt = time.time() - t0
        self.seconds += dt
        self._log({"purpose": purpose, "messages": messages, "response": text, "meta": meta,
                   "latency_s": round(dt, 3)})
        return text

    def _log(self, rec: dict) -> None:
        if not self.raw_path:
            return
        rec = {"time": now_iso(), "model": self.model, "kind": self.kind, **self.context, **rec}
        with open(self.raw_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def usage(self) -> dict:
        return {"calls": self.calls, "errors": self.errors, "seconds": round(self.seconds, 1),
                "raw_log": str(self.raw_path) if self.raw_path else None}

    def estimate(self, n_episodes: int) -> dict:
        calls = min(self.max_calls, n_episodes * CALLS_PER_EPISODE)
        return {"max_calls": calls, "calls_per_episode": CALLS_PER_EPISODE,
                "sec_per_call": self.sec_per_call, "minutes": calls * self.sec_per_call / 60}

    def _post(self, url: str, payload: dict, headers: dict | None = None) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            raise LLMError(f"HTTP {exc.code} from {url}: {body}") from exc

    def _get(self, url: str, headers: dict | None = None) -> dict:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=min(self.timeout, 10)) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def info(self) -> dict:
        return {"model": self.model, "version": self.version, "temperature": self.temperature,
                "seed": self.seed, "endpoint": self.endpoint(), "kind": self.kind}


class OllamaClient(LLMClient):
    kind = "ollama"
    sec_per_call = 4.0

    def __init__(self, model=None, **kw) -> None:
        self.host = _env("OLLAMA_HOST", default="http://127.0.0.1:11434").rstrip("/")
        if not self.host.startswith("http"):
            self.host = "http://" + self.host
        super().__init__(model or _env("NITAQ_MODEL", "MODEL"), **kw)

    def endpoint(self) -> str:
        return self.host

    def check(self) -> dict:
        try:
            tags = self._get(self.host + "/api/tags")
        except Exception as exc:
            return {"ok": False, "endpoint": self.host, "reason": f"Ollama not reachable: {type(exc).__name__}: {exc}"}
        models = [m.get("name") for m in tags.get("models", [])]
        if not self.model:
            if not models:
                return {"ok": False, "endpoint": self.host, "reason": "Ollama has no models (ollama pull <model>)"}
            self.model = models[0]
        if self.model not in models and f"{self.model}:latest" not in models:
            return {"ok": False, "endpoint": self.host, "models": models,
                    "reason": f"model {self.model!r} not installed"}
        try:
            show = self._post(self.host + "/api/show", {"model": self.model})
            det = show.get("details", {})
            self.version = "|".join(str(x) for x in (show.get("digest") or det.get("parameter_size"),
                                                      det.get("quantization_level"), det.get("family")) if x)
        except Exception:
            self.version = None
        return {"ok": True, "endpoint": self.host, "model": self.model, "version": self.version, "models": models}

    def _request(self, messages):
        out = self._post(self.host + "/api/chat", {
            "model": self.model, "messages": messages, "stream": False,
            "options": {"temperature": self.temperature, "seed": self.seed}})
        return out.get("message", {}).get("content", ""), {
            "eval_count": out.get("eval_count"), "prompt_eval_count": out.get("prompt_eval_count")}


class OpenAICompatClient(LLMClient):
    kind = "openai"
    sec_per_call = 2.0

    def __init__(self, model=None, **kw) -> None:
        self.base = (_env("NITAQ_BASE_URL", "BASE_URL") or "").rstrip("/")
        self.key = _env("NITAQ_API_KEY", "API_KEY") or ""
        super().__init__(model or _env("NITAQ_MODEL", "MODEL"), **kw)

    def endpoint(self) -> str:
        return self.base or "(BASE_URL not set)"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.key}"} if self.key else {}

    def check(self) -> dict:
        if not self.base:
            return {"ok": False, "reason": "BASE_URL is not set"}
        if not self.model:
            return {"ok": False, "reason": "MODEL is not set"}
        try:
            text, meta = self._request([{"role": "user", "content": 'Reply with {"tool": "final_answer", "args": {"text": "ok"}}'}])
        except Exception as exc:
            return {"ok": False, "endpoint": self.base, "reason": f"{type(exc).__name__}: {exc}"}
        return {"ok": True, "endpoint": self.base, "model": self.model, "version": self.version,
                "sample": text[:100]}

    def _request(self, messages):
        out = self._post(self.base + "/chat/completions", {
            "model": self.model, "messages": messages, "temperature": self.temperature,
            "seed": self.seed}, self._headers())
        self.version = out.get("system_fingerprint") or out.get("model") or self.version
        choice = (out.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        text = msg.get("content") or ""
        if not text and msg.get("tool_calls"):
            text = json.dumps({"tool_calls": msg["tool_calls"]})
        return text, {"usage": out.get("usage"), "finish_reason": choice.get("finish_reason")}


def make_client(kind: str, raw_dir: Path | None = None, max_calls: int = 2000, model: str | None = None):
    if kind == "ollama":
        return OllamaClient(model, raw_dir=raw_dir, max_calls=max_calls)
    if kind == "openai":
        return OpenAICompatClient(model, raw_dir=raw_dir, max_calls=max_calls)
    raise ValueError(f"unknown LLM kind: {kind}")


class LLMAgent(Agent):
    """Drives an episode with a real model through the JSON tool-call protocol."""
    simulated = False

    def __init__(self, client: LLMClient, max_parse_retries: int = 1) -> None:
        self.client = client
        self.name = f"llm:{client.kind}:{client.model}"
        self.label = "real model"
        self.max_parse_retries = max_parse_retries
        self.repeat = 0

    def set_repeat(self, rep: int) -> None:
        self.repeat = rep

    def info(self) -> dict:
        d = super().info()
        d.update(self.client.info())
        d["name"] = self.name
        return d

    def run(self, episode) -> None:
        from nitaq_bench.eval.episode import EpisodeOver

        self.client.context = {"case_id": episode.case.case_id, "defense": episode.stack.name,
                               "repeat": self.repeat}
        msgs = [{"role": "system", "content": build_system(episode.context.tools, episode.context.skills)},
                {"role": "user", "content": episode.context.instruction}]
        episode.parse_failures = 0
        while not episode.done:
            raw = self.client.chat(msgs, purpose="agent")
            call = parse_tool_call(raw)
            retries = 0
            while call is None and retries < self.max_parse_retries:
                retries += 1
                episode.parse_failures += 1
                msgs += [{"role": "assistant", "content": raw},
                         {"role": "user", "content": 'Invalid format. Reply with ONE JSON object: {"tool": "...", "args": {...}}'}]
                raw = self.client.chat(msgs, purpose="agent-retry")
                call = parse_tool_call(raw)
            if call is None:
                episode.parse_failures += 1
                episode.error = "unparseable_model_output"
                return
            tool, args = call
            msgs.append({"role": "assistant", "content": raw})
            try:
                res = episode.call(tool, args)
            except EpisodeOver:
                return
            if episode.done:
                return
            msgs.append({"role": "user", "content": tool_result_message(tool, res.status, res.content)})
