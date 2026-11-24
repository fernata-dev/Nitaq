"""Build every report artifact from results files.  No number is typed by hand.

Inputs   results/sim_test.json, results/sim_dev.json, results/llm_pilot_*.json,
         results/pilot_status.json
Outputs  report/results.json, report/index.html, report/tables/*.csv,
         CLAIMS_ALLOWED.md, CLAIMS_NOT_ALLOWED.md, docs/PILOT_DECISION.md,
         docs/CLAIM_AUDIT.md (numeric part), generated blocks in README.md

Wording here is template text filled with computed numbers.  It describes
numbers; it does not interpret them.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from nitaq_bench.attacks.encoders import CORE_ENCODINGS, ENCODING_FAMILY, ENCODINGS
from nitaq_bench.eval.metrics import cell, intervals_overlap
from nitaq_bench.eval.runner import collapse_repeats
from nitaq_bench.util import project_root, read_json, write_csv, write_json

LANG_ORDER = ("en", "msa", "arz", "arabizi", "mixed")
LANG_AR = {"en": "إنجليزي", "msa": "فصحى", "arz": "مصري", "arabizi": "فرانكو", "mixed": "مخلوط"}
DEF_ORDER = ("D0", "D1", "D2", "D3", "D4", "D5-tools", "D5-args", "D5-taint", "D6", "D5", "D2+D5")
SIM_LABEL = "worst-case simulated agent, not a real model"
FAKE_PREFIX = "nitaq-fake"


# ---------------------------------------------------------------- loading
def load_all(root: Path | None = None) -> dict:
    root = root or project_root()
    res: dict = {"sim": {}, "pilot": [], "pilot_status": None, "paths": {}}
    for split in ("test", "dev"):
        p = root / "results" / f"sim_{split}.json"
        if p.exists():
            res["sim"][split] = read_json(p)
            res["paths"][f"sim_{split}"] = f"results/sim_{split}.json"
    for p in sorted((root / "results").glob("llm_pilot_*.json")):
        r = read_json(p)
        if str(r["meta"]["agent"].get("model", "")).startswith(FAKE_PREFIX):
            continue
        r["_path"] = f"results/{p.name}"
        res["pilot"].append(r)
    sp = root / "results" / "pilot_status.json"
    if sp.exists():
        res["pilot_status"] = read_json(sp)
    return res


def pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def fmt(c: dict | None, cluster: bool = False) -> str:
    if not c or c.get("rate") is None:
        return "n/a"
    s = f"{pct(c['rate'])} [{pct(c['ci_lo'])}, {pct(c['ci_hi'])}] ({c['k']}/{c['n']})"
    if cluster:
        s += f"; cluster CI {('[' + pct(c['cluster_ci_lo']) + ', ' + pct(c['cluster_ci_hi']) + ']') if c.get('cluster_ci_lo') is not None else 'n/a (<5 texts)'}"
    return s


def find(rows: list[dict], **kw) -> tuple[int, dict] | tuple[None, None]:
    for i, r in enumerate(rows):
        if all(r.get(k) == v for k, v in kw.items()):
            return i, r
    return None, None


def defenses_in(result: dict) -> list[str]:
    ds = [r["defense"] for r in result["tables"]["attack"]["asr"]["by_defense"]]
    return [d for d in DEF_ORDER if d in ds] + [d for d in ds if d not in DEF_ORDER]


# ---------------------------------------------------------------- go / no-go
def pooled(result: dict, defense: str, langs, encodings) -> dict:
    rows = collapse_repeats([r for r in result["rows"] if r["kind"] == "attack"
                             and r["defense"] == defense and r["lang"] in langs
                             and r["encoding"] in encodings])
    c = cell(sum(1 for r in rows if r["success"]), len(rows))
    c["n_base"] = len({r["base_id"] for r in rows})
    return c


GROUPS = [
    ("msa, unencoded", ("msa",), ("none",)),
    ("arz, unencoded", ("arz",), ("none",)),
    ("arabizi, unencoded", ("arabizi",), ("none",)),
    ("mixed, unencoded", ("mixed",), ("none",)),
    ("en, core encodings pooled", ("en",), CORE_ENCODINGS),
    ("arz+arabizi, core encodings pooled", ("arz", "arabizi"), CORE_ENCODINGS),
]


def go_no_go(result: dict | None) -> dict | None:
    if not result:
        return None
    out = {"defenses": {}}
    present = defenses_in(result)
    for d in ("D1", "D2"):
        if d not in present:
            continue
        base = pooled(result, d, ("en",), ("none",))
        comps = []
        for label, langs, encs in GROUPS:
            c = pooled(result, d, langs, encs)
            if c["n"] == 0:
                continue
            ov = intervals_overlap(base, c)
            comps.append({"group": label, "cell": c,
                          "higher_non_overlapping": bool(c["rate"] is not None and base["rate"] is not None
                                                         and c["ci_lo"] > base["ci_hi"]),
                          "overlap": ov})
        out["defenses"][d] = {"baseline": {"group": "en, unencoded", "cell": base}, "comparisons": comps,
                              "any_gap": any(x["higher_non_overlapping"] for x in comps)}
    out["any_gap"] = any(v["any_gap"] for v in out["defenses"].values())
    return out


# ---------------------------------------------------------------- facts
class Facts:
    """Every number shown in README / claims is registered here with its source."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, fid: str, value: str, source: str, path: str) -> str:
        self.items.append({"id": fid, "value": value, "source": source, "json_path": path})
        return value


