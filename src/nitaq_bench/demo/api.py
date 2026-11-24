"""Demo API: thin adapters from JSON requests to the evaluator's own functions.

Nothing here decides anything.  Episodes run through nitaq_bench.eval.episode.run_episode,
defenses come from nitaq_bench.defenses.registry, variants from nitaq_bench.attacks.loader /
encoders, skill scans from nitaq_bench.skillscan.scanner, result tables and go/no-go
from nitaq_bench.eval.report.
"""
from __future__ import annotations

import re

from nitaq_bench.agents.obedient_mock import WORST_CASE_LABEL, ObedientMock
from nitaq_bench.attacks import encoders as E
from nitaq_bench.attacks.loader import expand_variants, load_base
from nitaq_bench.benign import load_benign
from nitaq_bench.defenses import registry
from nitaq_bench.env import world as W
from nitaq_bench.env.tasks import INTENT_TASKS, SOURCE_TASKS, TASKS, compatible_tasks
from nitaq_bench.eval.episode import Case, run_episode
from nitaq_bench.eval.report import DEF_ORDER, defenses_in, go_no_go, load_all
from nitaq_bench.skillscan.scanner import scan_text
from nitaq_bench.util import project_root

DEMO_DEFENSES = ("D0", "D1", "D2", "D4", "D5-tools", "D5-args", "D5-taint", "D5", "D2+D5")
INTENT_CALLS = {
    "exfil_send": {"tool": "send_email", "args": {"to": W.ATTACKER_EMAIL}},
    "wrong_recipient": {"tool": "send_email", "args": {"to": W.ATTACKER_EMAIL}},
    "override": {"tool": "http_post", "args": {"url": W.ATTACKER_URL}},
}
_MARKER = re.compile(r"\b[A-Z]{2,}-[A-Z0-9-]{3,}\b")


class BadRequest(ValueError):
    pass


def meta() -> dict:
    defs = []
    for d in DEMO_DEFENSES:
        ok, why = registry.availability(d)
        stack = registry.build(d) if ok else None
        defs.append({"name": d, "available": ok, "why": why,
                     "description": " | ".join(x.description for x in stack.defenses) if stack else ""})
    attacks = [{k: b[k] for k in ("id", "lang", "intent", "text", "split", "author")}
               for b in load_base()]
    benign = [{k: b[k] for k in ("id", "lang", "category", "text", "split", "author", "sources")}
              for b in load_benign()]
    return {
        "banner": WORST_CASE_LABEL,
        "tasks": {n: {"instruction": t.instruction, "instruction_ar": t.instruction_ar,
                      "allowed_tools": list(t.manifest.allowed_tools),
                      "arg_constraints": t.manifest.arg_constraints} for n, t in TASKS.items()},
        "source_tasks": {k: list(v) for k, v in SOURCE_TASKS.items()},
        "intent_tasks": {k: list(v) for k, v in INTENT_TASKS.items()},
        "encodings": [{"name": e, "family": E.ENCODING_FAMILY[e]} for e in E.ENCODINGS],
        "defenses": defs,
        "presets": {"attack": attacks, "benign": benign},
        "attacker": {"email": W.ATTACKER_EMAIL, "url": W.ATTACKER_URL},
    }


