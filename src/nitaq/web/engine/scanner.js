// Port of src/nitaq_bench/defenses/d2_scanner.py (frozen) + the D1 override pattern it reuses.
import DATA from "./data.js";
import {lossy, skeleton, stripInvisible, views, fold} from "./normalizer.js";
import {cpLen, cps, escapeRe, pyRegex, pySplit} from "./pyutil.js";

const L = DATA.lexicon, S = DATA.scanner, D1 = DATA.d1;
const AR = /[ء-ي]/u;
const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);

function arForms(tok) {
  const forms = new Set([tok]);
  for (const f of [...forms]) if (S.PROCLITIC_1.some((p) => f.startsWith(p)) && cpLen(f) >= 3) forms.add(cps(f).slice(1).join(""));
  for (const f of [...forms]) {
    for (const pre of S.PREP) {
      if (f.startsWith(pre + "ال") && cpLen(f) > 5) forms.add(cps(f).slice(3).join(""));
      else if (f.startsWith(pre) && cpLen(f) > 3) forms.add(cps(f).slice(1).join(""));
    }
  }
  for (const f of [...forms]) for (const art of S.ARTICLES) if (f.startsWith(art) && cpLen(f) > 3) forms.add(cps(f).slice(2).join(""));
  return forms;
}

function arWordMatch(tok, pat) {
  const forms = arForms(tok);
  if (pat.endsWith("*")) { const stem = pat.slice(0, -1); return [...forms].some((f) => f.startsWith(stem)); }
  if (forms.has(pat)) return true;
  return [...forms].some((f) => S.SUFFIXES.some((s) => f === pat + s));
}

const DSK_CACHE = new Map();
export function derivedSkeleton(word) {
  if (DSK_CACHE.has(word)) return DSK_CACHE.get(word);
  let w = word.replace(/\*+$/u, "");
  for (const art of S.ARTICLES) if (w.startsWith(art) && cpLen(w) > 3) w = cps(w).slice(2).join("");
  const a = cps(w);
  const out = a.map((ch, i) => {
    if (ch === "و") return i === 0 || (i + 1 < a.length && a[i + 1] === "ا") ? "w" : "";
    if (ch === "ي") return i === 0 ? "y" : "";
    return has(L.AR_TO_SKELETON, ch) ? L.AR_TO_SKELETON[ch] : "";
  });
  const r = out.join("").replace(/(.)\1+/gsu, "$1");
  DSK_CACHE.set(word, r);
  return r;
}

function skVariants(sk) {
  const out = new Set([sk]);
  for (const pre of S.AZ_PROCLITIC_SK) if (sk.startsWith(pre) && sk.length - pre.length >= 3) out.add(sk.slice(pre.length));
  return out;
}

const PATTERNS = [];
for (const [concept, by] of Object.entries(L.CONCEPTS)) {
  for (const [script, entries] of Object.entries(by)) {
    for (const e of entries) {
      const words = pySplit(e).map((w) => (script !== "az" ? fold(w) : w.toLowerCase()));
      const sk = script === "az" ? words.map(skeleton) : script === "ar" ? words.map(derivedSkeleton) : [];
      PATTERNS.push({concept, script, words, sk});
    }
  }
}

function wordMatch(tok, pat, i, isLossy) {
  const w = pat.words[i], t = tok.text;
  if (tok.address) return false;
  if (AR.test(t)) return pat.script === "ar" && arWordMatch(t, w);
  if (pat.script === "en") return w.endsWith("*") ? t.startsWith(w.slice(0, -1)) : t === w;
  if (pat.script === "az" && t === w.replaceAll("'", "")) return true;
  const sk = pat.sk.length ? pat.sk[i] : "";
  if (!sk || cpLen(sk) < 3 || !tok.sk) return false;
  if (pat.script === "ar" && cpLen(sk) < 4 && pat.words.length === 1) return false;
  const variants = skVariants(tok.sk);
  if (variants.has(sk)) return true;
  if (isLossy) { const lsk = lossy(sk); return cpLen(lsk) >= 3 && [...variants].some((v) => lossy(v) === lsk); }
  return false;
}

function blobHit(tok, pat) {
  if (!tok.blob || pat.words.length !== 1) return false;
  const w = pat.words[0].replace(/\*+$/u, "");
  if (pat.script === "en") return cpLen(w) >= 5 && tok.text.includes(w);
  if (pat.script === "ar") return cpLen(w) >= 4 && tok.text.includes(w);
  return false;
}

export function conceptHits(view) {
  const hits = {};
  const toks = view.tokens;
  for (let i = 0; i < toks.length; i++) {
    for (const p of PATTERNS) {
      const n = p.words.length;
      if (i + n > toks.length) continue;
      let all = true;
      for (let j = 0; j < n; j++) if (!wordMatch(toks[i + j], p, j, view.lossy)) { all = false; break; }
      if (all || blobHit(toks[i], p)) (hits[p.concept] ||= []).push(i + n - 1);
    }
  }
  for (const k of Object.keys(hits)) hits[k] = [...new Set(hits[k])].sort((a, b) => a - b);
  return hits;
}

