"""Record the terminal scenes of the demo video: REAL commands in a real pseudo-terminal.

Uses tools/record/recorder.py (asciicast-v2-style events; output bytes and their timing are real,
only the typing of each command line is animated). One cast file per scene.

  python tools/video/record_terminal.py OUTDIR FAKEHOME
      OUTDIR    where the .cast.json files go (e.g. demo/build/casts)
      FAKEHOME  a fake home built by `python -m nitaq.testing.fake_home DIR` (DIR/home)
"""
from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "record"))
import recorder  # noqa: E402

recorder.COLS, recorder.ROWS = 150, 30
OUT, HOME = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
VENV = ROOT / ".venv" / "bin"
ENV = {"HOME": str(HOME), "PATH": f"{VENV}:/usr/local/bin:/usr/bin:/bin", "TERM": "xterm-256color",
       "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "COLUMNS": "150", "NITAQ_ROOT": str(ROOT)}
if os.environ.get("NODE_PATH"):
    ENV["NODE_PATH"] = os.environ["NODE_PATH"]
PROMPT = "\x1b[1;32mnitaq@isef\x1b[0m:\x1b[1;34m~/nitaq\x1b[0m$ "

SCENES = {
    "t1_tests": [("python -m pytest", "all tests")],
    "t2_scan_ok": [("nitaq scan fixtures/benign_skill.md --fail-on high; echo \"exit code: $?\"", "scan a clean skill")],
    "t3_scan_bad": [("nitaq scan fixtures/malicious_skill.md --fail-on high | head -n 15", "scan a poisoned skill"),
                    ("nitaq scan fixtures/malicious_skill.md --fail-on high > /dev/null; echo \"exit code: $?\"", "verdict")],
    "t4_same_attack": [("python tools/video/same_attack.py --pace 1.8", "same attack, five forms")],
    "t5_bench": [("nitaq bench eval --split test --defenses D0,D1,D2,D5 --seed 1337 --out demo/build/bench.json",
                  "worst-case simulation")],
}

stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
only = set(sys.argv[3:])
for name, cmds in SCENES.items():
    if only and name not in only:
        continue
    r = recorder.Rec(ENV, str(ROOT), PROMPT)
    for cmd, title in cmds:
        r.run(cmd, title=title)
        r.marks[-1]["typed_end"] = r.marks[-1]["start"] + len(cmd) + 2   # prompt + typed chars + newline
    r.out(PROMPT, 0.5)
    r.save(str(OUT / f"{name}.cast.json"), {"recorded_at": stamp, "scene": name,
           "note": "Real commands in a real pseudo-terminal; HOME is a fake home; only typing is animated."})
    print(f"{name}: {len(r.events)} events, {r.t:.1f}s")
