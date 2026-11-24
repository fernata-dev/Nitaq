"""Command line interface: python -m nitaq_bench <command> ..."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nitaq_bench.util import DEFAULT_SEED, project_root


def _csv(value: str | None) -> tuple[str, ...] | None:
    if not value:
        return None
    return tuple(x.strip() for x in value.split(",") if x.strip())


def _fmt_cell(c: dict | None) -> str:
    if not c or c.get("rate") is None:
        return "n/a"
    return f"{c['rate'] * 100:5.1f}% [{c['ci_lo'] * 100:5.1f},{c['ci_hi'] * 100:5.1f}] ({c['k']}/{c['n']})"


# ---------------------------------------------------------------- validate
def cmd_validate(args) -> int:
    from nitaq_bench.attacks.loader import applicability_table, load_base, load_variants
    from nitaq_bench.attacks.schema import validate_dataset
    from nitaq_bench.benign import load_benign

    base = load_base(validate=False)
    errs, warns = validate_dataset(base)
    for w in warns:
        print("warning:", w)
    for e in errs:
        print("ERROR:", e)
    try:
        benign = load_benign()
    except ValueError as exc:
        print("ERROR:", exc)
        return 1
    if errs:
        return 1
    by = {}
    for r in base:
        by.setdefault((r["split"], r["lang"], r["author"]), 0)
        by[(r["split"], r["lang"], r["author"])] += 1
    print("attack base texts (split, lang, author): count")
    for k in sorted(by):
        print("  ", k, by[k])
    print("variants: dev =", len(load_variants("dev")), " test =", len(load_variants("test")))
    print("benign records: dev =", sum(1 for r in benign if r["split"] == "dev"),
          " test =", sum(1 for r in benign if r["split"] == "test"))
    print("encoding applicability by language (N/A cells are never reported as results):")
    for lang, row in applicability_table().items():
        print("  ", lang, ":", ", ".join(e for e, ok in row.items() if ok))
    print("OK")
    return 0


# -------------------------------------------------------------------- eval
def _make_agent(args):
    if args.agent == "obedient_mock":
        from nitaq_bench.agents.obedient_mock import ObedientMock
        return ObedientMock(), None
    from nitaq_bench.agents.llm_adapter import LLMAgent, make_client
    client = make_client(args.agent, raw_dir=project_root() / "results" / "raw",
                         max_calls=args.max_calls, model=getattr(args, "model", None))
    chk = client.check()
    if not chk.get("ok"):
        raise SystemExit(f"LLM endpoint not usable: {chk.get('reason')}")
    return LLMAgent(client), client


def cmd_eval(args) -> int:
    from nitaq_bench.defenses import registry
    from nitaq_bench.eval import runner
    from nitaq_bench.eval.freeze import freeze_status

    frz = freeze_status()
    if args.split == "test" and not frz["ok"] and not args.allow_unfrozen:
        print("REFUSED: the test split may only be run with scanners identical to git tag "
              f"'{frz['tag']}' ({frz.get('reason')}).")
        for f, st in frz["files"].items():
            print("   ", f, "->", st["note"])
        print("If you changed a scanner after the freeze: record it in CHANGELOG.md and pass "
              "--allow-unfrozen (the results file will say so).")
        return 2
    agent, client = _make_agent(args)
    default = registry.SIM_DEFAULT if agent.simulated else registry.LLM_DEFAULT
    defenses = _csv(args.defenses) or default
    filters = {"langs": _csv(args.langs), "encodings": _csv(args.encodings),
               "sources": _csv(args.sources), "intents": _csv(args.intents),
               "tasks": _csv(args.tasks), "authors": _csv(args.authors)}
    cases = runner.build_cases(args.split, args.seed, **filters)
    if args.limit:
        cases = cases[: args.limit]
    repeats = 1 if agent.simulated else args.repeats
    n_ep = len(cases) * len(defenses) * repeats
    print(f"agent={agent.name}  split={args.split}  cases={len(cases)}  defenses={len(defenses)}  "
          f"repeats={repeats}  episodes={n_ep}")
    if agent.simulated:
        print(f"NOTE: {agent.label}")
    else:
        est = client.estimate(n_ep)
        print(f"estimated LLM calls <= {est['max_calls']} (about {est['calls_per_episode']} per episode); "
              f"hard cap --max-calls={args.max_calls}; rough time {est['minutes']:.0f} min at "
              f"{est['sec_per_call']:.0f}s per call. Cost depends on your endpoint's pricing.")
    if args.dry_run:
        print("dry run: nothing executed.")
        return 0
    if not agent.simulated and not args.yes:
        print("Pass --yes to actually call the model.")
        return 0

    def progress(done, total):
        if done % max(1, total // 20) == 0 or done == total:
            print(f"  {done}/{total}", file=sys.stderr)

    stop = (lambda: client.exhausted()) if client else None
    rows, status = runner.run_matrix(cases, defenses, agent, repeats=repeats, llm_client=client,
                                     progress=progress if not args.quiet else None, stop=stop)
    extra = {"freeze": frz}
    if client:
        extra["llm_usage"] = client.usage()
    result = runner.package_results(rows, status, agent, split=args.split, seed=args.seed,
                                    repeats=repeats, filters={k: v for k, v in filters.items() if v},
                                    extra_meta=extra)
    if args.out:
        out = Path(args.out)
    elif agent.simulated:
        out = project_root() / "results" / f"sim_{args.split}.json"
    else:
        slug = "".join(ch if ch.isalnum() else "-" for ch in str(agent.info()["model"]))
        out = project_root() / "results" / f"llm_{slug}_{args.split}.json"
    runner.write_results(result, out)
    print(f"wrote {out}  digest={result['digest'][:16]}")
    for name, st in status.items():
        if st != "run":
            print(f"  {name}: {st}")
    _print_summary(result)
    return 0


def _print_summary(result: dict) -> None:
    t = result["tables"]
    asr = {r["defense"]: r for r in t["attack"]["asr"]["by_defense"]}
    util = {r["defense"]: r for r in t["benign"]["utility"]["by_defense"]}
    fpr = {r["defense"]: r for r in t["benign"]["false_positive_rate"]["by_defense"]}
    print(f"\n{'defense':10} {'attack success (95% Wilson CI)':38} {'benign utility':34} benign flagged")
    for d in asr or util:
        print(f"{d:10} {_fmt_cell(asr.get(d)):38} {_fmt_cell(util.get(d)):34} {_fmt_cell(fpr.get(d))}")
    c = t["counts"]
    print(f"\nattack cases={c['attack_cases']} from {c['attack_base_texts']} authored texts "
          f"(authors: {c['attack_base_by_author']}); benign cases={c['benign_cases']}.")
    print("CAUTION: cases expanded from the same authored text are not independent. Wilson CIs "
          "treat them as if they were; the cluster-bootstrap CI (by authored text) in the results "
          "file does not, and is omitted when there are fewer than 5 authored texts in a cell.")


# ------------------------------------------------------------ small tools
def cmd_scan(args) -> int:
    from nitaq_bench.defenses import registry

    text = Path(args.file).read_text(encoding="utf-8") if args.file else args.text
    if text is None:
        text = sys.stdin.read()
    out = {}
    for name in _csv(args.defenses) or ("D1", "D2"):
        ok, why = registry.availability(name)
        out[name] = registry.build(name).screen(text, args.source).to_dict() if ok else {"skipped": why}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_scan_skill(args) -> int:
    from nitaq_bench.skillscan.scanner import render_text, scan_path

    report = scan_path(Path(args.path), allow=_csv(args.allow) or ())
    if args.sarif:
        from nitaq_bench.skillscan.scanner import to_sarif
        print(json.dumps(to_sarif(report), ensure_ascii=False, indent=2))
    elif args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    order = {"info": 0, "low": 1, "medium": 2, "high": 3}
    if args.fail_on and any(order[f["severity"]] >= order[args.fail_on] for f in report["findings"]):
        return 3
    return 0


def cmd_verify_freeze(args) -> int:
    from nitaq_bench.eval.freeze import freeze_status

    st = freeze_status()
    print(json.dumps(st, indent=2))
    return 0 if st["ok"] else 1


def cmd_restore_tags(args) -> int:
    from nitaq_bench.eval.freeze import restore_tags

    return restore_tags()


def cmd_verify_repro(args) -> int:
    from nitaq_bench.eval.repro import verify

    return verify(_csv(args.splits) or ("dev", "test"), args.seed)


def cmd_report(args) -> int:
    from nitaq_bench.eval.report import build_all

    return build_all()


def cmd_demo(args) -> int:
    from nitaq_bench.demo.server import serve

    return serve(args.host, args.port)


def cmd_pilot(args) -> int:
    from nitaq_bench.eval.pilot import run_pilot

    return run_pilot(args)


def cmd_llm_check(args) -> int:
    from nitaq_bench.agents.llm_adapter import make_client

    client = make_client(args.agent, model=args.model)
    chk = client.check()
    print(json.dumps(chk, ensure_ascii=False, indent=2))
    return 0 if chk.get("ok") else 1


# ------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nitaq-bench", description="Nitaq (نِطاق) benchmark - mock environment, capability guard and skill scanner")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("validate", help="validate data files and show the matrix")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("eval", help="run attacks x defenses x tasks with an agent")
    s.add_argument("--split", choices=("dev", "test"), required=True)
    s.add_argument("--agent", default="obedient_mock", choices=("obedient_mock", "ollama", "openai"))
    s.add_argument("--defenses", help="comma list, e.g. D0,D1,D2,D5,D2+D5")
    s.add_argument("--langs"); s.add_argument("--encodings"); s.add_argument("--sources")
    s.add_argument("--intents"); s.add_argument("--tasks"); s.add_argument("--authors")
    s.add_argument("--seed", type=int, default=DEFAULT_SEED)
    s.add_argument("--repeats", type=int, default=3, help="repeats per case for real models (N=3)")
    s.add_argument("--limit", type=int, default=0, help="only the first N cases (debugging)")
    s.add_argument("--max-calls", type=int, default=2000, help="hard cap on LLM requests")
    s.add_argument("--model", help="model name (else env MODEL; Ollama: first installed model)")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--yes", action="store_true", help="really call the model")
    s.add_argument("--allow-unfrozen", action="store_true")
    s.add_argument("--quiet", action="store_true")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_eval)

    s = sub.add_parser("scan", help="run content scanners on a text")
    s.add_argument("text", nargs="?"); s.add_argument("--file")
    s.add_argument("--defenses"); s.add_argument("--source", default="webpage")
    s.set_defaults(fn=cmd_scan)

    s = sub.add_parser("scan-skill", help="static scan of a SKILL.md-like file (reads text only)")
    s.add_argument("path")
    s.add_argument("--allow", help="comma list of allowed hosts/domains")
    s.add_argument("--json", action="store_true")
    s.add_argument("--sarif", action="store_true", help="SARIF 2.1.0 output for code-scanning tools")
    s.add_argument("--fail-on", choices=("low", "medium", "high"))
    s.set_defaults(fn=cmd_scan_skill)

    s = sub.add_parser("verify-freeze", help="check scanners against git tag freeze-scanner")
    s.set_defaults(fn=cmd_verify_freeze)

    s = sub.add_parser("restore-tags", help="recreate milestone/freeze tags locally from docs/tags.json")
    s.set_defaults(fn=cmd_restore_tags)

    s = sub.add_parser("verify-repro", help="re-run the simulator and compare digests with results/")
    s.add_argument("--splits"); s.add_argument("--seed", type=int, default=DEFAULT_SEED)
    s.set_defaults(fn=cmd_verify_repro)

    s = sub.add_parser("report", help="build report/, claim files and generated doc blocks from results/")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("demo", help="serve the local Arabic demo UI")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8765)
    s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("pilot", help="real-LLM pilot (>=3 langs x 3 encodings x 2 sources, N=3)")
    s.add_argument("--agent", default="ollama", choices=("ollama", "openai"))
    s.add_argument("--split", default="test", choices=("dev", "test"))
    s.add_argument("--langs", default="en,arz,arabizi")
    s.add_argument("--authors", help="e.g. student (only your own texts); default: all authors")
    s.add_argument("--encodings", default="none,b64,zwsp")
    s.add_argument("--sources", default="email,webpage")
    s.add_argument("--defenses", default="D0,D1,D2,D5")
    s.add_argument("--repeats", type=int, default=3)
    s.add_argument("--max-calls", type=int, default=5000)
    s.add_argument("--model")
    s.add_argument("--seed", type=int, default=DEFAULT_SEED)
    s.add_argument("--dry-run", action="store_true"); s.add_argument("--yes", action="store_true")
    s.set_defaults(fn=cmd_pilot)

    s = sub.add_parser("llm-check", help="test the configured LLM endpoint with one request")
    s.add_argument("--agent", default="ollama", choices=("ollama", "openai"))
    s.add_argument("--model")
    s.set_defaults(fn=cmd_llm_check)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    return int(args.fn(args) or 0)
