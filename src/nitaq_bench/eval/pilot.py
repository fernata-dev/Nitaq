"""Real-LLM pilot: >=3 languages x 3 encodings x 2 sources, N=3 repeats.

If no real model endpoint is usable, nothing is invented: a status file
results/pilot_status.json records "not run" and the reason, and every report
reads that file.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from nitaq_bench.util import now_iso, project_root, write_json


def _public_endpoint(url: str) -> str:
    """Scheme + host only (never paths, keys or query strings) for results files."""
    try:
        p = urlsplit(url)
        return f"{p.scheme}://{p.hostname}" + (f":{p.port}" if p.port else "") if p.hostname else url[:40]
    except ValueError:
        return "(unparseable)"


def run_pilot(args) -> int:
    from nitaq_bench.agents.llm_adapter import LLMAgent, make_client
    from nitaq_bench.eval import runner
    from nitaq_bench.eval.freeze import freeze_status

    langs = tuple(x for x in args.langs.split(",") if x)
    encs = tuple(x for x in args.encodings.split(",") if x)
    sources = tuple(x for x in args.sources.split(",") if x)
    defenses = tuple(x for x in args.defenses.split(",") if x)
    authors = tuple(x for x in (getattr(args, "authors", None) or "").split(",") if x) or None
    plan = {"split": args.split, "langs": langs, "encodings": encs, "sources": sources,
            "defenses": defenses, "repeats": args.repeats, "authors": authors}
    if len(langs) < 3 or len(encs) < 3 or len(sources) < 2:
        print("pilot needs >= 3 languages, >= 3 encodings and >= 2 sources")
        return 2
    status_path = project_root() / "results" / "pilot_status.json"
    client = make_client(args.agent, raw_dir=project_root() / "results" / "raw",
                         max_calls=args.max_calls, model=args.model)
    chk = client.check()
    if not chk.get("ok"):
        status = {"status": "not run", "date": now_iso(), "agent_kind": args.agent,
                  "endpoint": _public_endpoint(client.endpoint()), "reason": chk.get("reason"),
                  "plan": plan}
        write_json(status_path, status)
        print(f"PILOT NOT RUN: {chk.get('reason')}\nrecorded in {status_path}")
        return 0
    frz = freeze_status()
    if args.split == "test" and not frz["ok"]:
        print("REFUSED: scanners differ from the freeze tag; see `python -m nitaq_bench verify-freeze`.")
        return 2
    cases = runner.build_cases(args.split, args.seed, langs=langs, encodings=encs, sources=sources,
                               authors=authors)
    if not cases:
        print("no cases match (with --authors student: add your texts to data/attacks/student_written/ "
              "and data/benign/student_written/, then run `python -m nitaq_bench validate`)")
        return 2
    agent = LLMAgent(client)
    n_ep = len(cases) * len(defenses) * args.repeats
    est = client.estimate(n_ep)
    print(f"model={client.model} ({client.version})  cases={len(cases)}  defenses={len(defenses)}  "
          f"repeats={args.repeats}  episodes={n_ep}\nestimated calls <= {est['max_calls']}, "
          f"~{est['minutes']:.0f} min; hard cap {args.max_calls}")
    if args.dry_run or not args.yes:
        print("dry run (pass --yes to call the model).")
        return 0
    rows, st = runner.run_matrix(cases, defenses, agent, repeats=args.repeats, llm_client=client,
                                 stop=client.exhausted)
    result = runner.package_results(rows, st, agent, split=args.split, seed=args.seed, repeats=args.repeats,
                                    filters={"langs": langs, "encodings": encs, "sources": sources, "authors": authors},
                                    extra_meta={"freeze": frz, "llm_usage": client.usage(), "pilot": True})
    result["meta"]["agent"]["endpoint"] = _public_endpoint(client.endpoint())
    slug = "".join(c if c.isalnum() else "-" for c in str(client.model))
    out = project_root() / "results" / f"llm_pilot_{slug}.json"
    runner.write_results(result, out)
    write_json(status_path, {"status": "run" if "_partial" not in st else "partial", "date": now_iso(),
                             "agent_kind": args.agent, "model": client.model, "version": client.version,
                             "endpoint": _public_endpoint(client.endpoint()), "results_file": out.name,
                             "usage": client.usage(), "plan": plan, "defense_status": st})
    print(f"wrote {out}")
    return 0
