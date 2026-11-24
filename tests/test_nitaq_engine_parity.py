"""The browser engine (src/nitaq/web/engine/*.js) must give exactly the Python results.

The phone/web app runs the scanners in JavaScript. These tests regenerate the shared rule data,
build a corpus with Python's answers and run the JS engine on it with Node. Node is optional for a
local run (skipped if missing) and installed in CI, where the test must run.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_engine_data_is_generated_from_python_rules():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "export_engine_data.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def _node() -> str:
    node = shutil.which("node")
    if not node:
        if os.environ.get("CI"):
            pytest.fail("node is required in CI for the browser-engine tests")
        pytest.skip("node not installed")
    return node


def test_js_engine_matches_python(tmp_path):
    node = _node()
    corpus = tmp_path / "corpus.json"
    subprocess.run([sys.executable, str(ROOT / "tools" / "parity" / "make_corpus.py"), str(corpus)],
                   check=True, capture_output=True)
    r = subprocess.run([node, str(ROOT / "tools" / "parity" / "check_parity.mjs"), str(corpus)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    last = r.stdout.strip().splitlines()[-1]
    done, total = last.split()[0].split("/")
    assert done == total and int(total) > 400, last


def test_js_document_readers_find_planted_hidden_text(tmp_path):
    """Word / e-mail / HTML files written by Python's stdlib, with known hidden parts."""
    node = _node()
    subprocess.run([sys.executable, str(ROOT / "tools" / "parity" / "make_doc_fixtures.py"), str(tmp_path)],
                   check=True, capture_output=True)
    r = subprocess.run([node, str(ROOT / "tools" / "parity" / "check_docs.mjs"), str(tmp_path)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    assert "documents OK" in r.stdout
