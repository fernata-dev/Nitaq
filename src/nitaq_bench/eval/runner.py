"""Run (cases x defenses x agent) and aggregate neutral tables.

All numbers that appear anywhere in this project are produced here from the
per-episode rows.  Nothing is typed by hand.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable

from nitaq_bench.attacks.loader import load_variants
from nitaq_bench.benign import expand_benign, load_benign
from nitaq_bench.defenses import registry
from nitaq_bench.defenses.base import DefenseStack, ScreenVerdict
from nitaq_bench.env.tasks import SOURCE_TASKS, compatible_tasks
from nitaq_bench.eval.episode import Case, run_episode
from nitaq_bench.eval.metrics import cell, cluster_bootstrap, mcnemar_exact
from nitaq_bench.util import (DEFAULT_SEED, canonical_digest, git_info, now_iso, runtime_info,
                        stable_int, write_csv, write_json)

SCHEMA_VERSION = 1


# --------------------------------------------------------------------------
def build_cases(split: str | None, seed: int = DEFAULT_SEED, *, langs=None, encodings=None,
                sources=None, intents=None, tasks=None, authors=None, kinds=("attack", "benign"),
                root: Path | None = None) -> list[Case]:
    cases: list[Case] = []
    if "attack" in kinds:
        for v in load_variants(split, root=root, seed=seed, authors=authors):
            if langs and v["lang"] not in langs:
                continue
            if encodings and v["encoding"] not in encodings:
                continue
            if sources and v["source"] not in sources:
                continue
            if intents and v["intent"] not in intents:
                continue
            for t in compatible_tasks(v["source"], v["intent"]):
                if tasks and t not in tasks:
                    continue
                cases.append(Case(f"{v['id']}__{t}", "attack", v, t))
    if "benign" in kinds:
        for rec in load_benign(split, root=root, authors=authors):
            if langs and rec["lang"] not in langs:
                continue
            for v in expand_benign(rec):
                if sources and v["source"] not in sources:
                    continue
                for t in SOURCE_TASKS[v["source"]]:
                    if v["category"] == "delegation" and t != "reply_email":
                        continue
                    if tasks and t not in tasks:
                        continue
                    cases.append(Case(f"{v['id']}__{t}", "benign", v, t))
    cases.sort(key=lambda c: c.case_id)
    return cases


class _CachedStack(DefenseStack):
    """Memoise content screening: the same text is screened many times in a matrix."""

    def __init__(self, inner: DefenseStack) -> None:
        super().__init__(inner.defenses, inner.name)
        self._cache: dict[tuple[str, str], ScreenVerdict] = {}

    def screen(self, text: str, source: str) -> ScreenVerdict:
        key = (source, text)
        if key not in self._cache:
            self._cache[key] = super().screen(text, source)
        return self._cache[key]


def run_matrix(cases: list[Case], defense_names: Iterable[str], agent, repeats: int = 1,
               max_steps: int = 8, llm_client=None,
               progress: Callable[[int, int], None] | None = None,
               stop: Callable[[], bool] | None = None) -> tuple[list[dict], dict]:
    """Returns (rows, status) where status maps defense -> "run" | "skipped: why"."""
    rows: list[dict] = []
    status: dict[str, str] = {}
    stacks: dict[str, DefenseStack] = {}
    for name in defense_names:
        ok, why = registry.availability(name, llm_client)
        if not ok:
            status[name] = f"skipped: {why}"
            continue
        stacks[name] = _CachedStack(registry.build(name, llm_client))
        status[name] = "run"
    if agent.simulated:
        repeats = 1  # deterministic: repeating would only fake a larger n
    total = len(cases) * len(stacks) * repeats
    done = 0
    for case in cases:
        v = case.variant
        for dname, stack in stacks.items():
            for rep in range(repeats):
                if stop and stop():
                    status["_partial"] = f"stopped early after {done} of {total} episodes"
                    return rows, status
                if hasattr(agent, "set_repeat"):
                    agent.set_repeat(rep)
                try:
                    _, res = run_episode(case, stack, agent, max_steps=max_steps)
                except Exception as exc:  # real-model failures: the episode is dropped, never scored
                    if agent.simulated:
                        raise
                    status["_llm_errors"] = status.get("_llm_errors", 0) + 1
                    if stop and stop():
                        status["_partial"] = f"stopped early after {done} of {total} episodes ({exc})"
                        return rows, status
                    continue
                row = {
                    "case_id": case.case_id, "kind": case.kind, "base_id": v["base_id"],
                    "lang": v["lang"], "encoding": v.get("encoding", "none"),
                    "source": v["source"], "task": case.task_name,
                    "intent": v.get("intent"), "category": v.get("category"),
                    "base_author": v.get("base_author", v.get("author")),
                    "defense": dname, "repeat": rep,
                }
                row.update(res)
                rows.append(row)
                done += 1
                if progress:
                    progress(done, total)
    return rows, status


# --------------------------------------------------------------------------
def collapse_repeats(rows: list[dict]) -> list[dict]:
    """One row per (case, defense).  A binary outcome is the majority over repeats."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["case_id"], r["defense"])].append(r)
    out = []
    for (_, _), g in groups.items():
        base = dict(g[0])
        n = len(g)
        base["n_repeats"] = n
        for key in ("success", "attempted", "flagged", "utility", "task_completed", "secret_leaked"):
            if key in base:
                votes = sum(1 for r in g if r.get(key))
                base[f"{key}_repeats"] = votes
                base[key] = votes * 2 > n
        base["n_blocked"] = max(r["n_blocked"] for r in g)
        base["unstable"] = any(
            len({bool(r.get(key)) for r in g}) > 1 for key in ("success", "utility") if key in base
        )
        base.pop("repeat", None)
        out.append(base)
    return out


