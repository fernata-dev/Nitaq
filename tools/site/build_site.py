"""Build the Nitaq website from site/template.html and tools/site/content.py.

  python tools/site/build_site.py              regenerate site/index.html, site/en/index.html,
                                              site/assets/demo-data.js and site/assets/img/*
  python tools/site/build_site.py --check      fail if the committed pages are stale
  python tools/site/build_site.py --out DIR    also assemble a deployable folder: the site at DIR/,
                                              the phone/desktop app (src/nitaq/web) at DIR/app/

Every decision shown in the demo is computed here by Nitaq's own policy code
(nitaq.policy.evaluate) and the frozen text scanner (D2); nothing is typed by hand.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import content as C  # noqa: E402
from nitaq.policy import DEFAULT_POLICY, evaluate, hosts_from_content  # noqa: E402
from nitaq_bench.defenses.d2_scanner import D2Scanner  # noqa: E402

SITE = ROOT / "site"
SKILLS = ROOT / "src" / "nitaq" / "agent" / "demo" / "skills"
FILM = ROOT / "demo" / "Nitaq_Full_Demo.mp4"          # the real demo video (no sound), served at assets/film/

# Cloudflare Pages response headers for the assembled folder (the same CSP as the pages, plus caching).
HEADERS = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: no-referrer
  X-Frame-Options: DENY
  Permissions-Policy: camera=(), microphone=(), geolocation=()
/assets/fonts/*
  Cache-Control: public, max-age=31536000, immutable
/assets/film/*
  Cache-Control: public, max-age=86400
"""
DEMO_HOME = Path("/home/demo")          # fixed, so the build is reproducible on any machine


def demo_data() -> dict:
    d2 = D2Scanner()
    out = []
    for sc in C.SCENARIOS:
        pol = dict(DEFAULT_POLICY, **sc["policy"])
        variants = []
        for code, text in sc["variants"]:
            tainted = hosts_from_content(text) if pol["destination_mode"] == "taint" else set()
            tool, args = sc["call"]
            dec = evaluate(tool, args, pol, DEMO_HOME, tainted).to_dict()
            v = d2.screen(text, sc["source"]).to_dict()
            variants.append({"code": code, "text": text, "tainted": sorted(tainted), "decision": dec,
                             "d2": {"flagged": v["flagged"], "score": v["score"],
                                    "rules": sorted({r["rule"] for r in v["reasons"]})}})
        item = {"id": sc["id"], "source": sc["source"], "mode": pol["destination_mode"],
                "call": {"tool": sc["call"][0], "args": sc["call"][1]}, "variants": variants}
        if "also" in sc:
            tool, args = sc["also"]
            item["also"] = {"tool": tool, "args": args, "decision": evaluate(tool, args, pol, DEMO_HOME, set()).to_dict()}
        out.append(item)
    return {"scenarios": out, "policy_default": {k: DEFAULT_POLICY[k] for k in ("allowed_hosts", "secret_paths")}}


def ledger_lines(data: dict) -> list[str]:
    """The hero's decision log: one line per scenario/variant, from the same computed data."""
    lines = []
    for sc in data["scenarios"]:
        for v in sc["variants"][:2]:
            d = v["decision"]
            target = ", ".join(d["hosts"]) or next(iter(sc["call"]["args"].values()))
            mark = "ALLOW" if d["allowed"] else "BLOCK"
            lines.append(f"{mark} {sc['call']['tool']} → {target} · {d['rule'] or 'ok'} [{v['code']}]")
    return lines