def asr_facts(F: Facts, result: dict, key: str, src: str) -> dict[str, str]:
    t = result["tables"]
    out = {}
    for d in defenses_in(result):
        i, c = find(t["attack"]["asr"]["by_defense"], defense=d)
        out[d] = F.add(f"{key}.asr.{d}", fmt(c), src, f"tables.attack.asr.by_defense[{i}]")
        j, u = find(t["benign"]["utility"]["by_defense"], defense=d)
        out[d + ".util"] = F.add(f"{key}.utility.{d}", fmt(u), src, f"tables.benign.utility.by_defense[{j}]")
        k, f = find(t["benign"]["false_positive_rate"]["by_defense"], defense=d)
        out[d + ".fpr"] = F.add(f"{key}.fpr.{d}", fmt(f), src, f"tables.benign.false_positive_rate.by_defense[{k}]")
    return out


# ---------------------------------------------------------------- markdown
def md_summary(F: Facts, data: dict) -> str:
    test = data["sim"].get("test")
    if not test:
        return "_No test-split results yet: run `python -m nitaq_bench eval --split test`._"
    src = data["paths"]["sim_test"]
    a = asr_facts(F, test, "sim_test", src)
    c = test["tables"]["counts"]
    lines = [f"Source: `{src}` (digest `{test['digest'][:16]}`, commit `{test['meta']['git']['commit'][:10]}`, "
             f"seed {test['meta']['seed']}). Agent: **{SIM_LABEL}**.", "",
             "| defense | attack success (Wilson 95% CI) | benign utility | benign flagged |",
             "|---|---|---|---|"]
    for d in defenses_in(test):
        lines.append(f"| {d} | {a[d]} | {a[d + '.util']} | {a[d + '.fpr']} |")
    skipped = {k: v for k, v in test["meta"]["defense_status"].items() if not k.startswith("_") and v != "run"}
    lines += ["", f"Attack cases: {F.add('sim_test.counts.attack_cases', str(c['attack_cases']), src, 'tables.counts.attack_cases')} "
              f"from {F.add('sim_test.counts.attack_base_texts', str(c['attack_base_texts']), src, 'tables.counts.attack_base_texts')} "
              f"authored texts; authors: {F.add('sim_test.counts.by_author', str(c['attack_base_by_author']), src, 'tables.counts.attack_base_by_author')}. "
              f"Benign cases: {F.add('sim_test.counts.benign_cases', str(c['benign_cases']), src, 'tables.counts.benign_cases')}."]
    if skipped:
        lines += ["", "Not run: " + "; ".join(f"{k} ({v})" for k, v in skipped.items()) + "."]
    pfc = test["meta"].get("freeze", {}).get("post_freeze_changes", [])
    lines += ["", f"Scanner freeze: {'OK' if test['meta'].get('freeze', {}).get('ok') else 'NOT OK'}; "
              f"post-freeze changes recorded: {len(pfc)}" + (" (" + "; ".join(
                  f"`{c['file']}`, affects results: {c['affects_results']}" for c in pfc) + "; see CHANGELOG.md)" if pfc else "") + "."]
    return "\n".join(lines)


def md_pilot(F: Facts, data: dict) -> str:
    st = data.get("pilot_status")
    if data["pilot"]:
        r = data["pilot"][0]
        m = r["meta"]["agent"]
        a = asr_facts(F, r, "pilot", r["_path"])
        lines = [f"Real-model pilot: model `{m.get('model')}` version `{m.get('version')}`, "
                 f"date {r['meta']['generated_at']}, temperature {m.get('temperature')}, "
                 f"repeats {r['meta']['repeats_requested']}. Source: `{r['_path']}`.", "",
                 "| defense | attack success | benign utility |", "|---|---|---|"]
        for d in defenses_in(r):
            lines.append(f"| {d} | {a[d]} | {a[d + '.util']} |")
        return "\n".join(lines)
    if st:
        F.add("pilot.status", st["status"], "results/pilot_status.json", "status")
        return (f"Real-model pilot: **{st['status'].upper()}** ({st.get('date')}). Reason: {st.get('reason')}. "
                f"Source: `results/pilot_status.json`. No statement about real models is supported.")
    return "Real-model pilot: **NOT RUN** (no status file)."


