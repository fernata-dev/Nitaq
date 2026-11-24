// Port of src/nitaq_bench/defenses/d2_normalizer.py (frozen). Same views, same tokens.
import DATA from "./data.js";
import {b64decodeStrict, cpLen, cps, isAlnum, isAlpha, isAscii, isSpace, pySplit, pyStrip, strIsSpace,
        translate, utf8Strict} from "./pyutil.js";

const N = DATA.normalizer;
const INVISIBLE_RE = new RegExp("[" + Array.from(N.ZERO_WIDTH + N.BIDI_CONTROLS).map((c) => `\\u{${c.codePointAt(0).toString(16)}}`).join("") + "]", "gu");
const TAG_RE = /[\u{E0000}-\u{E007F}]+/gu;
const DIACRITICS_RE = new RegExp("[" + Array.from(N.DIACRITICS_CLASS).map((c) => c === "-" ? "-" : `\\u{${c.codePointAt(0).toString(16)}}`).join("") + "]", "gu");
const ELONGATION_RE = /([\p{L}\p{Nl}\p{No}])\1{2,}/gu;          // Python r"([^\W\d_])\1{2,}"
const B64_RE = /(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/_-]{16,}={0,2}/g;
const SENT_END = new Set(N.SENT_END);
const DETACHED = new Set(N.DETACHED_ARTICLES);
const AZ_DIGITS = new Set(N.ARABIZI_DIGITS);
const LEET = N.LEET_FOLD;
const B64_OK = new Set(".,;:!?'\"@/-_()[]،؟");

export function stripInvisible(text) {
  let smuggled = "";
  for (const m of text.matchAll(TAG_RE)) {
    for (const ch of m[0]) {
      const cp = ch.codePointAt(0);
      if (cp >= 0xe0020 && cp <= 0xe007e) smuggled += String.fromCodePoint(cp - 0xe0000);
    }
  }
  text = text.replace(TAG_RE, "");
  return [text.replace(INVISIBLE_RE, ""), smuggled];
}

export function fold(text) {
  text = text.normalize("NFKC");
  text = stripInvisible(text)[0];
  text = text.replace(DIACRITICS_RE, "");
  text = translate(translate(text, N.ARABIC_FOLD), N.HOMOGLYPH_FOLD);
  text = text.replaceAll("’", "'").replaceAll("‘", "'").replaceAll("ʼ", "'").toLowerCase();
  return text.replace(ELONGATION_RE, "$1");
}

const collapse = (s) => s.replace(/(.)\1+/gsu, "$1");

export function skeleton(token) {
  let t = token.toLowerCase();
  for (const [a, b] of N.DIGRAPHS) t = t.replaceAll(a, b);
  const out = [];
  cps(t).forEach((ch, i) => {
    if (Object.prototype.hasOwnProperty.call(N.AZ_DIGIT, ch)) out.push(N.AZ_DIGIT[ch]);
    else if ("aeiou".includes(ch)) out.push("");
    else if (ch === "y") out.push(i === 0 ? "y" : "");
    else if (isAscii(ch) && isAlpha(ch)) out.push(ch);
  });
  return collapse(out.join(""));
}

export const lossy = (sk) => collapse(translate(sk, N.LOSSY));

export function deleetToken(tok) {
  const a = cps(tok);
  const has = (c) => Object.prototype.hasOwnProperty.call(LEET, c);
  if (a.some(isAlpha) && a.some(has) && !a.slice(1, -1).includes("@")) return a.map((c) => (has(c) ? LEET[c] : c)).join("");
  if (a.length && a.every((c) => has(c) || isAlpha(c)) && a.filter(has).length >= 2) return a.map((c) => (has(c) ? LEET[c] : c)).join("");
  return tok;
}