def transcript(name: str, reply_lines: int = 2) -> str:
    """A real `nitaq agent` run (docs/media/agent-*.txt), shortened: every step up to the model's reply."""
    lines = [ln.rstrip() for ln in (ROOT / "docs" / "media" / name).read_text(encoding="utf-8").splitlines()]
    out, replied = [], 0
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("│") or s == "---":
            continue
        tool = s[:2] in ("◇ ", "✎ ", "☰ ", "⇄ ") or s.startswith("›_")
        if s.startswith(("🛡 ", "✖ نِطاق", "▲ ")) or "نِطاق وقف" in s:
            cls = "r" if s.startswith(("🛡", "✖")) else "a"
        elif s.startswith("┃"):
            cls, s = "p", s.lstrip("┃ ")
        elif s.startswith(("↓", "الصلاحيات")):
            cls = "a"
        elif s.startswith("•"):
            cls = "m"
        elif s.startswith(("✖ اترفض", "توافق")):
            cls = "q"
        elif tool:
            cls = "t"
        else:
            cls = "y"
            replied += 1
            if replied > reply_lines:
                break
        if len(s) > 150:
            s = s[:149] + "…"
        out.append(f'<span class="{cls}">{_bidi(s)}</span>')
    return "".join(out)


_LATIN_RUN = re.compile(r"[A-Za-z0-9~@$_(\[{\"'<][A-Za-z0-9~@$._:/\\'\"=+\-#%&?*|<>{}\[\](),;! ]*[A-Za-z0-9~@$._:/'\">)\]}]|[A-Za-z0-9]")


def _bidi(s: str) -> str:
    """Escape a transcript line; Latin runs (commands, paths, URLs) inside Arabic get an LTR <bdi> island."""
    if not re.search(r"[\u0600-\u06FF]", s):
        return html.escape(s)
    out, last = [], 0
    for m in _LATIN_RUN.finditer(s):
        out.append(html.escape(s[last:m.start()]))
        out.append(f'<bdi dir="ltr">{html.escape(m.group(0))}</bdi>')
        last = m.end()
    out.append(html.escape(s[last:]))
    return "".join(out)


def _os_blocks(t: dict) -> tuple[str, str]:
    tabs, panels = [], []
    for i, os_id in enumerate(("arch", "debian", "mac", "win")):
        sel = "true" if i == 0 else "false"
        tabs.append(f'<button type="button" role="tab" id="tab-{os_id}" aria-controls="os-{os_id}" aria-selected="{sel}" '
                    f'tabindex="{0 if i == 0 else -1}">{html.escape(t["os_" + os_id])}</button>')
        cmds = C.INSTALL[os_id] + ["nitaq"]
        body = "\n".join(f'<span class="c">$</span> {html.escape(c)}' for c in cmds)
        hidden = "" if i == 0 else " hidden"
        panels.append(f'<div class="os-panel" role="tabpanel" id="os-{os_id}" aria-labelledby="tab-{os_id}"{hidden}>'
                      f'<pre class="term ltr" data-copy="{html.escape(chr(10).join(cmds))}">{body}</pre>'
                      f'<button class="copy on-term" type="button" data-copy-target data-label="{html.escape(t["copy"])}" '
                      f'data-done="{html.escape(t["copied"])}">{html.escape(t["copy"])}</button></div>')
    return "".join(tabs), "\n      ".join(panels)


def render(lang: str, data: dict) -> str:
    t = dict(C.T[lang])
    tpl = (SITE / "template.html").read_text(encoding="utf-8")
    tabs, panels = _os_blocks(t)
    lines = ledger_lines(data)
    shown = [l for l in lines if l.startswith("BLOCK")][:6] + [l for l in lines if l.startswith("ALLOW")][:1]   # allowed calls show too
    ledger = "".join(f'<p class="{"ok" if l.startswith("ALLOW") else "no"}"><b>{l[:5]}</b>{html.escape(l[5:])}</p>' for l in shown)
    values = {
        **{k: html.escape(v) for k, v in t.items()},
        "lang": lang, "dir": "rtl" if lang == "ar" else "ltr", "alt_lang": "en" if lang == "ar" else "ar",
        "root": "" if lang == "ar" else "../", "brand": "نِطاق" if lang == "ar" else "Nitaq",
        "pipx": html.escape(C.PIPX), "pipx_short": html.escape(C.PIPX), "repo": C.REPO,
        "src_owasp": C.SOURCES["owasp"], "src_willison": C.SOURCES["willison"],
        "doc_limits": f"{C.DOC}/docs/LIMITATIONS.md", "doc_install": f"{C.DOC}/docs/INSTALL.md",
        "doc_integrations": f"{C.DOC}/docs/INTEGRATIONS.md", "doc_ai": f"{C.DOC}/docs/AI_PROVENANCE.md",
        "doc_readme": f"{C.DOC}/README.md", "os_tabs": tabs, "os_panels": panels, "ledger_static": ledger,
        "ag_t1": transcript("agent-skill1.txt"), "ag_t2": transcript("agent-skill2.txt"),
    }
    out = re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], tpl)
    assert "{{" not in out, "unresolved placeholder"
    return "<!-- GENERATED by tools/site/build_site.py from site/template.html. Do not edit. -->\n" + out