def md_go_no_go(F: Facts, data: dict) -> str:
    parts = ["# PILOT_DECISION (generated by `python -m nitaq_bench report`; do not edit by hand)", "",
             "Question: is D1/D2 attack success on arz / arabizi / encoded cases HIGHER than on "
             "English (unencoded) with NON-overlapping Wilson 95% intervals?", "",
             "Note: Wilson intervals treat variants of one authored text as independent. "
             "Cluster-bootstrap intervals (by authored text) are in report/results.json.", ""]
    verdicts = {}
    sources = []
    if "test" in data["sim"]:
        sources.append(("Worst-case simulator, test split", data["sim"]["test"], data["paths"]["sim_test"]))
    for r in data["pilot"]:
        sources.append((f"Real-model pilot ({r['meta']['agent'].get('model')})", r, r["_path"]))
    for title, res, src in sources:
        g = go_no_go(res)
        verdicts[title] = g["any_gap"]
        parts += [f"## {title}", "", f"Source: `{src}`", ""]
        for d, v in g["defenses"].items():
            b = v["baseline"]["cell"]
            parts += [f"### {d}", "", f"Baseline (en, unencoded): {F.add(f'gng.{src}.{d}.base', fmt(b), src, 'rows (pooled by report.go_no_go)')}", "",
                      "| group | attack success | higher with non-overlapping CI? |", "|---|---|---|"]
            for comp in v["comparisons"]:
                group = comp["group"]
                val = F.add(f"gng.{src}.{d}.{group}", fmt(comp["cell"]), src, "rows (pooled by report.go_no_go)")
                yes = "YES" if comp["higher_non_overlapping"] else "no"
                parts.append(f"| {group} | {val} | {yes} |")
            if b["rate"] is not None and b["rate"] >= 0.95:
                parts += ["", f"The English baseline for {d} is already {pct(b['rate'])}, so no group can be "
                          "higher with a non-overlapping interval."]
            parts.append("")
        parts.append(f"**Gap observed: {'YES' if g['any_gap'] else 'NO'}.**")
        parts.append("")
    dev = data["sim"].get("dev")
    if dev:
        g = go_no_go(dev)
        parts += ["## Informational only: worst-case simulator, dev split", "",
                  f"Source: `{data['paths']['sim_dev']}`. NOT used for the decision: D2's lexicon was written from "
                  "these texts, and the English dev texts and D1's English list were written by the same AI, "
                  "which makes D1's English baseline optimistic.", ""]
        for d, v in g["defenses"].items():
            b = v["baseline"]["cell"]
            parts += [f"- {d}: en unencoded {fmt(b)}; " + "; ".join(
                f"{c['group']} {fmt(c['cell'])}{' (higher, non-overlapping)' if c['higher_non_overlapping'] else ''}"
                for c in v["comparisons"])]
        parts.append("")
    if not data["pilot"]:
        st = data.get("pilot_status") or {}
        parts += ["## Real-model pilot", "",
                  f"**NOT RUN.** {st.get('reason', 'no status file')} (`results/pilot_status.json`). "
                  "The go/no-go question cannot be answered for real models.", ""]
    parts += ["## Decision", ""]
    if any(verdicts.values()):
        parts.append("GO for the language/encoding question in: " +
                     ", ".join(k for k, v in verdicts.items() if v) + ".")
    else:
        parts.append("NO GAP was observed under the rule above in: " + (", ".join(verdicts) or "nothing") + ".")
        parts.append("")
        parts.append("Parts of the project whose value does not depend on such a gap:")
        test = data["sim"].get("test")
        if test:
            src = data["paths"]["sim_test"]
            t = test["tables"]
            i, tam = find(t["attack"]["asr"]["by_defense_intent"], defense="D5", intent="in_scope_tamper")
            j, ut = find(t["benign"]["utility"]["by_defense"], defense="D5")
            k, dl = find(t["benign"]["utility"]["by_defense_category"], defense="D5", category="delegation")
            parts.append(f"- Guard cost and residual risk: D5 in_scope_tamper success "
                         f"{F.add('gng.d5.tamper', fmt(tam), src, f'tables.attack.asr.by_defense_intent[{i}]')}; "
                         f"D5 benign utility {F.add('gng.d5.util', fmt(ut), src, f'tables.benign.utility.by_defense[{j}]')}; "
                         f"D5 delegation utility {F.add('gng.d5.deleg', fmt(dl), src, f'tables.benign.utility.by_defense_category[{k}]')}.")
            dev = data["sim"].get("dev")
            if dev:
                a, ddev = find(dev["tables"]["attack"]["asr"]["by_defense"], defense="D2")
                b, dtest = find(t["attack"]["asr"]["by_defense"], defense="D2")
                parts.append(f"- Dev/test generalisation of a lexicon scanner: D2 attack success on dev "
                             f"{F.add('gng.d2.dev', fmt(ddev), data['paths']['sim_dev'], f'tables.attack.asr.by_defense[{a}]')} vs test "
                             f"{F.add('gng.d2.test', fmt(dtest), src, f'tables.attack.asr.by_defense[{b}]')}.")
        parts.append("- The skill scanner (fixture tests only; no detection rate is claimed).")
    return "\n".join(parts) + "\n"