export function despace(text) {
  return text.split("\n").map((line) => line.split(/[ \t]{2,}/).map((chunk) => {
    const toks = chunk.split(" ");
    let buf = [];
    const res = [];
    for (const t of [...toks, ""]) {
      if (cpLen(t) === 1 && !strIsSpace(t)) { buf.push(t); continue; }
      if (buf.length >= 3) res.push(buf.join(""));
      else res.push(...buf);
      buf = [];
      if (t) res.push(t);
    }
    return res.join(" ");
  }).join("  ")).join("\n");
}

export function decodeB64Candidates(text) {
  const found = [];
  for (const m of text.matchAll(B64_RE)) {
    let blob = m[0].replaceAll("-", "+").replaceAll("_", "/");
    blob += "=".repeat((4 - (blob.length % 4)) % 4);
    const raw = b64decodeStrict(blob);
    if (!raw) continue;
    const dec = utf8Strict(raw);
    if (dec === null) continue;
    const chars = cps(dec);
    if (chars.length < 8) continue;
    const ok = chars.filter((ch) => isAlnum(ch) || isSpace(ch) || B64_OK.has(ch)).length;
    if (ok / chars.length >= 0.9 && chars.some(isSpace)) found.push(dec);
  }
  return found;
}

const ADDR_RE = /[\p{L}\p{N}_]@[\p{L}\p{N}_]/u;
const isAddress = (tok) => ADDR_RE.test(tok) || tok.startsWith("http://") || tok.startsWith("https://") || tok.startsWith("www.");

export function tokenize(folded, blobMin = 0) {
  const toks = [];
  let sent = 0;
  for (const line of folded.split("\n")) {
    for (const raw of pySplit(line)) {
      const chars = cps(raw);
      const ends = SENT_END.has(chars[chars.length - 1]);
      const core = pyStrip(raw, N.STRIP_CHARS);
      if (core && !DETACHED.has(core)) {
        const addr = isAddress(core);
        const text = core.replaceAll("'", "");
        const latin = cps(core).some((c) => c >= "a" && c <= "z");
        const sk = latin && !addr ? skeleton(core) : "";
        toks.push({text, sent, sk, skLossy: sk ? lossy(sk) : "",
                   azDigit: cps(core).some((c) => AZ_DIGITS.has(c)) && latin, address: addr,
                   blob: Boolean(blobMin) && cpLen(text) >= blobMin});
      }
      if (ends) sent += 1;
    }
    sent += 1;
  }
  return toks;
}

const rot13 = (s) => s.replace(/[a-zA-Z]/g, (c) => {
  const b = c <= "Z" ? 65 : 97;
  return String.fromCharCode(((c.charCodeAt(0) - b + 13) % 26) + b);
});

export function views(text, depth = 0) {
  const nfkc = text.normalize("NFKC");
  const [clean, smuggled] = stripInvisible(nfkc);
  const folded = fold(clean);
  const prefix = depth === 0 ? "" : `b64:${depth}/`;
  const out = [{name: prefix + "base", tokens: tokenize(folded), lossy: false}];
  const joined = despace(folded);
  if (joined !== folded) out.push({name: prefix + "despaced", tokens: tokenize(joined, 15), lossy: false});
  const base = out[0].tokens;
  if (base.some((t) => deleetToken(t.text) !== t.text)) {
    const del = base.map((t) => {
      const d = deleetToken(t.text);
      if (d === t.text) return t;
      const sk = !t.address ? skeleton(d) : "";
      return {text: d, sent: t.sent, sk, skLossy: sk ? lossy(sk) : "", azDigit: true, address: t.address, blob: t.blob};
    });
    out.push({name: prefix + "deleet", tokens: del, lossy: true});
  }
  if (/[a-z]/.test(folded)) out.push({name: prefix + "rot13", tokens: tokenize(rot13(folded)), lossy: false});
  if (cps(smuggled).some((c) => !isSpace(c))) out.push({name: prefix + "tags", tokens: tokenize(fold(smuggled)), lossy: false});
  if (depth < 2) for (const dec of decodeB64Candidates(clean)) out.push(...views(dec, depth + 1));
  return out;
}