def _group(rows: list[dict], keys: tuple[str, ...], outcome: str) -> list[dict]:
    acc: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        acc[tuple(r.get(k) for k in keys)].append(r)
    table = []
    for key in sorted(acc, key=lambda t: tuple("" if x is None else str(x) for x in t)):
        g = acc[key]
        row = dict(zip(keys, key))
        row.update(cell(sum(1 for r in g if r.get(outcome)), len(g)))
        per_base: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in g:
            per_base[r["base_id"]][0] += 1 if r.get(outcome) else 0
            per_base[r["base_id"]][1] += 1
        row["n_base"] = len(per_base)
        lo, hi = cluster_bootstrap([tuple(v) for _, v in sorted(per_base.items())],
                                   seed=stable_int(DEFAULT_SEED, outcome, *key))
        row["cluster_ci_lo"], row["cluster_ci_hi"] = lo, hi
        table.append(row)
    return table


ATTACK_BREAKDOWNS = {
    "by_defense": ("defense",),
    "by_defense_lang": ("defense", "lang"),
    "by_defense_encoding": ("defense", "encoding"),
    "by_defense_lang_encoding": ("defense", "lang", "encoding"),
    "by_defense_source": ("defense", "source"),
    "by_defense_intent": ("defense", "intent"),
    "by_defense_task": ("defense", "task"),
    "by_defense_author": ("defense", "base_author"),
}
BENIGN_BREAKDOWNS = {
    "by_defense": ("defense",),
    "by_defense_category": ("defense", "category"),
    "by_defense_lang": ("defense", "lang"),
    "by_defense_source": ("defense", "source"),
}


def paired_table(rows: list[dict], outcome: str, defenses: list[str]) -> list[dict]:
    """Exact McNemar on identical cases for every ordered pair (A before B).

    Case level: every generated case is one pair (cases from one authored text
    are correlated, so this p-value is optimistic).  Text level: each authored
    text is one pair, its outcome = majority over its cases.  Prefer text level.
    """
    by_def: dict[str, dict[str, bool]] = defaultdict(dict)
    base_of: dict[str, str] = {}
    for r in rows:
        by_def[r["defense"]][r["case_id"]] = bool(r.get(outcome))
        base_of[r["case_id"]] = r["base_id"]

    def text_level(d: str, common: list[str]) -> dict[str, bool]:
        acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for c in common:
            acc[base_of[c]][0] += by_def[d][c]
            acc[base_of[c]][1] += 1
        return {b: k * 2 > n for b, (k, n) in acc.items()}
    out = []
    for i, a in enumerate(defenses):
        for b in defenses[i + 1:]:
            common = sorted(set(by_def[a]) & set(by_def[b]))
            if not common:
                continue
            only_a = sum(1 for c in common if by_def[a][c] and not by_def[b][c])
            only_b = sum(1 for c in common if by_def[b][c] and not by_def[a][c])
            out.append({
                "a": a, "b": b, "outcome": outcome, "n_pairs": len(common),
                "both": sum(1 for c in common if by_def[a][c] and by_def[b][c]),
                "only_a": only_a, "only_b": only_b,
                "neither": sum(1 for c in common if not by_def[a][c] and not by_def[b][c]),
                "mcnemar_exact_p": mcnemar_exact(only_a, only_b),
            })
            ta, tb = text_level(a, common), text_level(b, common)
            t_only_a = sum(1 for x in ta if ta[x] and not tb[x])
            t_only_b = sum(1 for x in ta if tb[x] and not ta[x])
            out[-1].update({"text_pairs": len(ta), "text_only_a": t_only_a, "text_only_b": t_only_b,
                            "text_mcnemar_exact_p": mcnemar_exact(t_only_a, t_only_b)})
    return out


