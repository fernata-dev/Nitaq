"""Load authored attack records and expand them into the evaluation matrix."""
from __future__ import annotations

from pathlib import Path

from nitaq_bench.attacks import encoders as E
from nitaq_bench.attacks.schema import SOURCES, validate_dataset
from nitaq_bench.env.tasks import compatible_tasks
from nitaq_bench.util import project_root, read_jsonl, stable_int

ATTACK_DIRS = ("data/attacks/ai_draft", "data/attacks/student_written")


def load_base(root: Path | None = None, validate: bool = True) -> list[dict]:
    root = root or project_root()
    records: list[dict] = []
    for d in ATTACK_DIRS:
        for path in sorted((root / d).glob("*.jsonl")):
            for rec in read_jsonl(path):
                rec["_file"] = str(path.relative_to(root))
                records.append(rec)
    if validate:
        errs, _ = validate_dataset(records)
        if errs:
            raise ValueError("attack data failed validation:\n  " + "\n  ".join(errs))
    return records


def expand_variants(base: dict, encodings: tuple[str, ...] | None = None, seed: int = 0) -> list[dict]:
    """One authored record -> one variant per applicable (encoding, source)."""
    encodings = encodings or E.ENCODINGS
    sources = SOURCES if base["source"] == "*" else (base["source"],)
    out = []
    for enc in encodings:
        enc_seed = stable_int(seed, base["id"], enc)
        if not E.applicable(enc, base["text"], enc_seed):
            continue
        encoded = E.encode(enc, base["text"], enc_seed)
        for src in sources:
            if not compatible_tasks(src, base["intent"]):
                continue
            out.append({
                "id": f"{base['id']}__{enc}__{src}",
                "base_id": base["id"],
                "lang": base["lang"],
                "encoding": enc,
                "source": src,
                "intent": base["intent"],
                "text": E.present(enc, encoded),
                "intended_call": base["intended_call"],
                "author": base["author"] if enc == "none" else "programmatic",
                "base_author": base["author"],
                "split": base["split"],
            })
    return out


def load_variants(split: str | None = None, root: Path | None = None, seed: int = 0,
                  encodings: tuple[str, ...] | None = None,
                  authors: tuple[str, ...] | None = None) -> list[dict]:
    out = []
    for base in load_base(root):
        if split and base["split"] != split:
            continue
        if authors and base["author"] not in authors:
            continue
        out.extend(expand_variants(base, encodings, seed))
    return out


def applicability_table(root: Path | None = None) -> dict[str, dict[str, bool]]:
    """lang -> encoding -> does any authored text of that language change under it."""
    table: dict[str, dict[str, bool]] = {}
    for base in load_base(root):
        row = table.setdefault(base["lang"], {e: False for e in E.ENCODINGS})
        for enc in E.ENCODINGS:
            if E.applicable(enc, base["text"], stable_int(0, base["id"], enc)):
                row[enc] = True
    return table