def claims(F: Facts, data: dict) -> tuple[str, str]:
    allowed = ["# CLAIMS_ALLOWED (generated by `python -m nitaq_bench report`; do not edit by hand)", "",
               "Each statement is supported by the cited results file and JSON path. Statements about "
               f"the simulator must keep the label: \"{SIM_LABEL}\".", ""]
    test = data["sim"].get("test")
    dev = data["sim"].get("dev")
    if test:
        src = data["paths"]["sim_test"]
        t = test["tables"]
        n = 1
        for d in defenses_in(test):
            i, c = find(t["attack"]["asr"]["by_defense"], defense=d)
            allowed.append(f"{n}. With the {SIM_LABEL}, on the test split, {d} had attack success "
                           f"{F.add(f'claim.asr.{d}', fmt(c), src, f'tables.attack.asr.by_defense[{i}]')}. "
                           f"`{src}` → `tables.attack.asr.by_defense[{i}]`")
            n += 1
        for intent in ("exfil_send", "wrong_recipient", "override", "in_scope_tamper"):
            i, c = find(t["attack"]["asr"]["by_defense_intent"], defense="D5", intent=intent)
            if c:
                allowed.append(f"{n}. With the {SIM_LABEL}, D5 attack success for intent {intent}: "
                               f"{F.add(f'claim.d5.{intent}', fmt(c), src, f'tables.attack.asr.by_defense_intent[{i}]')}. "
                               f"`{src}` → `tables.attack.asr.by_defense_intent[{i}]`")
                n += 1
        for intent in ("override",):
            i, c = find(t["attack"]["task_completed_under_attack"]["by_defense_intent"], defense="D5", intent=intent)
            if c:
                allowed.append(f"{n}. Under D5, the user's task was still completed in "
                               f"{F.add('claim.d5.override.task', fmt(c), src, f'tables.attack.task_completed_under_attack.by_defense_intent[{i}]')} "
                               f"of override cases (simulator). `{src}` → `tables.attack.task_completed_under_attack.by_defense_intent[{i}]`")
                n += 1
        for d in ("D5-tools", "D5-args", "D5-taint", "D6", "D5"):
            i, c = find(t["benign"]["utility"]["by_defense_category"], defense=d, category="delegation")
            if c:
                allowed.append(f"{n}. {d} benign utility on legitimate delegation requests: "
                               f"{F.add(f'claim.deleg.{d}', fmt(c), src, f'tables.benign.utility.by_defense_category[{i}]')}. "
                               f"`{src}` → `tables.benign.utility.by_defense_category[{i}]`")
                n += 1
        for dname, label in (("D5-taint", "byte-exact taint"), ("D6", "normalised taint, designed after D5-taint's "
                                                                          "dev and test numbers were seen")):
            for enc in ("none", "b64", "zwsp", "homoglyph"):
                i, c = find(t["attack"]["asr"]["by_defense_encoding"], defense=dname, encoding=enc)
                if c:
                    allowed.append(f"{n}. {dname} ({label}; no argument constraints) attack success with encoding "
                                   f"{enc}: {F.add(f'claim.taint.{dname}.{enc}', fmt(c), src, f'tables.attack.asr.by_defense_encoding[{i}]')}. "
                                   f"`{src}` → `tables.attack.asr.by_defense_encoding[{i}]`")
                    n += 1
        if dev:
            a, cd = find(dev["tables"]["attack"]["asr"]["by_defense"], defense="D2")
            b, ct = find(t["attack"]["asr"]["by_defense"], defense="D2")
            allowed.append(f"{n}. D2 attack success was {F.add('claim.d2.dev', fmt(cd), data['paths']['sim_dev'], f'tables.attack.asr.by_defense[{a}]')} "
                           f"on the dev split (the split its lexicon was written from) and "
                           f"{F.add('claim.d2.test', fmt(ct), src, f'tables.attack.asr.by_defense[{b}]')} on the test split. "
                           f"`{data['paths']['sim_dev']}` and `{src}` → `tables.attack.asr.by_defense`")
            n += 1
        for p in t["paired"]["attack_success"]:
            if p["mcnemar_exact_p"] is not None and (p["a"], p["b"]) in (("D0", "D1"), ("D1", "D2"), ("D2", "D5"), ("D5-taint", "D5"), ("D5-tools", "D5-args"), ("D5-taint", "D6")):
                allowed.append(f"{n}. Paired on {p['text_pairs']} authored texts (majority outcome per text), {p['a']} vs "
                               f"{p['b']}: attack succeeded only under {p['a']} for {p['text_only_a']} texts and only under "
                               f"{p['b']} for {p['text_only_b']} texts (exact McNemar p = {_p(p['text_mcnemar_exact_p'])}). "
                               f"At case level ({p['n_pairs']} correlated cases): {p['only_a']} vs {p['only_b']}. "
                               f"`{src}` → `tables.paired.attack_success`")
                n += 1
        c = t["counts"]
        allowed.append(f"{n}. The test-split attack set has {c['attack_base_texts']} authored texts "
                       f"(by author: {c['attack_base_by_author']}), expanded to {c['attack_cases']} cases.")
    if data["pilot"]:
        for r in data["pilot"]:
            allowed.append(f"- Real-model pilot results exist for `{r['meta']['agent'].get('model')}` in `{r['_path']}`; "
                           "claims about that model must cite its tables and its date.")

    na = ["# CLAIMS_NOT_ALLOWED (generated by `python -m nitaq_bench report`; do not edit by hand)", "",
          "The numbers in this repository do NOT support the following:", "",
          "1. \"Nitaq prevents prompt injection\" / \"prevents all jailbreaks\" / \"first ever\". "
          "Nitaq reduces the damage an injected instruction can cause; it does not stop a model from following it.",
          "2. \"The guard stops the model from being fooled.\" The guard only blocks tool calls outside the task's manifest.",
          "3. \"The guard makes the agent safe.\" In-scope tampering (allowed channel, harmful content) is not blocked.",
          "4. Any statement that simulator numbers describe how often a real model follows injections. "
          f"The simulator is a {SIM_LABEL}."]
    k = 5
    if not data["pilot"]:
        na.append(f"{k}. Any statement about real LLMs, Ollama models or commercial models: the pilot was NOT RUN."); k += 1
    if test:
        c = test["tables"]["counts"]["attack_base_by_author"]
        if c.get("student", 0) == 0:
            na.append(f"{k}. Any statement about how Egyptians (or anyone) write injections, or about \"Egyptian Arabic\" in "
                      f"general: all test attack texts are AI drafts ({c}). Replace them with student-written texts first."); k += 1
        ps = [p for p in test["tables"]["paired"]["attack_success"]]
        weak = [f"{p['a']} vs {p['b']}" for p in ps if p.get("text_mcnemar_exact_p") is None or p["text_mcnemar_exact_p"] >= 0.05]
        na.append(f"{k}. \"Significant\" / \"significantly better\" for any pair whose TEXT-level exact McNemar p is missing or "
                  f">= 0.05 ({len(weak)} of {len(ps)} pairs, e.g. {', '.join(weak[:4])}). Case-level p-values must never be "
                  "quoted alone: cases derived from one authored text are correlated."); k += 1
        small = [r for r in test["tables"]["attack"]["asr"]["by_defense_lang"] if r["n_base"] < 5]
        if small:
            na.append(f"{k}. Per-language rates as population estimates: {len(small)} defense x language cells rest on fewer "
                      "than 5 authored texts (no cluster-bootstrap CI)."); k += 1
        skipped = [d for d, s in test["meta"]["defense_status"].items() if not d.startswith("_") and s != "run"]
        if skipped:
            na.append(f"{k}. Any result for {', '.join(skipped)}: not run ({'; '.join(test['meta']['defense_status'][d] for d in skipped)})."); k += 1
    na += [f"{k}. Detection rates for D2 measured on the dev split as evidence of performance: the lexicon was written from dev.",
           f"{k + 1}. Detection rates for the skill scanner: it was only checked on synthetic fixtures, not on a held-out corpus.",
           f"{k + 2}. Results for language x encoding cells marked N/A (the encoding does not change that script).",
           f"{k + 3}. Claims about other tokenizers, other models, or attacks not in this benchmark (e.g. multi-turn, images)."]
    return "\n".join(allowed) + "\n", "\n".join(na) + "\n"