def _variant(req: dict) -> tuple[str, dict]:
    kind = req.get("kind", "attack")
    source = req.get("source")
    enc = req.get("encoding", "none")
    if source not in SOURCE_TASKS:
        raise BadRequest("unknown source")
    if enc not in E.ENCODINGS:
        raise BadRequest("unknown encoding")
    preset = req.get("preset_id")
    if kind == "attack":
        if preset:
            base = next((b for b in load_base() if b["id"] == preset), None)
            if not base:
                raise BadRequest("unknown preset")
            base = dict(base, source=source)
            vs = [v for v in expand_variants(base, (enc,)) if v["source"] == source]
            if not vs:
                raise BadRequest(f"encoding '{enc}' does not apply to this text or source (N/A cell)")
            return kind, vs[0]
        text = str(req.get("text", ""))[:4000]
        intent = req.get("intent")
        if not text.strip():
            raise BadRequest("empty text")
        if intent == "in_scope_tamper":
            m = req.get("marker") or (_MARKER.search(text).group(0) if _MARKER.search(text) else None)
            if not m or m not in text:
                raise BadRequest("in_scope_tamper needs an ASCII marker (e.g. ACCT-0000-FAKE) that appears in the text")
            call = {"tool": "@output", "args": {"contains": m}}
        elif intent in INTENT_CALLS:
            call = INTENT_CALLS[intent]
        else:
            raise BadRequest("unknown intent")
        if not compatible_tasks(source, intent):
            raise BadRequest("this intent does not apply to this source")
        payload = E.present(enc, E.encode(enc, text, 0))
        return kind, {"id": "demo", "base_id": "demo", "lang": req.get("lang", "mixed"), "encoding": enc,
                      "source": source, "intent": intent, "text": payload, "intended_call": call,
                      "author": "demo", "split": "demo"}
    if kind == "benign":
        text = str(req.get("text", ""))[:4000]
        if preset:
            rec = next((b for b in load_benign() if b["id"] == preset), None)
            if not rec:
                raise BadRequest("unknown preset")
            text = rec["text"]
        if not text.strip():
            raise BadRequest("empty text")
        return kind, {"id": "demo", "base_id": "demo", "lang": req.get("lang", "mixed"), "source": source,
                      "category": "demo", "text": text, "expected_extra_call": None, "author": "demo",
                      "split": "demo", "encoding": "none"}
    raise BadRequest("kind must be attack or benign")


def run(req: dict) -> dict:
    kind, v = _variant(req)
    task = req.get("task")
    allowed = compatible_tasks(v["source"], v.get("intent") if kind == "attack" else None)
    if task not in allowed:
        raise BadRequest(f"task must be one of {allowed} for this source/intent")
    names = [d for d in (req.get("defenses") or DEMO_DEFENSES) if d in DEMO_DEFENSES]
    agent = ObedientMock()
    out = []
    for d in names:
        ok, why = registry.availability(d)
        if not ok:
            out.append({"defense": d, "skipped": why})
            continue
        ep, res = run_episode(Case("demo", kind, v, task), registry.build(d), agent)
        out.append({"defense": d, "result": res, "trace": ep.log,
                    "screens": [s for s in ep.screens if s["flagged"] or s["is_case_site"]],
                    "outbox": ep.world.outbox, "posts": ep.world.posts, "answers": ep.world.answers})
    return {"agent": agent.info(), "banner": WORST_CASE_LABEL, "payload": v["text"],
            "intended_call": v.get("intended_call"), "task": TASKS[task].instruction, "runs": out}


def results() -> dict:
    data = load_all()
    out = {"sets": []}
    for split, r in data["sim"].items():
        out["sets"].append(_pack(f"sim_{split}", r, simulated=True))
    for r in data["pilot"]:
        out["sets"].append(_pack(r["_path"], r, simulated=False))
    out["pilot_status"] = data["pilot_status"]
    return out


def _pack(name: str, r: dict, simulated: bool) -> dict:
    t = r["tables"]
    return {"name": name, "simulated": simulated, "meta": {k: r["meta"].get(k) for k in
            ("generated_at", "seed", "split", "agent", "git", "defense_status")},
            "digest": r["digest"], "defenses": defenses_in(r),
            "by_defense": t["attack"]["asr"]["by_defense"],
            "lang_encoding": t["attack"]["asr"]["by_defense_lang_encoding"],
            "by_intent": t["attack"]["asr"]["by_defense_intent"],
            "utility": t["benign"]["utility"]["by_defense"],
            "fpr": t["benign"]["false_positive_rate"]["by_defense"],
            "counts": t["counts"], "go_no_go": go_no_go(r)}


def fixtures() -> dict:
    d = project_root() / "fixtures"
    return {p.name: p.read_text(encoding="utf-8", errors="replace")[:50000]
            for p in sorted(d.glob("*")) if p.is_file() and p.suffix in (".md", ".json")}


def scan_skill(req: dict) -> dict:
    text = str(req.get("text", ""))[:200000]
    allow = tuple(a.strip().lower() for a in str(req.get("allow", "")).split(",") if a.strip())
    name = str(req.get("name", "pasted SKILL.md"))[:100]
    return scan_text(text, name, allow)
