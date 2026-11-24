"""Minimal Gemini API client (REST, standard library only) with model fallback.

Docs: https://ai.google.dev/api/generate-content  (function calling: https://ai.google.dev/gemini-api/docs/function-calling)
The key is read from GEMINI_API_KEY / GOOGLE_API_KEY, a .env file in the current folder, or the
Nitaq config file written by `nitaq agent --set-key`.  It is sent only to Google's API host, in a header.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Light models first: fast and cheap.  If one is overloaded (429/503) or gone (404) the next is tried.
MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash")
RETRY_CODES = (429, 500, 502, 503, 504)


class GeminiError(RuntimeError):
    pass


def config_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "nitaq"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "nitaq"


def key_file() -> Path:
    return config_dir() / "gemini.key"


def _from_dotenv(path: Path) -> str | None:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() in ("GEMINI_API_KEY", "GOOGLE_API_KEY") and v.strip():
                return v.strip().strip("'\"")
    except OSError:
        pass
    return None


def find_key(cwd: Path | None = None) -> str | None:
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(name, "").strip():
            return os.environ[name].strip()
    k = _from_dotenv(Path(cwd or Path.cwd()) / ".env")
    if k:
        return k
    try:
        k = key_file().read_text(encoding="utf-8").strip()
        return k or None
    except OSError:
        return None


def save_key(key: str) -> Path:
    p = key_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(key.strip(), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return p


def _http(url: str, body: dict, key: str, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"content-type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class Gemini:
    def __init__(self, key: str, models: tuple[str, ...] | list[str] = MODELS, timeout: float = 45,
                 transport=None) -> None:
        self.key = key
        self.models = list(dict.fromkeys(models))
        self.timeout = timeout
        self.transport = transport or _http
        self.last_model = self.models[0]

    def generate(self, system: str, contents: list[dict], tools: list[dict], temperature: float = 0.2) -> list[dict]:
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                "tools": [{"functionDeclarations": tools}] if tools else [],
                "generationConfig": {"temperature": temperature}}
        order = [self.last_model] + [m for m in self.models if m != self.last_model]
        errors = []
        for model in order:
            for attempt in range(2):
                try:
                    data = self.transport(API.format(model=model), body, self.key, self.timeout)
                except urllib.error.HTTPError as e:
                    detail = ""
                    try:
                        detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
                    except (ValueError, OSError):
                        pass
                    errors.append(f"{model}: HTTP {e.code} {detail[:120]}")
                    if e.code in (401, 403):
                        raise GeminiError(f"the API key was refused (HTTP {e.code}). {detail[:200]}") from e
                    if e.code == 400 and "signature" in detail.lower():
                        _strip_signatures(contents)
                        continue
                    if e.code in RETRY_CODES and attempt == 0:
                        time.sleep(1.5)
                        continue
                    break                                   # 404 / 400 / second failure: next model
                except (urllib.error.URLError, TimeoutError, OSError) as e:
                    errors.append(f"{model}: {getattr(e, 'reason', e)}")
                    break
                cands = data.get("candidates") or []
                if not cands:
                    reason = (data.get("promptFeedback") or {}).get("blockReason", "no answer")
                    errors.append(f"{model}: {reason}")
                    break
                parts = (cands[0].get("content") or {}).get("parts") or []
                self.last_model = model
                return parts or [{"text": ""}]
        raise GeminiError("no Gemini model answered: " + "; ".join(errors[-4:]))


def _strip_signatures(contents: list[dict]) -> None:
    for c in contents:
        for p in c.get("parts", []):
            p.pop("thoughtSignature", None)