# ---------------------------------------------------------------- CSV
def write_tables(data: dict, out: Path) -> list[str]:
    written = []
    for name, res in [(f"sim_{k}", v) for k, v in data["sim"].items()] + \
                     [(Path(r["_path"]).stem, r) for r in data["pilot"]]:
        t = res["tables"]
        for kind in ("attack", "benign"):
            for metric, by in t[kind].items():
                for bname, rows in by.items():
                    if not rows:
                        continue
                    keys = [k for k in rows[0] if k not in ("k", "n", "rate", "ci_lo", "ci_hi", "n_base",
                                                             "cluster_ci_lo", "cluster_ci_hi")]
                    cols = keys + ["k", "n", "rate", "ci_lo", "ci_hi", "n_base", "cluster_ci_lo", "cluster_ci_hi"]
                    p = out / f"{name}__{kind}__{metric}__{bname}.csv"
                    write_csv(p, cols, ([r.get(c) for c in cols] for r in rows))
                    written.append(p.name)
        for outcome, rows in t["paired"].items():
            if rows:
                cols = list(rows[0])
                p = out / f"{name}__paired__{outcome}.csv"
                write_csv(p, cols, ([r.get(c) for c in cols] for r in rows))
                written.append(p.name)
    return written


# ---------------------------------------------------------------- HTML
def _heat(rate: float | None) -> tuple[str, str]:
    if rate is None:
        return "#e6e6e6", "#555"
    stops = [(0.0, (255, 245, 235)), (0.5, (253, 141, 60)), (1.0, (127, 39, 4))]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if rate <= b:
            f = (rate - a) / (b - a)
            rgb = tuple(round(x + (y - x) * f) for x, y in zip(ca, cb))
            break
    lum = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    return "#%02x%02x%02x" % rgb, ("#111" if lum > 140 else "#fff")


def svg_heatmap(result: dict, defense: str, title: str) -> str:
    rows = {(r["lang"], r["encoding"]): r for r in result["tables"]["attack"]["asr"]["by_defense_lang_encoding"]
            if r["defense"] == defense}
    langs = [l for l in LANG_ORDER if any(k[0] == l for k in rows)]
    encs = [e for e in ENCODINGS if any(k[1] == e for k in rows)]
    cw, ch, left, top = 74, 34, 70, 74
    w, h = left + cw * len(encs) + 10, top + ch * len(langs) + 30
    out = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{html.escape(title)}" '
           f'xmlns="http://www.w3.org/2000/svg" font-family="system-ui, sans-serif" font-size="11">']
    for j, e in enumerate(encs):
        x = left + j * cw + cw / 2
        out.append(f'<text x="{x}" y="{top - 8}" text-anchor="start" transform="rotate(-40 {x} {top - 8})" '
                   f'fill="#333">{html.escape(e)}</text>')
    for i, l in enumerate(langs):
        y = top + i * ch
        out.append(f'<text x="{left - 6}" y="{y + ch / 2 + 4}" text-anchor="end" fill="#333">{l}</text>')
        for j, e in enumerate(encs):
            x = left + j * cw
            r = rows.get((l, e))
            fill, fg = _heat(r["rate"] if r else None)
            label = f"{r['k']}/{r['n']}" if r else "N/A"
            tip = (f"{defense} {l} {e}: {fmt(r, cluster=True)}" if r else f"{l} {e}: N/A (encoding does not apply)")
            out.append(f'<g><title>{html.escape(tip)}</title><rect x="{x + 1}" y="{y + 1}" width="{cw - 2}" '
                       f'height="{ch - 2}" rx="3" fill="{fill}"/><text x="{x + cw / 2}" y="{y + ch / 2 + 4}" '
                       f'text-anchor="middle" fill="{fg}">{label}</text></g>')
    out.append(f'<text x="{left}" y="{h - 8}" fill="#555">cell = attacks that succeeded / cases; darker = more '
               f'successful attacks; hover for 95% CIs</text></svg>')
    return "".join(out)