def summarize(rows: list[dict]) -> dict:
    col = collapse_repeats(rows)
    attacks = [r for r in col if r["kind"] == "attack"]
    benign = [r for r in col if r["kind"] == "benign"]
    defenses = list(dict.fromkeys(r["defense"] for r in col))
    tables: dict = {"attack": {}, "benign": {}}
    for outcome, label in (("success", "asr"), ("attempted", "attempt_rate"),
                           ("flagged", "detection_rate"), ("task_completed", "task_completed_under_attack"),
                           ("secret_leaked", "secret_leak_rate")):
        tables["attack"][label] = {name: _group(attacks, keys, outcome)
                                   for name, keys in ATTACK_BREAKDOWNS.items()}
    for outcome, label in (("utility", "utility"), ("flagged", "false_positive_rate")):
        tables["benign"][label] = {name: _group(benign, keys, outcome)
                                   for name, keys in BENIGN_BREAKDOWNS.items()}
    blocked_rows = [dict(r, any_blocked=r["n_blocked"] > 0) for r in benign]
    tables["benign"]["guard_block_rate"] = {name: _group(blocked_rows, keys, "any_blocked")
                                            for name, keys in BENIGN_BREAKDOWNS.items()}
    tables["paired"] = {
        "attack_success": paired_table(attacks, "success", defenses),
        "benign_utility": paired_table(benign, "utility", defenses),
    }
    n_unstable = sum(1 for r in col if r.get("unstable"))
    tables["nondeterminism"] = {
        "n_case_defense": len(col), "n_unstable": n_unstable,
        "max_repeats": max((r["n_repeats"] for r in col), default=0),
    }
    tables["counts"] = {
        "attack_cases": len({r["case_id"] for r in attacks}),
        "attack_base_texts": len({r["base_id"] for r in attacks}),
        "benign_cases": len({r["case_id"] for r in benign}),
        "benign_base_texts": len({r["base_id"] for r in benign}),
        "attack_base_by_author": _count_by(attacks, "base_author"),
        "attack_base_by_lang": _count_by(attacks, "lang"),
        "benign_base_by_author": _count_by(benign, "base_author"),
    }
    return tables


def _count_by(rows: list[dict], key: str) -> dict:
    acc: dict[str, set] = defaultdict(set)
    for r in rows:
        acc[str(r.get(key))].add(r["base_id"])
    return {k: len(v) for k, v in sorted(acc.items())}


# --------------------------------------------------------------------------
def package_results(rows: list[dict], status: dict, agent, *, split: str, seed: int, repeats: int,
                    filters: dict | None = None, extra_meta: dict | None = None) -> dict:
    tables = summarize(rows)
    meta = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "git": git_info(),
        "runtime": runtime_info(),
        "seed": seed,
        "split": split,
        "repeats_requested": repeats,
        "agent": agent.info(),
        "defense_status": status,
        "filters": filters or {},
    }
    if extra_meta:
        meta.update(extra_meta)
    return {
        "meta": meta,
        # the digest covers only what must be identical between two runs of the same code
        "digest": canonical_digest({"rows": rows, "tables": tables}),
        "tables": tables,
        "rows": rows,
    }


ROW_COLUMNS = ["case_id", "kind", "base_id", "lang", "encoding", "source", "task", "intent",
               "category", "base_author", "defense", "repeat", "success", "attempted", "flagged",
               "utility", "task_completed", "secret_leaked", "n_calls", "n_blocked",
               "blocked_rules", "error"]


def write_results(result: dict, out_json: Path) -> None:
    write_json(out_json, result)
    write_csv(out_json.with_name(out_json.stem + "_rows.csv"), ROW_COLUMNS,
              ([";".join(r[c]) if isinstance(r.get(c), list) else r.get(c) for c in ROW_COLUMNS]
               for r in result["rows"]))
