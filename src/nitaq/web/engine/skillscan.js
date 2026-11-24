// Port of src/nitaq_bench/skillscan/scanner.py::scan_text. Static text analysis only: nothing in the
// input is executed, rendered, imported or fetched. Offsets, lines and columns are code points,
// exactly as in Python; tests/test_nitaq_engine_parity.py compares the two on a shared corpus.
import DATA from "./data.js";
import {decodeB64Candidates, fold} from "./normalizer.js";
import {screen} from "./scanner.js";
import {b64decodeStrict, cps, isSpace, PY_WS, pyJsonString, pyRegex, pyStrip, sha256Hex, utf8Strict} from "./pyutil.js";

const R = DATA.skillscan;
const SEV_ORDER = Object.fromEntries(R.SEVERITIES.map((s, i) => [s, i]));
const rx = (name, extra = "g") => pyRegex(R.REGEX[name][0], R.REGEX[name][1] + extra);
const SHELL_RES = R.SHELL_PATTERNS.map(([rid, sev, src]) => [rid, sev, pyRegex(src, "Ig")]);
const FRONT_MATTER_RE = pyRegex("\\A\ufeff?---[ \\t]*\\n(.*?)\\n---[ \\t]*(\\n|\\Z)", "Sd");
const FIELD_RE = pyRegex("^([A-Za-z0-9_-]+)\\s*:\\s*(.*)$");
const POWER_RE = pyRegex("\\b(bash|shell|exec|webfetch|http|network)\\b", "I");
const PARA_RE = pyRegex("(?:[^\\n]+\\n?)+", "g");
const TAG_RE = /[\u{E0000}-\u{E007F}]+/gu;
const ZW_RE = pyRegex("(?<=\\w)[\u200b\u200c\u2060\ufeff\u00ad\u180e\u034f]+(?=\\w)", "g");
const WORD_RE = pyRegex("\\w+", "g");
const SCHEME_RE = /^[a-z]+:\/\//i;
const CC_RE = /^\p{Cc}$/u;
const NONPRINT_RE = /^[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}\p{Zl}\p{Zp}\p{Zs}]$/u;

const isPrintable = (ch) => ch === " " || !NONPRINT_RE.test(ch);
const pyTrim = (s) => pyStrip(s, PY_WS);
const notBlank = (s) => cps(s).some((c) => !isSpace(c));
const formatG = (x) => String(Number(x.toPrecision(6)));       // Python f"{x:g}" for this range

/** UTF-16 <-> code-point offsets for one string. */
function indexer(text) {
  const toCp = new Int32Array(text.length + 1), toU16 = [];
  let cp = 0;
  for (let i = 0; i < text.length; i++) {
    toCp[i] = cp;
    toU16.push(i);
    const c = text.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff && i + 1 < text.length) {
      const d = text.charCodeAt(i + 1);
      if (d >= 0xdc00 && d <= 0xdfff) { toCp[i + 1] = cp; i++; }
    }
    cp++;
  }
  toCp[text.length] = cp;
  toU16.push(text.length);
  return {cp: (u) => toCp[u], u16: (c) => toU16[Math.min(c, toU16.length - 1)]};
}

function visible(s, n = 160) {
  let out = "";
  for (const ch of s) {
    const name = R.BIDI[ch] || R.ZERO_WIDTH[ch];
    const cp = ch.codePointAt(0);
    if (name) out += `<${name}>`;
    else if (cp >= 0xe0000 && cp <= 0xe007f) out += "<TAG>";
    else if (CC_RE.test(ch) && ch !== "\n" && ch !== "\t") out += `<U+${cp.toString(16).toUpperCase().padStart(4, "0")}>`;
    else out += ch;
  }
  const a = cps(out.replaceAll("\n", " "));
  return a.length <= n ? a.join("") : a.slice(0, n - 1).join("") + "…";
}