function near(a, b, window, ordered) {
  for (const i of a) for (const j of b) {
    const d = j - i;
    if (ordered ? d > 0 && d <= window : Math.abs(d) > 0 && Math.abs(d) <= window) return [i, j];
  }
  return null;
}

const alt = (xs) => "(?:" + [...xs].sort((a, b) => cpLen(b) - cpLen(a)).map(escapeRe).join("|") + ")";
const OVERRIDE_RE = pyRegex("\\b" + alt(D1.VERBS) + "\\s+(?:" + alt(D1.DETERMINERS) + "\\s+){0,3}(?:" + alt(D1.QUALIFIERS) +
                            "\\s+)?" + alt(D1.OBJECTS) + "\\b");

export function scoreView(view) {
  const h = conceptHits(view), toks = view.tokens;
  const get = (c) => h[c] || [];
  const reasons = [];
  const add = (rule, ...pos) => {
    if (reasons.some((r) => r.rule === rule)) return;
    const ev = [...new Set(pos)].sort((a, b) => a - b).map((p) => toks[p].text).join(" ");
    reasons.push({rule, weight: L.WEIGHTS[rule], view: view.name, evidence: ev});
  };
  let m = near(get("IGNORE"), get("INSTR"), L.WINDOWS.override, true);
  if (m) add("override", ...m);
  const secret = new Set(get("SECRET"));
  for (const i of get("NEG_TELL")) for (const j of get("AUDIENCE")) {
    if (j - i > 0 && j - i <= L.WINDOWS.conceal && ![...secret].some((s) => i < s && s < j)) add("conceal", i, j);
  }
  m = near(get("SEND"), get("SECRET"), L.WINDOWS.secret_send, false) || near(get("ACCESS"), get("SECRET"), L.WINDOWS.secret_access, true);
  if (m) add("secret_flow", ...m);
  m = near(get("CHANGE"), get("ADDRESS_NOUN"), L.WINDOWS.change_address, false) || near(get("SEND"), get("INSTEAD"), L.WINDOWS.instead, true);
  if (m) add("redirect", ...m);
  const addr = toks.map((t, k) => (t.address ? k : -1)).filter((k) => k >= 0);
  m = near(get("SEND"), addr, L.WINDOWS.send_address, true);
  if (m) add("send_to_address", ...m);
  if (get("AI_ADDR").length) add("ai_addressed", get("AI_ADDR")[0]);
  const joined = toks.map((t) => t.text).join(" ");
  const mm = joined.match(OVERRIDE_RE);
  if (mm) reasons.push({rule: "d1_override", weight: L.WEIGHTS.d1_override, view: view.name, evidence: mm[0]});
  const names = new Set(reasons.map((r) => r.rule));
  const total = reasons.filter((r) => !(r.rule === "d1_override" && names.has("override"))).reduce((s, r) => s + r.weight, 0);
  return [total, reasons];
}

const ZW_NO_ZWJ = Array.from(DATA.normalizer.ZERO_WIDTH.replace("‍", "") + DATA.normalizer.BIDI_CONTROLS)
  .map((c) => `\\u{${c.codePointAt(0).toString(16)}}`).join("");
const INVISIBLE_IN_WORD = new RegExp(`[\\p{L}\\p{N}_][${ZW_NO_ZWJ}]+[\\p{L}\\p{N}_]`, "u");
const TAG_RE = /[\u{E0000}-\u{E007F}]+/u;

/** D2Scanner.screen(text) -> {flagged, score, reasons, defense} */
export function screen(text) {
  let best = 0, bestReasons = [], bestView = "base", baseScore = null;
  for (const view of views(text)) {
    const [s, r] = scoreView(view);
    if (view.name === "base") baseScore = s;
    if (s > best) { best = s; bestReasons = r; bestView = view.name; }
  }
  const hidden = [];
  if (best && bestView !== "base" && best > (baseScore || 0)) {
    hidden.push({rule: "hidden_text", weight: L.WEIGHTS.hidden_text, view: bestView, evidence: `evidence only visible after undoing: ${bestView}`});
  } else if (INVISIBLE_IN_WORD.test(text) || TAG_RE.test(text)) {
    hidden.push({rule: "hidden_text", weight: L.WEIGHTS.hidden_text, view: "raw", evidence: "invisible characters inside words"});
  }
  if (best) { best += hidden.reduce((s, h) => s + h.weight, 0); bestReasons = bestReasons.concat(hidden); }
  return {flagged: best >= L.FLAG_THRESHOLD, score: Math.round(best * 1000) / 1000, reasons: bestReasons, defense: "D2"};
}

export {stripInvisible};
