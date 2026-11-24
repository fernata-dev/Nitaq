"""`nitaq-bench scan-skill PATH`: static scanner for SKILL.md-like files.

SAFETY: files are opened in binary mode and decoded as text.  Nothing is
executed, imported, rendered or fetched.  URLs are reported, never visited.

Checks
  front_matter      YAML front matter fields; injection in `description` (always loaded) is escalated
  injection_*       the frozen D2 scanner run on each paragraph, HTML comment, hidden HTML and decoded blob
  hidden_comment    HTML / Markdown comments (invisible when rendered) that carry instructions
  hidden_html       display:none / font-size:0 spans
  encoded_blob      Base64 / data-URI / hex blobs: decoded and shown
  bidi_control      Trojan-Source style bidirectional controls
  tag_characters    Unicode tag characters (invisible ASCII smuggling): decoded and shown
  zero_width        zero-width characters inside words
  homoglyph_mix     a word mixing Latin with Cyrillic/Greek look-alikes
  external_address  e-mail / URL hosts not in the allowlist
  shell_*           suspicious shell patterns (report only)
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from nitaq_bench.defenses import d2_normalizer as N
from nitaq_bench.defenses.d2_scanner import D2Scanner
from nitaq_bench.skillscan import rules as R

_D2 = D2Scanner()
_SEV_ORDER = {s: i for i, s in enumerate(R.SEVERITIES)}


class _Doc:
    def __init__(self, text: str) -> None:
        self.text = text
        self.starts = [0]
        for m in re.finditer("\n", text):
            self.starts.append(m.end())

    def pos(self, offset: int) -> tuple[int, int]:
        lo, hi = 0, len(self.starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1, offset - self.starts[lo] + 1


def _visible(s: str, n: int = 160) -> str:
    out = []
    for ch in s:
        name = R.BIDI.get(ch) or R.ZERO_WIDTH.get(ch)
        if name:
            out.append(f"<{name}>")
        elif 0xE0000 <= ord(ch) <= 0xE007F:
            out.append("<TAG>")
        elif unicodedata.category(ch) == "Cc" and ch not in "\n\t":
            out.append(f"<U+{ord(ch):04X}>")
        else:
            out.append(ch)
    s = "".join(out).replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def _host(value: str) -> str:
    if "@" in value and "://" not in value:
        return value.rsplit("@", 1)[1].lower()
    h = re.sub(r"^[a-z]+://", "", value, flags=re.I).split("/")[0].split("?")[0]
    return h.split("@")[-1].split(":")[0].lower()


def _allowed(host: str, allow: tuple[str, ...]) -> bool:
    return any(host == a or host.endswith("." + a) for a in allow)


def _front_matter(text: str) -> tuple[dict[str, str], int, int]:
    m = re.match(r"\A﻿?---[ \t]*\n(.*?)\n---[ \t]*(\n|\Z)", text, re.S)
    if not m:
        return {}, 0, 0
    fields: dict[str, str] = {}
    key = None
    for line in m.group(1).split("\n"):
        km = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$", line)
        if km:
            key = km.group(1).lower()
            fields[key] = km.group(2).strip().strip("\"'")
        elif key and line.startswith((" ", "\t")):
            fields[key] += " " + line.strip()
    return fields, m.start(1), m.end(1)


def scan_text(text: str, name: str = "<text>", allow: tuple[str, ...] = ()) -> dict:
    doc = _Doc(text)
    findings: list[dict] = []

    def add(rule: str, sev: str, offset: int, message: str, evidence: str = "", **extra) -> None:
        line, col = doc.pos(offset)
        f = {"rule": rule, "severity": sev, "line": line, "col": col, "message": message,
             "evidence": _visible(evidence)}
        f.update({k: v for k, v in extra.items() if v is not None})
        findings.append(f)

    def injection(segment: str, offset: int, where: str, escalate: bool = False) -> None:
        v = _D2.screen(segment, "skill_md")
        if not v.reasons:
            return
        rules = sorted({r["rule"] for r in v.reasons})
        sev = max((R.D2_RULE_SEVERITY.get(r, "low") for r in rules), key=_SEV_ORDER.get)
        if not v.flagged and sev == "high":
            sev = "medium"
        if v.flagged and escalate:
            sev = "high"
        if not v.flagged and sev == "low":
            return
        add(f"injection_{where}", sev, offset,
            f"instruction-like content in {where} (D2 score {v.score:g}: {', '.join(rules)})",
            segment, d2_flagged=v.flagged, d2_reasons=v.reasons)

    # -- front matter --------------------------------------------------
    fm, fm_start, fm_end = _front_matter(text)
    if fm:
        for field in ("name", "description"):
            if field not in fm:
                add("front_matter_missing", "low", fm_start, f"front matter has no '{field}' field")
        if "description" in fm:
            off = text.find(fm["description"][:30], fm_start)
            injection(fm["description"], max(off, fm_start), "description", escalate=True)
        tools = fm.get("allowed-tools", "") + " " + fm.get("allowed_tools", "")
        if re.search(r"\b(bash|shell|exec|webfetch|http|network)\b", tools, re.I):
            add("front_matter_powerful_tools", "info", fm_start,
                "skill requests powerful tools", tools.strip())
    elif text.lstrip().startswith("#") or name.lower().endswith("skill.md"):
        add("front_matter_missing", "info", 0, "no YAML front matter found")

    # -- structured manifests (e.g. MCP / tool lists): every string value on its own --
    structured = _json_strings(text) if name.lower().endswith(".json") else None
    if structured is not None:
        for jpath, value in structured:
            off = text.find(json.dumps(value, ensure_ascii=False)[1:-1][:40])
            v = _D2.screen(value, "tool_desc")
            if v.flagged:
                sev = "high"
            elif v.reasons and max((R.D2_RULE_SEVERITY.get(r["rule"], "low") for r in v.reasons),
                                   key=_SEV_ORDER.get) != "low":
                sev = "medium"
            else:
                continue
            add("injection_json_value", sev, max(off, 0),
                f"instruction-like content in {jpath} (D2 score {v.score:g}: "
                f"{', '.join(sorted({r['rule'] for r in v.reasons}))})", value,
                json_path=jpath, d2_flagged=v.flagged, d2_reasons=v.reasons)
    # -- paragraphs (visible text only: hidden carriers are scanned separately below) --
    visible = _mask_hidden(text) if structured is None else ""
    for m in re.finditer(r"(?:[^\n]+\n?)+", visible):
        if fm and m.start() < fm_end:
            continue
        if m.group(0).strip():
            injection(m.group(0), m.start(), "body")

    # -- hidden carriers -------------------------------------------------
    for m in R.HTML_COMMENT_RE.finditer(text):
        body = m.group(1).strip()
        if body:
            add("hidden_comment", "low", m.start(), "HTML comment (invisible when rendered)", body)
            injection(body, m.start(), "html_comment", escalate=True)
    for m in R.MD_COMMENT_RE.finditer(text):
        add("hidden_comment", "low", m.start(), "Markdown comment (invisible when rendered)", m.group(1))
        injection(m.group(1), m.start(), "md_comment", escalate=True)
    for m in R.HIDDEN_HTML_RE.finditer(text):
        add("hidden_html", "medium", m.start(), "text hidden with CSS", m.group(3))
        injection(m.group(3), m.start(), "hidden_html", escalate=True)

    # -- encoded blobs -----------------------------------------------------
    seen_spans: list[tuple[int, int]] = []
    for m in R.DATA_URI_RE.finditer(text):
        seen_spans.append(m.span(2))
        mime = m.group(1)
        if mime.startswith("image/"):
            add("encoded_blob", "info", m.start(), f"data URI ({mime})", m.group(0)[:60])
        else:
            dec = _try_b64(m.group(2))
            add("encoded_blob", "medium", m.start(), f"non-image data URI ({mime})", m.group(0)[:60],
                decoded=_visible(dec) if dec else None)
            if dec:
                injection(dec, m.start(), "decoded_blob", escalate=True)
    for dec, (s, e) in _b64_runs(text):
        if any(a <= s < b for a, b in seen_spans):
            continue
        add("encoded_blob", "medium", s, "Base64 blob that decodes to readable text", text[s:e][:60],
            decoded=_visible(dec))
        injection(dec, s, "decoded_blob", escalate=True)
    for m in R.HEX_BLOB_RE.finditer(text):
        try:
            dec = bytes.fromhex(m.group(0)).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        if sum(c.isprintable() or c.isspace() for c in dec) / len(dec) > 0.95:
            add("encoded_blob", "medium", m.start(), "hex blob that decodes to readable text",
                m.group(0)[:60], decoded=_visible(dec))
            injection(dec, m.start(), "decoded_blob", escalate=True)

    # -- invisible / confusable characters ---------------------------------
    for i, ch in enumerate(text):
        if ch in R.BIDI:
            add("bidi_control", "high", i, f"bidirectional control {R.BIDI[ch]} (Trojan Source)",
                text[max(0, i - 20): i + 20])
    for m in re.finditer(r"[\U000e0000-\U000e007f]+", text):
        decoded = "".join(chr(ord(c) - 0xE0000) for c in m.group(0) if 0xE0020 <= ord(c) <= 0xE007E)
        add("tag_characters", "high", m.start(), "invisible Unicode tag characters (ASCII smuggling)",
            "", decoded=decoded)
        if decoded.strip():
            injection(decoded, m.start(), "tag_characters", escalate=True)
    zw = [m for m in re.finditer(r"(?<=\w)[​‌⁠﻿­᠎͏]+(?=\w)", text)]
    if zw:
        add("zero_width", "medium", zw[0].start(),
            f"{len(zw)} zero-width character run(s) inside words", text[max(0, zw[0].start() - 15): zw[0].end() + 15])
    for m in re.finditer(r"\w+", text):
        w = m.group(0)
        if re.search(r"[A-Za-z]", w) and re.search(r"[Ѐ-ӿͰ-Ͽ]", w):
            add("homoglyph_mix", "medium", m.start(), "word mixes Latin and Cyrillic/Greek letters", w,
                decoded=N.fold(w))

    # -- destinations ------------------------------------------------------
    for rx, kind in ((R.EMAIL_RE, "e-mail address"), (R.URL_RE, "URL")):
        for m in rx.finditer(text):
            v = m.group(0)
            if kind == "e-mail address" and text[max(0, m.start() - 3): m.start()].endswith("://"):
                continue
            h = _host(v)
            if not _allowed(h, allow):
                add("external_address", "low", m.start(), f"{kind} outside the allowlist: {h}", v)

    # -- shell patterns (report only) ---------------------------------------
    for rid, sev, rx in R.SHELL_RES:
        for m in rx.finditer(text):
            add(rid, sev, m.start(), "suspicious shell pattern (reported only, never executed)",
                m.group(0))

    findings.sort(key=lambda f: (-_SEV_ORDER[f["severity"]], f["line"], f["col"], f["rule"]))
    for i, f in enumerate(findings, 1):
        f["id"] = f"F{i:03d}"
    summary = {s: sum(1 for f in findings if f["severity"] == s) for s in reversed(R.SEVERITIES)}
    verdict = "high-risk" if summary["high"] else "review" if summary["medium"] else "no-major-findings"
    return {"file": name, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "verdict": verdict, "summary": summary, "allowlist": list(allow),
            "front_matter": fm, "findings": findings,
            "note": "Static text analysis only. A clean result is not proof that a skill is safe."}


def _json_strings(text: str) -> list[tuple[str, str]] | None:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    out: list[tuple[str, str]] = []

    def walk(node, path):
        if isinstance(node, dict):
            label = node.get("name") if isinstance(node.get("name"), str) else None
            for k, v in node.items():
                walk(v, f"{path}.{k}" if not label or k == "name" else f"{path}[{label}].{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str) and len(node) >= 12:
            out.append((path, node))
    walk(data, "$")
    return out


def _mask_hidden(text: str) -> str:
    """Blank out carriers that are scanned on their own (same length, so offsets stay valid)."""
    blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))
    for rx in (R.HTML_COMMENT_RE, R.MD_COMMENT_RE, R.HIDDEN_HTML_RE, R.DATA_URI_RE, N._B64_RE,
               re.compile(r"[\U000e0000-\U000e007f]+")):
        text = rx.sub(blank, text)
    return text


def _try_b64(blob: str) -> str | None:
    try:
        dec = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    return dec if dec and sum(c.isprintable() or c.isspace() for c in dec) / len(dec) > 0.9 else None


def _b64_runs(text: str):
    for m in N._B64_RE.finditer(text):
        dec = N.decode_b64_candidates(m.group(0))
        if dec:
            yield dec[0], m.span()


def scan_path(path: Path, allow: tuple[str, ...] = ()) -> dict:
    path = Path(path)
    files = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in (".md", ".txt", ".json", ".yaml", ".yml")) \
        if path.is_dir() else [path]
    reports = []
    for f in files:
        raw = f.read_bytes()[: R.MAX_BYTES]          # bytes in, text out: never executed
        text = raw.decode("utf-8", errors="replace")
        reports.append(scan_text(text, str(f), allow))
    if len(reports) == 1:
        return reports[0]
    summary = {s: sum(r["summary"][s] for r in reports) for s in reversed(R.SEVERITIES)}
    findings = [dict(f, file=r["file"]) for r in reports for f in r["findings"]]
    return {"file": str(path), "verdict": "high-risk" if summary["high"] else "review" if summary["medium"]
            else "no-major-findings", "summary": summary, "files": reports, "findings": findings,
            "allowlist": list(allow), "note": reports[0]["note"] if reports else ""}


def render_text(report: dict) -> str:
    icon = {"high": "[HIGH]  ", "medium": "[MEDIUM]", "low": "[LOW]   ", "info": "[INFO]  "}
    lines = [f"Nitaq skill scan: {report['file']}",
             f"verdict: {report['verdict']}   " + "  ".join(f"{k}={v}" for k, v in report["summary"].items()),
             ""]
    for f in report["findings"]:
        loc = f"{f.get('file', '')}:{f['line']}:{f['col']}" if f.get("file") else f"line {f['line']}:{f['col']}"
        lines.append(f"{icon[f['severity']]} {f['id']} {loc}  {f['rule']}: {f['message']}")
        if f.get("evidence"):
            lines.append(f"            evidence: {f['evidence']}")
        if f.get("decoded"):
            lines.append(f"            decoded : {f['decoded']}")
    lines += ["", report["note"]]
    return "\n".join(lines)


def to_sarif(report: dict) -> dict:
    """SARIF 2.1.0 for code-scanning tools."""
    level = {"high": "error", "medium": "warning", "low": "note", "info": "note"}
    rules = sorted({f["rule"] for f in report["findings"]})
    results = []
    for f in report["findings"]:
        results.append({
            "ruleId": f["rule"], "level": level[f["severity"]],
            "message": {"text": f["message"] + (f" | decoded: {f['decoded']}" if f.get("decoded") else "")},
            "properties": {"severity": f["severity"]},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": f.get("file", report["file"])},
                "region": {"startLine": f["line"], "startColumn": f["col"]}}}],
        })
    return {"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "nitaq-skillscan",
                                          "rules": [{"id": r} for r in rules]}},
                      "results": results}]}