function host(value) {
  if (value.includes("@") && !value.includes("://")) return value.slice(value.lastIndexOf("@") + 1).toLowerCase();
  const h = value.replace(SCHEME_RE, "").split("/")[0].split("?")[0];
  const parts = h.split("@");
  return parts[parts.length - 1].split(":")[0].toLowerCase();
}

const allowed = (h, allow) => allow.some((a) => h === a || h.endsWith("." + a));

function frontMatter(text, ix) {
  const m = FRONT_MATTER_RE.exec(text);
  if (!m) return [{}, 0, 0];
  const fields = new Map();
  let key = null;
  for (const line of m[1].split("\n")) {
    const km = FIELD_RE.exec(line);
    if (km) {
      key = km[1].toLowerCase();
      fields.set(key, pyStrip(pyTrim(km[2]), "\"'"));
    } else if (key && (line.startsWith(" ") || line.startsWith("\t"))) {
      fields.set(key, fields.get(key) + " " + pyTrim(line));
    }
  }
  return [Object.fromEntries(fields), ix.cp(m.indices[1][0]), ix.cp(m.indices[1][1])];
}

/** Python json.loads (C scanner) -> value with objects as ordered [key, value] lists, or undefined. */
function pyJsonParse(text) {
  let i = 0;
  const ws = () => { while (i < text.length && " \t\n\r".includes(text[i])) i++; };
  const fail = () => { throw new SyntaxError("json"); };
  const str = () => {
    i++;
    let out = "";
    for (;;) {
      if (i >= text.length) fail();
      const c = text[i];
      if (c === '"') { i++; return out; }
      if (c === "\\") {
        const e = text[i + 1];
        const simple = {'"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t"};
        if (e in simple) { out += simple[e]; i += 2; continue; }
        if (e === "u") {
          const hex = text.slice(i + 2, i + 6);
          if (!/^[0-9a-fA-F]{4}$/.test(hex)) fail();
          out += String.fromCharCode(parseInt(hex, 16));
          i += 6;
          continue;
        }
        fail();
      }
      if (c.charCodeAt(0) <= 0x1f) fail();
      out += c;
      i++;
    }
  };
  const NUM = /-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?/y;
  const value = () => {
    ws();
    const c = text[i];
    if (c === "{") {
      i++;
      const entries = new Map();
      ws();
      if (text[i] === "}") { i++; return {obj: entries}; }
      for (;;) {
        ws();
        if (text[i] !== '"') fail();
        const k = str();
        ws();
        if (text[i] !== ":") fail();
        i++;
        entries.set(k, value());
        ws();
        if (text[i] === ",") { i++; continue; }
        if (text[i] === "}") { i++; return {obj: entries}; }
        fail();
      }
    }
    if (c === "[") {
      i++;
      const arr = [];
      ws();
      if (text[i] === "]") { i++; return {arr}; }
      for (;;) {
        arr.push(value());
        ws();
        if (text[i] === ",") { i++; continue; }
        if (text[i] === "]") { i++; return {arr}; }
        fail();
      }
    }
    if (c === '"') return {str: str()};
    for (const lit of ["true", "false", "null", "NaN", "Infinity", "-Infinity"]) {
      if (text.startsWith(lit, i)) { i += lit.length; return {other: lit}; }
    }
    NUM.lastIndex = i;
    const m = NUM.exec(text);
    if (m) { i += m[0].length; return {other: m[0]}; }
    return fail();
  };
  try {
    ws();
    const v = value();
    ws();
    return i === text.length ? v : undefined;
  } catch (e) {
    return undefined;
  }
}

function jsonStrings(text) {
  const data = pyJsonParse(text);
  if (data === undefined) return null;
  const out = [];
  const walk = (node, path) => {
    if (node.obj) {
      const nm = node.obj.get("name");
      const label = nm && nm.str !== undefined ? nm.str : null;
      for (const [k, v] of node.obj) walk(v, !label || k === "name" ? `${path}.${k}` : `${path}[${label}].${k}`);
    } else if (node.arr) {
      node.arr.forEach((v, i) => walk(v, `${path}[${i}]`));
    } else if (node.str !== undefined && cps(node.str).length >= 12) {
      out.push([path, node.str]);
    }
  };
  walk(data, "$");
  return out;
}

const MASK_RES = ["HTML_COMMENT", "MD_COMMENT", "HIDDEN_HTML", "DATA_URI", "B64"].map((n) => rx(n)).concat([TAG_RE]);
function maskHidden(text) {
  for (const re of MASK_RES) text = text.replace(re, (m) => m.replace(/[^\n]/gu, " "));
  return text;
}

function tryB64(blob) {
  const raw = b64decodeStrict(blob + "=".repeat((4 - (blob.length % 4)) % 4));
  if (!raw) return null;
  const dec = utf8Strict(raw);
  if (!dec) return null;
  const a = cps(dec);
  return a.filter((c) => isPrintable(c) || isSpace(c)).length / a.length > 0.9 ? dec : null;
}

function hexDecode(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) bytes[i] = parseInt(hex.slice(2 * i, 2 * i + 2), 16);
  return utf8Strict(bytes);
}

