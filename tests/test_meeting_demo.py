"""The meeting demo (tools/demo/meeting_demo.py) must run end to end on a fake home, offline."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_meeting_demo_runs_and_blocks():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "demo" / "meeting_demo.py"), "--no-pause"],
                       capture_output=True, text=True, encoding="utf-8", timeout=180)
    assert r.returncode == 0, r.stderr[-2000:]
    out = r.stdout
    assert out.count("BLOCKED (destination_not_allowed)") == 4          # the guard, all four languages
    assert "tainted_destination" in out and "secret_path" in out and "poisoned_description" in out
    assert "verdict: high-risk" in out and "would change" in out
    assert "Nothing was modified" in out