def demo_module(data: dict) -> str:
    texts = {lang: {k: v for k, v in C.T[lang].items()
                    if k.startswith(("demo_", "dec_", "src_", "scn_", "v_", "rule_", "mode_", "copy", "copied", "seq_", "cx_", "fr_"))}
             for lang in ("ar", "en")}
    samples = {"skill1": (SKILLS / "skill1.md").read_text(encoding="utf-8")}     # the connect panel's "use an example"
    body = json.dumps({"data": data, "text": texts, "samples": samples}, ensure_ascii=True, indent=1, sort_keys=True)
    return ("// GENERATED by tools/site/build_site.py (decisions computed by nitaq.policy). Do not edit.\n"
            f"// A classic script (not a module) so the page also works in sandboxed previews and from file://.\n"
            f"self.NITAQ_DEMO = {body};\n")


def outputs() -> dict[Path, str]:
    data = demo_data()
    return {SITE / "index.html": render("ar", data), SITE / "en" / "index.html": render("en", data),
            SITE / "assets" / "demo-data.js": demo_module(data),
            **{SITE / "assets" / "skills" / f.name: f.read_text(encoding="utf-8")
               for f in sorted(SKILLS.glob("skill*.md"))}}


def images() -> None:
    """Real recordings / app screenshots, resized for the web (proof, not illustration)."""
    from PIL import Image, ImageOps
    dst = SITE / "assets" / "img"
    dst.mkdir(parents=True, exist_ok=True)
    for src, name, width in ((ROOT / "docs/media/08-mcp-proxy-taint.png", "proxy-taint.png", 2056),
                             (ROOT / "docs/media/app/desktop-2-result.png", "desktop-result.png", 1440),
                             (ROOT / "docs/media/app/phone-2-result-ar.png", "phone-result.png", 585),
                             (ROOT / "docs/media/gateway-dashboard.png", "gateway.png", 1280)):
        im = Image.open(src).convert("RGB")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        im.save(dst / name, optimize=True)
        # the page shows an ink-on-paper print of each exhibit; the full-colour original is one tap away
        g = ImageOps.autocontrast(ImageOps.grayscale(im), cutoff=1)
        if sum(g.resize((32, 32)).getdata()) / 1024 < 110:       # dark UI: print it as ink on paper
            g = ImageOps.invert(g)
        ImageOps.colorize(g, black="#1a1814", white="#f4eedb").save(dst / name.replace(".png", "-ink.png"), optimize=True)


def assemble(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SITE, out, ignore=shutil.ignore_patterns("template.html"))
    shutil.copytree(ROOT / "src" / "nitaq" / "web", out / "app")
    (out / "assets" / "film").mkdir(parents=True, exist_ok=True)
    if FILM.is_file():
        shutil.copyfile(FILM, out / "assets" / "film" / "nitaq-demo.mp4")
    (out / "_headers").write_text(HEADERS, encoding="utf-8")
    print(f"assembled {out} (site + app/ + film + _headers)")


def main(argv: list[str]) -> int:
    outs = outputs()
    if "--check" in argv:
        stale = [str(p.relative_to(ROOT)) for p, text in outs.items()
                 if not p.exists() or p.read_text(encoding="utf-8") != text]
        print("site up to date" if not stale else "site STALE: " + ", ".join(stale))
        return 1 if stale else 0
    for p, text in outs.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    if "--no-images" not in argv:
        images()
    print("wrote site/index.html, site/en/index.html, site/assets/demo-data.js, site/assets/skills/")
    if "--out" in argv:
        assemble(Path(argv[argv.index("--out") + 1]).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
