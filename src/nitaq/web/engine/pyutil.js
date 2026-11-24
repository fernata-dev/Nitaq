// Python string semantics in JavaScript, so the browser engine behaves exactly like the
// Python one (code points, Unicode \w/\s/\b, str.split/strip/isalpha/...).
// Parity with Python is checked by tests/test_nitaq_engine_parity.py.

export const PY_WS = "\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f \x85\xa0                　";
const WS_SET = new Set(PY_WS);
export const W_CLASS = "\\p{L}\\p{N}_";          // Python's Unicode \w (letters, numbers, underscore)

export const cps = (s) => Array.from(s);         // code points
export const cpLen = (s) => Array.from(s).length;
export const isSpace = (ch) => WS_SET.has(ch);
export const isAlpha = (ch) => /^\p{L}$/u.test(ch);
export const isAlnum = (ch) => /^[\p{L}\p{N}]$/u.test(ch);
export const isAscii = (ch) => ch.codePointAt(0) < 128;
export const isWord = (ch) => /^[\p{L}\p{N}_]$/u.test(ch);
export const strIsSpace = (s) => s.length > 0 && cps(s).every(isSpace);

/** str.split() with no argument. */
export function pySplit(s) {
  const out = [];
  let cur = "";
  for (const ch of s) {
    if (WS_SET.has(ch)) { if (cur) { out.push(cur); cur = ""; } }
    else cur += ch;
  }
  if (cur) out.push(cur);
  return out;
}

/** str.strip(chars). */
export function pyStrip(s, chars) {
  const set = new Set(chars);
  const a = cps(s);
  let i = 0, j = a.length;
  while (i < j && set.has(a[i])) i++;
  while (j > i && set.has(a[j - 1])) j--;
  return a.slice(i, j).join("");
}

/** str.translate with a {char: replacement|null} table. */
export function translate(s, table) {
  let out = "";
  for (const ch of s) {
    if (Object.prototype.hasOwnProperty.call(table, ch)) { const r = table[ch]; if (r !== null) out += r; }
    else out += ch;
  }
  return out;
}

export const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\\/-]/g, "\\$&");

/**
 * Translate a Python `re` pattern (as used in this project) to a JS RegExp with the `u` flag.
 * \w \W \s \S \d \D \b \B, `.`, `^`, `$`, \A and \Z get Python's meaning (only "\n" ends a line).
 * flags: Python flags as upper-case letters (I, M, S) plus JS flags in lower case (g, d, y).
 */
export function pyRegex(src, flags = "") {
  const W = `[${W_CLASS}]`, NW = `[^${W_CLASS}]`;
  const WSC = escapeClass(PY_WS);
  const M = flags.includes("M"), S = flags.includes("S");
  const SYNTAX = "^$\\.*+?()[]{}|/";
  let out = "", inClass = false;
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (c === "\\" && i + 1 < src.length) {
      const n = src[i + 1];
      i++;
      if (inClass) {
        if (n === "w") out += W_CLASS;
        else if (n === "s") out += WSC;
        else if (n === "d") out += "\\p{Nd}";
        else if (/[A-Za-z0-9]/.test(n) || SYNTAX.includes(n) || n === "-") out += "\\" + n;
        else out += n;                                   // Python identity escape, e.g. \" -> "
        continue;
      }
      if (n === "w") out += W;
      else if (n === "W") out += NW;
      else if (n === "s") out += `[${WSC}]`;
      else if (n === "S") out += `[^${WSC}]`;
      else if (n === "d") out += "\\p{Nd}";
      else if (n === "D") out += "\\P{Nd}";
      else if (n === "b") out += `(?:(?<=${W})(?!${W})|(?<!${W})(?=${W}))`;
      else if (n === "B") out += `(?:(?<=${W})(?=${W})|(?<!${W})(?!${W}))`;
      else if (n === "A") out += "(?<![\\s\\S])";
      else if (n === "Z") out += "(?![\\s\\S])";
      else if (/[A-Za-z0-9]/.test(n) || SYNTAX.includes(n)) out += "\\" + n;
      else out += n;
      continue;
    }
    if (inClass) {
      if (c === "]" && !(out.endsWith("[") || out.endsWith("[^"))) inClass = false;
      out += c;
      continue;
    }
    if (c === "[") { inClass = true; out += c; continue; }
    if (c === ".") { out += S ? "[\\s\\S]" : "[^\\n]"; continue; }
    if (c === "^") { out += M ? "(?:(?<![\\s\\S])|(?<=\\n))" : "(?<![\\s\\S])"; continue; }
    if (c === "$") { out += M ? "(?=\\n|(?![\\s\\S]))" : "(?=\\n?(?![\\s\\S]))"; continue; }
    out += c;
  }
  let js = "u";
  if (flags.includes("I")) js += "i";
  for (const f of "gdy") if (flags.includes(f)) js += f;
  return new RegExp(out, js);
}
function escapeClass(chars) {
  return Array.from(chars).map((c) => {
    const cp = c.codePointAt(0);
    return cp < 0x20 || cp > 0x7e ? `\\u{${cp.toString(16)}}` : "\\" + c;
  }).join("").replace(/\\ /g, " ");
}

/** Offsets: JS regex indices are UTF-16; Python's are code points. */
export function cpIndexer(text) {
  const map = new Int32Array(text.length + 1);
  let cp = 0;
  for (let i = 0; i < text.length; i++) {
    map[i] = cp;
    const code = text.charCodeAt(i);
    if (code >= 0xd800 && code <= 0xdbff && i + 1 < text.length) {
      const next = text.charCodeAt(i + 1);
      if (next >= 0xdc00 && next <= 0xdfff) { map[i + 1] = cp; i++; }
    }
    cp++;
  }
  map[text.length] = cp;
  return (u16) => map[u16];
}

/** Python's json.dumps(value, ensure_ascii=False) for a string. */
export function pyJsonString(s) {
  let out = '"';
  for (const ch of s) {
    const cp = ch.codePointAt(0);
    if (ch === '"') out += '\\"';
    else if (ch === "\\") out += "\\\\";
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch === "\t") out += "\\t";
    else if (ch === "\b") out += "\\b";
    else if (ch === "\f") out += "\\f";
    else if (cp < 0x20) out += "\\u" + cp.toString(16).padStart(4, "0");
    else out += ch;
  }
  return out + '"';
}

/** SHA-256 hex of a string's UTF-8 bytes (Web Crypto; available in browsers and Node). */
export async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** base64.b64decode(blob, validate=True) -> bytes, or null. */
export function b64decodeStrict(blob) {
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(blob) || blob.length % 4 !== 0) return null;
  try {
    const bin = atob(blob);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
  } catch (e) {
    return null;
  }
}

/** bytes.decode("utf-8") (strict, BOM kept) -> string, or null. */
export function utf8Strict(bytes) {
  try {
    return new TextDecoder("utf-8", {fatal: true, ignoreBOM: true}).decode(bytes);
  } catch (e) {
    return null;
  }
}