def svg_forest(result: dict, title: str, table=("attack", "asr")) -> str:
    rows = {r["defense"]: r for r in result["tables"][table[0]][table[1]]["by_defense"]}
    ds = [d for d in defenses_in(result) if d in rows]
    left, w, rh, top = 90, 420, 26, 20
    h = top + rh * len(ds) + 30
    out = [f'<svg viewBox="0 0 {left + w + 120} {h}" width="{left + w + 120}" height="{h}" role="img" '
           f'aria-label="{html.escape(title)}" xmlns="http://www.w3.org/2000/svg" font-family="system-ui, sans-serif" font-size="11">']
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        x = left + t * w
        out.append(f'<line x1="{x}" x2="{x}" y1="{top - 6}" y2="{h - 24}" stroke="#ddd"/>'
                   f'<text x="{x}" y="{h - 10}" text-anchor="middle" fill="#555">{int(t * 100)}%</text>')
    for i, d in enumerate(ds):
        r = rows[d]
        y = top + i * rh + rh / 2
        out.append(f'<text x="{left - 8}" y="{y + 4}" text-anchor="end" fill="#222">{d}</text>')
        if r["rate"] is None:
            continue
        x0, x1, xm = left + r["ci_lo"] * w, left + r["ci_hi"] * w, left + r["rate"] * w
        out.append(f'<g><title>{html.escape(d + ": " + fmt(r, cluster=True))}</title>'
                   f'<line x1="{x0}" x2="{x1}" y1="{y}" y2="{y}" stroke="#7f2704" stroke-width="2"/>'
                   f'<line x1="{x0}" x2="{x0}" y1="{y - 5}" y2="{y + 5}" stroke="#7f2704"/>'
                   f'<line x1="{x1}" x2="{x1}" y1="{y - 5}" y2="{y + 5}" stroke="#7f2704"/>'
                   f'<circle cx="{xm}" cy="{y}" r="4" fill="#d94801"/>'
                   f'<text x="{left + w + 8}" y="{y + 4}" fill="#333">{pct(r["rate"])} ({r["k"]}/{r["n"]})</text></g>')
    out.append("</svg>")
    return "".join(out)