/**
 * scanText(text, name, allow) -> the same report as Python's scan_text.
 * Async only because SHA-256 comes from Web Crypto.
 */
export async function scanText(text, name = "<text>", allow = []) {
  const ix = indexer(text);
  const A = cps(text);
  const cpSlice = (a, b) => A.slice(Math.max(0, a), b).join("");
  const starts = [0];
  A.forEach((ch, i) => { if (ch === "\n") starts.push(i + 1); });
  const pos = (off) => {
    let lo = 0, hi = starts.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (starts[mid] <= off) lo = mid; else hi = mid - 1;
    }
    return [lo + 1, off - starts[lo] + 1];
  };
  const findings = [];
  const add = (rule, severity, offset, message, evidence = "", extra = {}) => {
    const [line, col] = pos(offset);
    const f = {rule, severity, line, col, message, evidence: visible(evidence)};
    for (const [k, v] of Object.entries(extra)) if (v !== null && v !== undefined) f[k] = v;
    findings.push(f);
  };
  const injection = (segment, offset, where, escalate = false) => {
    const v = screen(segment);
    if (!v.reasons.length) return;
    const rules = [...new Set(v.reasons.map((r) => r.rule))].sort();
    let sev = rules.map((r) => R.D2_RULE_SEVERITY[r] || "low").reduce((a, b) => (SEV_ORDER[b] > SEV_ORDER[a] ? b : a));
    if (!v.flagged && sev === "high") sev = "medium";
    if (v.flagged && escalate) sev = "high";
    if (!v.flagged && sev === "low") return;
    add(`injection_${where}`, sev, offset, `instruction-like content in ${where} (D2 score ${formatG(v.score)}: ${rules.join(", ")})`,
        segment, {d2_flagged: v.flagged, d2_reasons: v.reasons});
  };
  const cpFind = (sub, fromCp) => {
    const u = text.indexOf(sub, ix.u16(fromCp));
    return u < 0 ? -1 : ix.cp(u);
  };

  // -- front matter --
  const [fm, fmStart, fmEnd] = frontMatter(text, ix);
  const hasFm = Object.keys(fm).length > 0;
  const fmHas = (k) => Object.prototype.hasOwnProperty.call(fm, k);
  if (hasFm) {
    for (const field of ["name", "description"]) {
      if (!fmHas(field)) add("front_matter_missing", "low", fmStart, `front matter has no '${field}' field`);
    }
    if (fmHas("description")) {
      const off = cpFind(cps(fm.description).slice(0, 30).join(""), fmStart);
      injection(fm.description, Math.max(off, fmStart), "description", true);
    }
    const tools = (fmHas("allowed-tools") ? fm["allowed-tools"] : "") + " " + (fmHas("allowed_tools") ? fm.allowed_tools : "");
    if (POWER_RE.test(tools)) add("front_matter_powerful_tools", "info", fmStart, "skill requests powerful tools", pyTrim(tools));
  } else if (lstrip(text).startsWith("#") || name.toLowerCase().endsWith("skill.md")) {
    add("front_matter_missing", "info", 0, "no YAML front matter found");
  }

  // -- structured manifests: every string value on its own --
  const structured = name.toLowerCase().endsWith(".json") ? jsonStrings(text) : null;
  if (structured !== null) {
    for (const [jpath, value] of structured) {
      const off = cpFind(cps(pyJsonString(value).slice(1, -1)).slice(0, 40).join(""), 0);
      const v = screen(value);
      let sev;
      if (v.flagged) sev = "high";
      else if (v.reasons.length && v.reasons.map((r) => R.D2_RULE_SEVERITY[r.rule] || "low")
        .reduce((a, b) => (SEV_ORDER[b] > SEV_ORDER[a] ? b : a)) !== "low") sev = "medium";
      else continue;
      const rules = [...new Set(v.reasons.map((r) => r.rule))].sort();
      add("injection_json_value", sev, Math.max(off, 0), `instruction-like content in ${jpath} (D2 score ${formatG(v.score)}: ${rules.join(", ")})`,
          value, {json_path: jpath, d2_flagged: v.flagged, d2_reasons: v.reasons});
    }
  }

  // -- paragraphs (visible text only) --
  const vis = structured === null ? maskHidden(text) : "";
  const vix = indexer(vis);
  for (const m of vis.matchAll(PARA_RE)) {
    const start = vix.cp(m.index);
    if (hasFm && start < fmEnd) continue;
    if (notBlank(m[0])) injection(m[0], start, "body");
  }

  // -- hidden carriers --
  for (const m of text.matchAll(rx("HTML_COMMENT"))) {
    const body = pyTrim(m[1]);
    if (body) {
      add("hidden_comment", "low", ix.cp(m.index), "HTML comment (invisible when rendered)", body);
      injection(body, ix.cp(m.index), "html_comment", true);
    }
  }
  for (const m of text.matchAll(rx("MD_COMMENT"))) {
    add("hidden_comment", "low", ix.cp(m.index), "Markdown comment (invisible when rendered)", m[1]);
    injection(m[1], ix.cp(m.index), "md_comment", true);
  }
  for (const m of text.matchAll(rx("HIDDEN_HTML"))) {
    add("hidden_html", "medium", ix.cp(m.index), "text hidden with CSS", m[3]);
    injection(m[3], ix.cp(m.index), "hidden_html", true);
  }

  // -- encoded blobs --
  const seen = [];
  for (const m of text.matchAll(rx("DATA_URI", "gd"))) {
    seen.push([ix.cp(m.indices[2][0]), ix.cp(m.indices[2][1])]);
    const mime = m[1], at = ix.cp(m.index), ev = cps(m[0]).slice(0, 60).join("");
    if (mime.startsWith("image/")) {
      add("encoded_blob", "info", at, `data URI (${mime})`, ev);
    } else {
      const dec = tryB64(m[2]);
      add("encoded_blob", "medium", at, `non-image data URI (${mime})`, ev, {decoded: dec ? visible(dec) : null});
      if (dec) injection(dec, at, "decoded_blob", true);
    }
  }
  for (const m of text.matchAll(rx("B64"))) {
    const dec = decodeB64Candidates(m[0]);
    if (!dec.length) continue;
    const s = ix.cp(m.index), e = ix.cp(m.index + m[0].length);
    if (seen.some(([a, b]) => a <= s && s < b)) continue;
    add("encoded_blob", "medium", s, "Base64 blob that decodes to readable text", cpSlice(s, Math.min(e, s + 60)),
        {decoded: visible(dec[0])});
    injection(dec[0], s, "decoded_blob", true);
  }
  for (const m of text.matchAll(rx("HEX_BLOB"))) {
    const dec = hexDecode(m[0]);
    if (dec === null) continue;
    const a = cps(dec);
    if (a.filter((c) => isPrintable(c) || isSpace(c)).length / a.length > 0.95) {
      const at = ix.cp(m.index);
      add("encoded_blob", "medium", at, "hex blob that decodes to readable text", m[0].slice(0, 60), {decoded: visible(dec)});
      injection(dec, at, "decoded_blob", true);
    }
  }

  // -- invisible / confusable characters --
  A.forEach((ch, i) => {
    if (R.BIDI[ch]) add("bidi_control", "high", i, `bidirectional control ${R.BIDI[ch]} (Trojan Source)`, cpSlice(i - 20, i + 20));
  });
  for (const m of text.matchAll(TAG_RE)) {
    let decoded = "";
    for (const c of m[0]) {
      const cp = c.codePointAt(0);
      if (cp >= 0xe0020 && cp <= 0xe007e) decoded += String.fromCodePoint(cp - 0xe0000);
    }
    const at = ix.cp(m.index);
    add("tag_characters", "high", at, "invisible Unicode tag characters (ASCII smuggling)", "", {decoded});
    if (notBlank(decoded)) injection(decoded, at, "tag_characters", true);
  }
  const zw = [...text.matchAll(ZW_RE)];
  if (zw.length) {
    const s = ix.cp(zw[0].index), e = ix.cp(zw[0].index + zw[0][0].length);
    add("zero_width", "medium", s, `${zw.length} zero-width character run(s) inside words`, cpSlice(s - 15, e + 15));
  }
  for (const m of text.matchAll(WORD_RE)) {
    const w = m[0];
    if (/[A-Za-z]/.test(w) && /[\u0400-\u04ff\u0370-\u03ff]/u.test(w)) {
      add("homoglyph_mix", "medium", ix.cp(m.index), "word mixes Latin and Cyrillic/Greek letters", w, {decoded: fold(w)});
    }
  }

  // -- destinations --
  for (const [re, kind] of [[rx("EMAIL"), "e-mail address"], [rx("URL"), "URL"]]) {
    for (const m of text.matchAll(re)) {
      const at = ix.cp(m.index);
      if (kind === "e-mail address" && cpSlice(at - 3, at).endsWith("://")) continue;
      const h = host(m[0]);
      if (!allowed(h, allow)) add("external_address", "low", at, `${kind} outside the allowlist: ${h}`, m[0]);
    }
  }

  // -- shell patterns (report only) --
  for (const [rid, sev, re] of SHELL_RES) {
    re.lastIndex = 0;
    for (const m of text.matchAll(re)) add(rid, sev, ix.cp(m.index), "suspicious shell pattern (reported only, never executed)", m[0]);
  }

  findings.sort((a, b) => (SEV_ORDER[b.severity] - SEV_ORDER[a.severity]) || (a.line - b.line) || (a.col - b.col) ||
                          (a.rule < b.rule ? -1 : a.rule > b.rule ? 1 : 0));
  findings.forEach((f, i) => { f.id = `F${String(i + 1).padStart(3, "0")}`; });
  const summary = {};
  for (const s of [...R.SEVERITIES].reverse()) summary[s] = findings.filter((f) => f.severity === s).length;
  const verdict = summary.high ? "high-risk" : summary.medium ? "review" : "no-major-findings";
  return {file: name, sha256: await sha256Hex(text), verdict, summary, allowlist: [...allow], front_matter: fm, findings,
          note: "Static text analysis only. A clean result is not proof that a skill is safe."};
}

function lstrip(s) {
  const a = cps(s);
  let i = 0;
  while (i < a.length && isSpace(a[i])) i++;
  return a.slice(i).join("");
}
