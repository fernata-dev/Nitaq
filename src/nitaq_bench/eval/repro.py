"""`python -m nitaq_bench verify-repro`: re-run the simulator and compare digests.

The digest covers per-episode rows and every aggregated table (not dates or
commit ids), so two runs of the same code on the same data with the same seed
must produce the same digest.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from nitaq_bench.agents.obedient_mock import ObedientMock
from nitaq_bench.defenses import registry
from nitaq_bench.eval import runner
from nitaq_bench.util import project_root, read_json


def rerun(split: str, seed: int) -> dict:
    stored = read_json(project_root() / "results" / f"sim_{split}.json")
    defenses = [d for d, s in stored["meta"]["defense_status"].items() if not d.startswith("_")]
    f = stored["meta"].get("filters", {})
    cases = runner.build_cases(split, seed, **{k: tuple(v) for k, v in f.items() if v})
    rows, status = runner.run_matrix(cases, defenses or registry.SIM_DEFAULT, ObedientMock())
    return runner.package_results(rows, status, ObedientMock(), split=split, seed=seed, repeats=1)


def verify(splits, seed: int) -> int:
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for split in splits:
            p = project_root() / "results" / f"sim_{split}.json"
            if not p.exists():
                print(f"{split}: no stored results ({p})")
                bad += 1
                continue
            stored = read_json(p)
            if stored["meta"]["seed"] != seed:
                print(f"{split}: stored seed {stored['meta']['seed']} != {seed}")
            new = rerun(split, stored["meta"]["seed"])
            runner.write_results(new, Path(tmp) / f"sim_{split}.json")
            same = new["digest"] == stored["digest"]
            print(f"{split}: stored {stored['digest'][:16]}  re-run {new['digest'][:16]}  "
                  f"{'IDENTICAL' if same else 'DIFFERENT'}")
            bad += 0 if same else 1
    return 1 if bad else 0
