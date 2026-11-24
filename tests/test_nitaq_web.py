"""Static checks on the web app (src/nitaq/web): what ships, what it may do, how it is cached.

The app runs on phones and in `nitaq ui`. It must never build HTML from data, never call
another host, keep a strict CSP, list every shipped file for offline use, and carry one version.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nitaq import __version__

WEB = Path(__file__).resolve().parents[1] / "src" / "nitaq" / "web"
JS = sorted(WEB.rglob("*.js"))


def test_no_html_injection_sinks_or_eval_in_any_script():
    for f in JS:
        src = f.read_text(encoding="utf-8")
        for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function",
                    "setAttribute(\"style\"", "javascript:"):
            assert bad not in src, f"{f.name}: {bad}"


def test_scripts_never_contact_another_host():
    for f in JS:
        src = f.read_text(encoding="utf-8")
        assert not re.search(r"fetch\(\s*[\"'`]https?:", src), f.name
        assert "XMLHttpRequest" not in src and "WebSocket" not in src and "sendBeacon" not in src, f.name
        assert "importScripts" not in src, f.name


def test_index_has_strict_csp_and_no_inline_code():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html).group(1)
    assert "default-src 'none'" in csp and "script-src 'self'" in csp and "connect-src 'self'" in csp
    assert "unsafe" not in csp
    assert "<script>" not in html and " style=" not in html and " on" + "click=" not in html
    assert not re.search(r'(src|href)="https?:', html)


def test_service_worker_lists_every_shipped_file_and_one_version():
    sw = (WEB / "sw.js").read_text(encoding="utf-8")
    listed = set(re.findall(r'"([^"]+)"', sw.split("const FILES = [")[1].split("];")[0]))
    shipped = {p.relative_to(WEB).as_posix() for p in WEB.rglob("*") if p.is_file()} - {"sw.js", "fonts/OFL.txt"}
    assert shipped <= listed, f"not cached for offline use: {sorted(shipped - listed)}"
    assert listed - {"./"} <= shipped, f"listed but missing: {sorted(listed - {'./'} - shipped)}"
    assert f'const CACHE = "nitaq-{__version__}"' in sw
    assert f'export const VERSION = "{__version__}"' in (WEB / "app" / "about.js").read_text(encoding="utf-8")


def test_manifest_icons_and_font_license_exist():
    man = json.loads((WEB / "manifest.webmanifest").read_text(encoding="utf-8"))
    for icon in man["icons"]:
        assert (WEB / icon["src"]).is_file(), icon["src"]
    assert "share_target" not in man          # a GET share target would put shared text into URLs
    assert "SIL Open Font License" in (WEB / "fonts" / "OFL.txt").read_text(encoding="utf-8")


def test_every_module_parses_as_an_es_module(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    for f in JS:
        copy = tmp_path / (f.stem + ".mjs")
        copy.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        r = subprocess.run([node, "--check", str(copy)], capture_output=True, text=True)
        assert r.returncode == 0, f"{f.relative_to(WEB)}: {r.stderr[-800:]}"


def test_every_string_key_exists_in_both_languages():
    src = (WEB / "app" / "i18n.js").read_text(encoding="utf-8")
    ar = src.split("  ar: {")[1].split("\n  },\n  en: {")[0]
    en = src.split("\n  en: {")[1].split("\n  },\n};")[0]
    key = re.compile(r'(?m)(?:^\s+|, )([a-z][a-z0-9_]*): ["\[]')
    ka, ke = set(key.findall(ar)), set(key.findall(en))
    assert ka == ke, f"only ar: {sorted(ka - ke)}; only en: {sorted(ke - ka)}"
    used = set()
    for f in (WEB / "app").glob("*.js"):
        used |= set(re.findall(r'\bt\("([a-z][a-z0-9_]*)"\)', f.read_text(encoding="utf-8")))
    assert used <= ke, f"used but not defined: {sorted(used - ke)}"


def test_example_documents_are_bundled_as_one_module():
    src = (WEB / "samples" / "samples.js").read_text(encoding="utf-8")
    for name in ("hidden.docx", "mail.eml", "page.html", "smuggle.txt", "skill1.md", "skill2.md"):
        assert f'"{name}":' in src
    assert sorted(p.name for p in (WEB / "samples").iterdir()) == ["samples.js"]


def test_page_loads_classic_bundles_not_modules():
    """Module scripts are refused in sandboxed previews (opaque origin) and on file:// pages, where
    a module-only page is blank. The page loads generated classic bundles; they must be fresh."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert '<script src="bundle.js" defer></script>' in html and 'type="module"' not in html
    root = WEB.parents[2]
    r = subprocess.run([sys.executable, str(root / "tools" / "web" / "bundle.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    for f in ("bundle.js", "engine/worker-bundle.js"):
        src = (WEB / f).read_text(encoding="utf-8")
        assert "import.meta" not in src and not re.search(r"^\s*(import|export)\b", src, re.M), f


def test_worker_bundle_gives_the_same_reports_as_the_modules(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    root = WEB.parents[2]
    subprocess.run([sys.executable, str(root / "tools" / "parity" / "make_doc_fixtures.py"), str(tmp_path)], check=True, capture_output=True)
    r = subprocess.run([node, str(root / "tools" / "web" / "check_bundle.mjs"), str(tmp_path)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
