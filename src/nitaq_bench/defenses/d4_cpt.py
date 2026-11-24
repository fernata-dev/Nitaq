"""D4: characters-per-token filter in the style of Broken-Token (optional).

Idea: obfuscated text (Base64, leet, zero-width, spaced letters) splits into
many short tokens, so its characters-per-token (CPT) ratio is low.  D4 flags
content whose CPT is below a threshold.

Requires a BPE tokenizer.  We use tiktoken's `cl100k_base` ONLY if its
vocabulary file is already in tiktoken's local cache.  Nitaq never downloads it
(HARD RULE 2: no network calls except a user-configured LLM endpoint).  To
enable D4, fetch the file yourself once, e.g.
    python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"
If it is not cached, D4 is SKIPPED and every results file says so; no fallback
"tokenizer" is invented.

POST-FREEZE CHANGE (recorded in CHANGELOG.md and docs/post_freeze_changes.json):
the cache check was added after the freeze because tiktoken otherwise tries to
download the vocabulary.  D4 was skipped in every run before and after.

Threshold: calibrated on the DEV benign split only (the 5th percentile of CPT
over dev benign texts), per script group (Arabic script vs Latin script),
because the same tokenizer gives Arabic far fewer characters per token.

FROZEN at git tag `freeze-scanner`.
"""
from __future__ import annotations

import re
from functools import lru_cache

from nitaq_bench.defenses.base import Defense, ScreenVerdict

_AR = re.compile(r"[؀-ۿ]")


_VOCAB_URL = "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"


def _cache_file():
    import hashlib
    import os
    import tempfile
    from pathlib import Path

    d = os.environ.get("TIKTOKEN_CACHE_DIR") or os.environ.get("DATA_GYM_CACHE_DIR") or \
        os.path.join(tempfile.gettempdir(), "data-gym-cache")
    return Path(d) / hashlib.sha1(_VOCAB_URL.encode()).hexdigest()


@lru_cache(maxsize=1)
def _encoding():
    try:
        import tiktoken  # optional dependency
    except ImportError:
        return None, "tiktoken is not installed (pip install tiktoken)"
    if not _cache_file().exists():
        return None, ("cl100k_base vocabulary is not in the local tiktoken cache; Nitaq never downloads it "
                      "(see the D4 docstring to enable it)")
    try:
        return tiktoken.get_encoding("cl100k_base"), ""
    except Exception as exc:
        return None, f"tokenizer vocabulary could not be loaded ({type(exc).__name__})"


def cpt(text: str) -> float | None:
    enc, _ = _encoding()
    if enc is None or not text:
        return None
    n = len(enc.encode(text))
    return len(text) / n if n else None


def _group(text: str) -> str:
    return "arabic" if len(_AR.findall(text)) > 0.3 * max(1, sum(c.isalpha() for c in text)) else "latin"


@lru_cache(maxsize=1)
def thresholds() -> dict[str, float]:
    from nitaq_bench.benign import load_benign

    vals: dict[str, list[float]] = {"arabic": [], "latin": []}
    for rec in load_benign("dev"):
        c = cpt(rec["text"])
        if c is not None:
            vals[_group(rec["text"])].append(c)
    out = {}
    for g, xs in vals.items():
        xs.sort()
        if xs:
            out[g] = xs[max(0, int(0.05 * len(xs)) - 1)] * 0.95
    return out


class D4CharsPerToken(Defense):
    name = "D4"
    kind = "scanner"
    description = "Characters-per-token filter (Broken-Token style), tiktoken cl100k_base, dev-calibrated."

    def available(self) -> tuple[bool, str]:
        enc, why = _encoding()
        return (enc is not None), why

    def screen(self, text: str, source: str) -> ScreenVerdict:
        c = cpt(text)
        if c is None:
            return ScreenVerdict(False, defense=self.name)
        g = _group(text)
        th = thresholds().get(g)
        if th is None:
            return ScreenVerdict(False, defense=self.name)
        flagged = c < th
        return ScreenVerdict(flagged, round(c, 3),
                             [{"rule": "low_chars_per_token", "evidence": f"cpt={c:.2f} < {th:.2f} ({g})"}]
                             if flagged else [], self.name)
