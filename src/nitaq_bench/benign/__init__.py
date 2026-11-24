"""Benign content: schema, loader and expansion (used for false positives and utility)."""
from __future__ import annotations

import re
from pathlib import Path

from nitaq_bench.attacks.schema import AUTHORS, LANGS, SOURCES, SPLITS, _ID, _safety_errors, script_stats
from nitaq_bench.env.tasks import SOURCE_TASKS
from nitaq_bench.util import project_root, read_jsonl

BENIGN_DIRS = ("data/benign/ai_draft", "data/benign/student_written")
CATEGORIES = ("plain", "trigger_like", "delegation", "encoded_benign")
REQUIRED = ("id", "lang", "sources", "category", "text", "author", "split")


def validate_benign(rec: dict) -> list[str]:
    errs = [f"missing field: {k}" for k in REQUIRED if k not in rec]
    if errs:
        return errs
    if not isinstance(rec["id"], str) or not _ID.match(rec["id"]):
        errs.append(f"bad id: {rec['id']!r}")
    if rec["lang"] not in LANGS:
        errs.append(f"bad lang: {rec['lang']!r}")
    if not isinstance(rec["sources"], list) or not rec["sources"] or any(s not in SOURCES for s in rec["sources"]):
        errs.append(f"bad sources: {rec['sources']!r}")
    if rec["category"] not in CATEGORIES:
        errs.append(f"bad category: {rec['category']!r}")
    if rec["author"] not in AUTHORS or rec["author"] == "programmatic":
        errs.append(f"bad author: {rec['author']!r}")
    if rec["split"] not in SPLITS:
        errs.append(f"bad split: {rec['split']!r}")
    if not isinstance(rec["text"], str) or not rec["text"].strip():
        errs.append("text must be a non-empty string")
        return errs
    errs.extend(_safety_errors(rec["text"], "text"))
    extra = rec.get("expected_extra_call")
    if rec["category"] == "delegation":
        if not (isinstance(extra, dict) and extra.get("tool") and isinstance(extra.get("args"), dict)):
            errs.append("delegation records need expected_extra_call {tool, args}")
        elif rec["sources"] != ["email"]:
            errs.append("delegation records must have sources ['email']")
        else:
            for v in extra["args"].values():
                if isinstance(v, str) and "@" in v and not v.endswith("test.local"):
                    errs.append(f"expected_extra_call names a non-mock address: {v}")
                if v == "attacker@test.local":
                    errs.append("a benign record cannot point at the mock attacker")
    elif extra is not None:
        errs.append("expected_extra_call is only allowed for category 'delegation'")
    st = script_stats(re.sub(r"[A-Za-z0-9+/=]{24,}", " ", rec["text"]))
    if rec["lang"] == "en" and st["arabic"] > 0:
        errs.append("lang=en but text contains Arabic-script letters")
    if rec["lang"] in ("msa", "arz") and st["arabic_share"] < 0.6:
        errs.append(f"lang={rec['lang']} but Arabic-script share is {st['arabic_share']:.2f}")
    if rec["lang"] == "arabizi" and st["arabic"] > 0:
        errs.append("lang=arabizi but text contains Arabic-script letters")
    return errs


def load_benign(split: str | None = None, root: Path | None = None,
                authors: tuple[str, ...] | None = None) -> list[dict]:
    root = root or project_root()
    records, errs, seen = [], [], set()
    for d in BENIGN_DIRS:
        for path in sorted((root / d).glob("*.jsonl")):
            for rec in read_jsonl(path):
                e = validate_benign(rec)
                errs.extend(f"{rec.get('id', '<no id>')}: {x}" for x in e)
                if rec.get("id") in seen:
                    errs.append(f"{rec.get('id')}: duplicate id")
                seen.add(rec.get("id"))
                records.append(rec)
    if errs:
        raise ValueError("benign data failed validation:\n  " + "\n  ".join(errs))
    out = []
    for rec in records:
        if split and rec["split"] != split:
            continue
        if authors and rec["author"] not in authors:
            continue
        out.append(rec)
    return out


def expand_benign(rec: dict) -> list[dict]:
    """One benign record -> one variant per source it is declared for."""
    out = []
    for src in rec["sources"]:
        if not SOURCE_TASKS.get(src):
            continue
        out.append({
            "id": f"{rec['id']}__{src}",
            "base_id": rec["id"],
            "lang": rec["lang"],
            "source": src,
            "category": rec["category"],
            "text": rec["text"],
            "expected_extra_call": rec.get("expected_extra_call"),
            "author": rec["author"],
            "split": rec["split"],
        })
    return out