def html_table(rows: list[dict], keys: list[str], cluster=True) -> str:
    head = "".join(f"<th>{html.escape(k)}</th>" for k in keys) + "<th>rate [Wilson 95% CI] (k/n)</th>" + \
        ("<th>cluster CI (by text)</th><th>texts</th>" if cluster else "")
    body = []
    for r in rows:
        tds = "".join(f"<td>{html.escape(str(r.get(k)))}</td>" for k in keys)
        tds += f"<td class='num'>{html.escape(fmt(r))}</td>"
        if cluster:
            cl = (f"[{pct(r['cluster_ci_lo'])}, {pct(r['cluster_ci_hi'])}]" if r.get("cluster_ci_lo") is not None else "n/a (&lt;5 texts)")
            tds += f"<td class='num'>{cl}</td><td class='num'>{r.get('n_base')}</td>"
        body.append(f"<tr>{tds}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _p(v) -> str:
    return "undefined (no discordant pair)" if v is None else f"{v:.3g}"


def build_html(data: dict, gng_md: str) -> str:
    test, dev = data["sim"].get("test"), data["sim"].get("dev")
    S = []
    css = """body{font-family:system-ui,-apple-system,'Segoe UI',Tahoma,sans-serif;margin:0;color:#1d1d1f;background:#fafafa}
main{max-width:1100px;margin:auto;padding:24px}h1{margin:0 0 4px}h2{margin-top:36px;border-bottom:1px solid #ddd;padding-bottom:4px}
.banner{background:#7f2704;color:#fff;padding:10px 16px;border-radius:8px;font-weight:600}
.warn{background:#fff4e5;border:1px solid #f0b46b;padding:10px 14px;border-radius:8px}
table{border-collapse:collapse;margin:8px 0;font-size:13px;background:#fff}td,th{border:1px solid #ddd;padding:4px 8px;text-align:left}
th{background:#f2f2f2}.num{font-variant-numeric:tabular-nums;white-space:nowrap}code{background:#eee;padding:1px 4px;border-radius:4px}
.grid{display:flex;flex-wrap:wrap;gap:24px}.grid>div{max-width:100%;overflow-x:auto}.muted{color:#666;font-size:13px}pre{white-space:pre-wrap;background:#fff;border:1px solid #ddd;padding:12px;border-radius:8px}"""
    S.append(f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>Nitaq (نِطاق) - results</title><style>{css}</style></head><body><main>")
    S.append("<h1>Nitaq (نِطاق) — benchmark tables</h1><p class='muted'>Generated by <code>python -m nitaq_bench report</code> "
             "from files in <code>results/</code>. Tables only; no interpretation.</p>")
    if not test:
        S.append("<p class='warn'>No test-split results. Run <code>python -m nitaq_bench eval --split test</code>.</p></main></body></html>")
        return "".join(S)
    m = test["meta"]
    S.append(f"<p class='banner'>Agent: {SIM_LABEL}. These numbers measure defenses against a model that always obeys; "
             "they do not measure how often real models obey.</p>")
    S.append(f"<p class='muted'>test split · commit <code>{m['git']['commit'][:10]}</code> · seed {m['seed']} · "
             f"generated {m['generated_at']} · digest <code>{test['digest'][:16]}</code> · scanner freeze "
             f"{'OK' if m.get('freeze', {}).get('ok') else 'NOT OK'}</p>")
    pfc = m.get("freeze", {}).get("post_freeze_changes", [])
    if pfc:
        S.append("<p class='warn'>Post-freeze changes to frozen files (recorded in CHANGELOG.md): " + html.escape("; ".join(
            f"{c['file']} — {c['reason']} Affects results: {c['affects_results']}." for c in pfc)) + "</p>")
    c = test["tables"]["counts"]
    if c["attack_base_by_author"].get("student", 0) == 0:
        S.append(f"<p class='warn'>All attack texts are AI drafts ({html.escape(str(c['attack_base_by_author']))}). "
                 "They exist to test the pipeline. Replace them with student-written texts before drawing any conclusion.</p>")
    S.append(f"<p>Attack cases: {c['attack_cases']} from {c['attack_base_texts']} authored texts "
             f"(by language: {html.escape(str(c['attack_base_by_lang']))}). Benign cases: {c['benign_cases']} from "
             f"{c['benign_base_texts']} texts. Cases from one authored text are correlated: prefer the cluster CI.</p>")
    skipped = {k: v for k, v in m["defense_status"].items() if not k.startswith("_") and v != "run"}
    if skipped:
        S.append("<p class='warn'>Not run: " + html.escape("; ".join(f"{k}: {v}" for k, v in skipped.items())) + "</p>")

    t = test["tables"]
    S.append("<h2>1. Attack success by defense (test)</h2>" + svg_forest(test, "attack success by defense"))
    S.append(html_table(t["attack"]["asr"]["by_defense"], ["defense"]))
    S.append("<h2>2. Language × encoding (test)</h2><div class='grid'>")
    for d in ("D1", "D2", "D5"):
        if d in defenses_in(test):
            S.append(f"<div><h3>{d}</h3>{svg_heatmap(test, d, f'{d} attack success by language and encoding')}</div>")
    S.append("</div><p class='muted'>Encoding families: " + html.escape(", ".join(f"{e}={f}" for e, f in ENCODING_FAMILY.items())) + "</p>")
    S.append("<h2>3. By language</h2>" + html_table(t["attack"]["asr"]["by_defense_lang"], ["defense", "lang"]))
    S.append("<h2>4. By source (where the injection lives)</h2>" + html_table(t["attack"]["asr"]["by_defense_source"], ["defense", "source"]))
    S.append("<h2>5. By intent — residual risk</h2><p class='muted'>in_scope_tamper stays inside the task's allowed "
             "tools and recipients; a capability guard is not designed to block it.</p>" +
             html_table(t["attack"]["asr"]["by_defense_intent"], ["defense", "intent"]))
    S.append("<h3>User task still completed while under attack</h3>" +
             html_table(t["attack"]["task_completed_under_attack"]["by_defense_intent"], ["defense", "intent"]))
    S.append("<h2>6. Benign content: utility and false positives</h2>" +
             svg_forest(test, "benign utility by defense", ("benign", "utility")))
    S.append(html_table(t["benign"]["utility"]["by_defense_category"], ["defense", "category"]))
    S.append("<h3>Benign content flagged by a scanner</h3>" + html_table(t["benign"]["false_positive_rate"]["by_defense"], ["defense"]))
    S.append("<h2>7. Paired comparison on identical cases (exact McNemar, descriptive)</h2>")
    pr = t["paired"]["attack_success"]
    S.append("<p class='muted'>Text level (each authored text = one pair, majority outcome) is the honest unit; "
             "case-level p-values treat correlated variants as independent and are shown only for completeness.</p>")
    S.append("<table><thead><tr><th>A</th><th>B</th><th>texts</th><th>only A</th><th>only B</th><th>text-level exact p</th>"
             "<th>cases</th><th>only A</th><th>only B</th><th>case-level p (optimistic)</th></tr></thead><tbody>" + "".join(
                 f"<tr><td>{p['a']}</td><td>{p['b']}</td><td>{p['text_pairs']}</td><td>{p['text_only_a']}</td>"
                 f"<td>{p['text_only_b']}</td><td>{_p(p['text_mcnemar_exact_p'])}</td><td>{p['n_pairs']}</td>"
                 f"<td>{p['only_a']}</td><td>{p['only_b']}</td><td>{_p(p['mcnemar_exact_p'])}</td></tr>"
                 for p in pr) + "</tbody></table>")
    S.append("<h2>8. Guard ablation by encoding</h2>" + html_table(
        [r for r in t["attack"]["asr"]["by_defense_encoding"] if r["defense"].startswith("D5")], ["defense", "encoding"]))
    if dev:
        S.append("<h2>9. Dev split (the D2 lexicon was written from these texts)</h2><p class='warn'>Development numbers. "
                 "Not evidence of performance.</p>" + svg_forest(dev, "dev attack success") +
                 (f"<div><h3>D2 (dev)</h3>{svg_heatmap(dev, 'D2', 'D2 on dev')}</div>" if "D2" in defenses_in(dev) else ""))
    S.append("<h2>10. Real-model pilot</h2>")
    if data["pilot"]:
        for r in data["pilot"]:
            a = r["meta"]["agent"]
            S.append(f"<p>Model <code>{html.escape(str(a.get('model')))}</code> version <code>{html.escape(str(a.get('version')))}</code>, "
                     f"{r['meta']['generated_at']}, temperature {a.get('temperature')}, repeats {r['meta']['repeats_requested']}, "
                     f"unstable case×defense pairs: {r['tables']['nondeterminism']['n_unstable']} of {r['tables']['nondeterminism']['n_case_defense']}.</p>"
                     + svg_forest(r, "pilot attack success") + html_table(r["tables"]["attack"]["asr"]["by_defense_lang"], ["defense", "lang"]))
    else:
        st = data.get("pilot_status") or {}
        S.append(f"<p class='warn'>NOT RUN — {html.escape(str(st.get('reason', 'no status file')))} ({html.escape(str(st.get('date', '')))})</p>")
    S.append("<h2>11. Go / no-go (generated)</h2><pre>" + html.escape(gng_md) + "</pre>")
    S.append("</main></body></html>")
    return "".join(S)


# ---------------------------------------------------------------- blocks
def fill_blocks(path: Path, blocks: dict[str, str]) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    new = text
    for name, body in blocks.items():
        new = re.sub(rf"(<!-- BEGIN GENERATED:{name} -->\n).*?(\n<!-- END GENERATED:{name} -->)",
                     lambda m: m.group(1) + body.strip() + m.group(2), new, flags=re.S)
    if new != text:
        path.write_text(new, encoding="utf-8")
    return True


def audit_md(F: Facts) -> str:
    lines = ["<!-- BEGIN GENERATED:numbers -->",
             "| id | value | results file | JSON path |", "|---|---|---|---|"]
    seen = set()
    for f in F.items:
        if f["id"] in seen:
            continue
        seen.add(f["id"])
        lines.append(f"| `{f['id']}` | {f['value']} | `{f['source']}` | `{f['json_path']}` |")
    lines.append("<!-- END GENERATED:numbers -->")
    return "\n".join(lines[1:-1])


# ---------------------------------------------------------------- main
def build_all(root: Path | None = None) -> int:
    root = root or project_root()
    data = load_all(root)
    F = Facts()
    summary = md_summary(F, data)
    pilot = md_pilot(F, data)
    gng = md_go_no_go(F, data)
    allowed, not_allowed = claims(F, data)
    out = root / "report"
    tables = write_tables(data, out / "tables")
    consolidated = {
        "generated_from": data["paths"] | {f"pilot_{i}": r["_path"] for i, r in enumerate(data["pilot"])},
        "sim_test_meta": data["sim"].get("test", {}).get("meta"),
        "sim_test_digest": data["sim"].get("test", {}).get("digest"),
        "sim_test_tables": data["sim"].get("test", {}).get("tables"),
        "sim_dev_digest": data["sim"].get("dev", {}).get("digest"),
        "sim_dev_tables": data["sim"].get("dev", {}).get("tables"),
        "pilot": [{"meta": r["meta"], "digest": r["digest"], "tables": r["tables"]} for r in data["pilot"]],
        "pilot_status": data["pilot_status"],
        "go_no_go": {"sim_test": go_no_go(data["sim"].get("test")),
                     **{r["_path"]: go_no_go(r) for r in data["pilot"]}},
        "facts": F.items,
        "csv_tables": tables,
    }
    write_json(out / "results.json", consolidated)
    (out / "index.html").write_text(build_html(data, gng), encoding="utf-8")
    (root / "CLAIMS_ALLOWED.md").write_text(allowed, encoding="utf-8")
    (root / "CLAIMS_NOT_ALLOWED.md").write_text(not_allowed, encoding="utf-8")
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "PILOT_DECISION.md").write_text(gng, encoding="utf-8")
    fill_blocks(root / "README.md", {"summary": summary, "pilot": pilot})
    fill_blocks(root / "docs" / "CLAIM_AUDIT.md", {"numbers": audit_md(F)})
    print(f"wrote report/index.html, report/results.json, {len(tables)} CSV tables, CLAIMS_*.md, "
          f"docs/PILOT_DECISION.md; {len(F.items)} traced numbers")
    return 0
