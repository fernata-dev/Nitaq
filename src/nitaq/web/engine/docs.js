// Document readers for the app: they turn a .docx, an e-mail (.eml / raw source) or an HTML page
// into text SEGMENTS and record which ones a person would not see when the document is shown
// normally (white text, Word's hidden-text format, CSS-hidden elements, comments, metadata...).
// Cloud assistants (e.g. an assistant summarising a file in a drive or an inbox) read those parts too.
//
// SAFETY: input is parsed as data. Nothing is executed, rendered, fetched or opened. Archives are
// read with size limits (zip-bomb guard). No dependency, no network.
//
// Segment: {text, where, hidden: [reason, ...], seen: "hidden" | "unseen" | "visible"}
//   hidden  -> a reader of the rendered document cannot see it (white, vanish, display:none, ...)
//   unseen  -> shown only in side panels / properties (comments, metadata, alt text, field codes)

export const LIMITS = {maxInput: 25 * 1024 * 1024, maxUnzipped: 60 * 1024 * 1024, maxEntries: 4000, maxRatio: 200,
                       maxDepth: 4, maxSegments: 20000};

const HIDDEN_KINDS = new Set(["vanish", "white", "tiny", "css_display", "css_visibility", "css_opacity", "css_fontsize",
  "css_offscreen", "css_clip", "css_size0", "css_white", "attr_hidden", "html_comment", "template", "noscript", "script",
  "style_block"]);
const seenOf = (hidden) => (!hidden.length ? "visible" : hidden.some((h) => HIDDEN_KINDS.has(h)) ? "hidden" : "unseen");
const seg = (text, where, hidden = []) => ({text, where, hidden: [...new Set(hidden)], seen: seenOf(hidden)});

// ---------------------------------------------------------------- shared helpers
const NAMED = {amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", shy: "­", zwj: "‍", zwnj: "‌",
  lrm: "‎", rlm: "‏", ndash: "–", mdash: "—", hellip: "…", laquo: "«", raquo: "»", lsquo: "‘", rsquo: "’",
  ldquo: "“", rdquo: "”", copy: "©", reg: "®", trade: "™", bull: "•", middot: "·", times: "×", divide: "÷", euro: "€",
  pound: "£", yen: "¥", cent: "¢", sect: "§", para: "¶", deg: "°", plusmn: "±", frac12: "½", thinsp: " ",
  ensp: " ", emsp: " ", Tab: "\t", NewLine: "\n"};
export function decodeEntities(s) {
  return s.replace(/&(#[xX][0-9a-fA-F]{1,6}|#[0-9]{1,7}|[A-Za-z][A-Za-z0-9]{1,31});?/g, (m, e) => {
    if (e[0] === "#") {
      const cp = e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      if (cp === 0 || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff)) return "�";
      return String.fromCodePoint(cp);
    }
    return Object.prototype.hasOwnProperty.call(NAMED, e) ? NAMED[e] : m;
  });
}

const TAG_TOKEN = /<!--([\s\S]*?)(?:-->|$)|<!\[CDATA\[([\s\S]*?)\]\]>|<[?!][^>]*>|<(\/?)([A-Za-z][\w:.-]*)((?:[^>"']|"[^"]*"|'[^']*')*?)(\/?)>|([^<]+|<)/g;
const ATTR = /([^\s=\/>"']+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>"']+)))?/g;

function attrs(src) {
  const out = {};
  for (const m of src.matchAll(ATTR)) {
    const k = m[1].toLowerCase();
    if (!(k in out)) out[k] = decodeEntities(m[2] ?? m[3] ?? m[4] ?? "");
  }
  return out;
}

/** Tokens: {t: "open"|"close"|"text"|"comment", name, attrs, self} */
function* tokens(src) {
  for (const m of src.matchAll(TAG_TOKEN)) {
    if (m[1] !== undefined) yield {t: "comment", text: m[1]};
    else if (m[2] !== undefined) yield {t: "text", text: m[2], raw: true};
    else if (m[4] !== undefined) {
      if (m[3]) yield {t: "close", name: m[4].toLowerCase()};
      else yield {t: "open", name: m[4].toLowerCase(), attrs: attrs(m[5] || ""), self: Boolean(m[6])};
    } else if (m[7] !== undefined) yield {t: "text", text: m[7]};
  }
}

const collapseWs = (s) => s.replace(/[ \t\r\n\f]+/g, " ");

// ---------------------------------------------------------------- HTML
const VOID = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"]);
const BLOCK = new Set(["p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "table", "h1", "h2", "h3", "h4", "h5", "h6",
  "section", "article", "header", "footer", "blockquote", "pre", "hr", "dt", "dd", "form", "main", "aside", "nav", "figure"]);
const RAWTEXT = new Set(["script", "style", "textarea", "title", "xmp", "noscript", "template"]);

const WHITE = new Set(["#fff", "#ffffff", "white", "#fefefe", "#fdfdfd", "rgb(255,255,255)", "rgba(255,255,255,1)",
  "hsl(0,0%,100%)", "#ffff", "#ffffffff"]);
function isWhiteCss(v) {
  v = v.replace(/\s+/g, "").toLowerCase().replace(/!important$/, "");
  if (WHITE.has(v)) return true;
  const m = v.match(/^#([0-9a-f]{6})$/);
  if (m) return [0, 2, 4].every((i) => parseInt(m[1].slice(i, i + 2), 16) >= 0xf0);
  const r = v.match(/^rgba?\((\d+),(\d+),(\d+)(?:,([\d.]+))?\)$/);
  return Boolean(r) && [r[1], r[2], r[3]].every((x) => +x >= 240) && (r[4] === undefined || +r[4] > 0.5);
}
const isTransparent = (v) => /^(transparent|rgba\([^)]*,\s*0(\.0+)?\)|#[0-9a-f]{6}00|#[0-9a-f]{3}0)$/i.test(v.trim());

function pxValue(v) {
  const m = v.trim().toLowerCase().match(/^(-?[\d.]+)(px|pt|em|rem|%|vw|vh)?$/);
  if (!m) return null;
  const n = parseFloat(m[1]);
  const unit = m[2] || "px";
  return unit === "pt" ? n * 4 / 3 : unit === "em" || unit === "rem" ? n * 16 : unit === "px" ? n : null;
}

/** CSS declarations -> hiding reasons. */
export function cssHiding(style) {
  const d = {};
  for (const part of style.split(";")) {
    const i = part.indexOf(":");
    if (i > 0) d[part.slice(0, i).trim().toLowerCase()] = part.slice(i + 1).trim().toLowerCase().replace(/\s*!important$/, "");
  }
  const out = [];
  if (d.display === "none") out.push("css_display");
  if (d.visibility === "hidden" || d.visibility === "collapse") out.push("css_visibility");
  if (d.opacity !== undefined && parseFloat(d.opacity) <= 0.05) out.push("css_opacity");
  if (d["font-size"] !== undefined) { const px = pxValue(d["font-size"]); if (px !== null && px <= 2) out.push("css_fontsize"); }
  if (d.color !== undefined && (isWhiteCss(d.color) || isTransparent(d.color))) {
    const bg = d.background ?? d["background-color"];
    if (bg === undefined || isWhiteCss(bg) || isTransparent(d.color)) out.push("css_white");
  }
  for (const k of ["left", "top", "right", "margin-left", "margin-top", "text-indent"]) {
    if (d[k] !== undefined) { const px = pxValue(d[k]); if (px !== null && px <= -500) { out.push("css_offscreen"); break; } }
  }
  if (/rect\(\s*0(px)?[\s,]+0(px)?[\s,]+0(px)?[\s,]+0(px)?\s*\)/.test(d.clip || "") || /inset\(\s*(50%|100%)/.test(d["clip-path"] || "")) out.push("css_clip");
  if (/scale\(\s*0(\.0+)?\s*(,\s*0(\.0+)?\s*)?\)/.test(d.transform || "")) out.push("css_size0");
  const w = d.width !== undefined ? pxValue(d.width) : null, h = d.height !== undefined ? pxValue(d.height) : null;
  if ((w === 0 || h === 0 || (w !== null && w <= 1 && h !== null && h <= 1)) && /hidden|clip/.test(d.overflow || "")) out.push("css_size0");
  if (d["max-height"] !== undefined && pxValue(d["max-height"]) === 0 && /hidden|clip/.test(d.overflow || "")) out.push("css_size0");
  return out;
}

/** Simple stylesheet rules: `.cls`, `#id`, `tag`, `tag.cls` (comma lists). Complex selectors are ignored. */
function stylesheetRules(css) {
  const rules = [];
  css = css.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const m of css.matchAll(/([^{}@]+)\{([^{}]*)\}/g)) {
    const hide = cssHiding(m[2]);
    if (!hide.length) continue;
    for (let sel of m[1].split(",")) {
      sel = sel.trim().toLowerCase();
      const s = sel.match(/^([a-z][a-z0-9-]*)?(?:([.#])([a-z0-9_-]+))?$/);
      if (s && (s[1] || s[3])) rules.push({tag: s[1] || null, kind: s[2] || null, name: s[3] || null, hide});
    }
  }
  return rules;
}

function ruleHits(rules, name, a) {
  const classes = new Set((a.class || "").toLowerCase().split(/\s+/).filter(Boolean));
  const id = (a.id || "").toLowerCase();
  const out = [];
  for (const r of rules) {
    if (r.tag && r.tag !== name) continue;
    if (r.kind === "." && !classes.has(r.name)) continue;
    if (r.kind === "#" && id !== r.name) continue;
    out.push(...r.hide);
  }
  return out;
}

export function readHtml(src, where = "page") {
  const segs = [];
  let rules = [];
  for (const m of src.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style\s*>/gi)) rules = rules.concat(stylesheetRules(m[1]));
  const stack = [];                    // {name, hidden: [...]}
  let buf = "", bufHidden = [];
  const cur = () => (stack.length ? stack[stack.length - 1].hidden : []);
  const flush = () => {
    const t = collapseWs(buf).trim();
    if (t) segs.push(seg(t, where, bufHidden));
    buf = "";
  };
  const emit = (text, hidden) => {
    const key = [...new Set(hidden)].sort().join(",");
    if (key !== [...new Set(bufHidden)].sort().join(",")) { flush(); bufHidden = [...new Set(hidden)]; }
    buf += text;
  };
  let raw = null;                      // inside a raw-text element: {name, hidden, text}
  for (const tk of tokens(src)) {
    if (raw) {
      if (tk.t === "close" && tk.name === raw.name) {
        let text = decodeEntities(raw.text);
        if (raw.name === "style") text = [...text.matchAll(/\/\*([\s\S]*?)\*\//g)].map((m) => m[1]).join(" ");
        else if (raw.name === "script") text = text.slice(0, 20000);
        text = collapseWs(text).trim();
        if (text) { flush(); segs.push(seg(text, where, raw.hidden)); }
        raw = null;
      } else {
        raw.text += tk.t === "text" ? tk.text : tk.t === "comment" ? "" : tokenSource(tk);
      }
      continue;
    }
    if (tk.t === "comment") {
      const t = collapseWs(tk.text).trim();
      if (t) { flush(); segs.push(seg(t, where, [...cur(), "html_comment"])); }
      continue;
    }
    if (tk.t === "text") { emit(decodeEntities(tk.text), cur()); continue; }
    if (tk.t === "open") {
      const a = tk.attrs;
      const hide = [...cur()];
      if ("hidden" in a) hide.push("attr_hidden");
      if (a.style) hide.push(...cssHiding(a.style));
      if (tk.name === "font" && a.color && isWhiteCss(a.color)) hide.push("css_white");
      hide.push(...ruleHits(rules, tk.name, a));
      if (tk.name === "meta" && a.content && /^(description|keywords|author|og:|twitter:)/i.test(a.name || a.property || "")) {
        flush(); segs.push(seg(collapseWs(a.content).trim(), where, [...hide, "meta"]));
      }
      for (const k of ["alt", "title", "aria-label", "placeholder", "data-instructions"]) {
        if (a[k] && a[k].trim()) { flush(); segs.push(seg(collapseWs(a[k]).trim(), where, [...hide, k === "alt" ? "alt" : "attr_text"])); }
      }
      if (BLOCK.has(tk.name)) flush();
      if (RAWTEXT.has(tk.name) && !tk.self) {
        const why = tk.name === "title" ? "title" : tk.name === "template" ? "template" : tk.name === "noscript" ? "noscript" :
          tk.name === "script" ? "script" : tk.name === "style" ? "style_block" : null;
        raw = {name: tk.name, hidden: why ? [...hide, why] : hide, text: ""};
        continue;
      }
      if (!VOID.has(tk.name) && !tk.self) stack.push({name: tk.name, hidden: hide});
      continue;
    }
    if (tk.t === "close") {
      const i = stack.map((s) => s.name).lastIndexOf(tk.name);
      if (i >= 0) stack.length = i;
      if (BLOCK.has(tk.name)) flush();
    }
  }
  if (raw && raw.text.trim()) segs.push(seg(collapseWs(decodeEntities(raw.text)).trim(), where, raw.hidden));
  flush();
  return segs;
}

function tokenSource(tk) {
  if (tk.t === "close") return `</${tk.name}>`;
  return `<${tk.name}${Object.entries(tk.attrs || {}).map(([k, v]) => ` ${k}="${v}"`).join("")}${tk.self ? "/" : ""}>`;
}

export function looksLikeHtml(text) {
  const head = text.slice(0, 4000).toLowerCase();
  if (/^\s*(<!doctype html|<html[\s>])/.test(head)) return true;
  return (head.match(/<(div|span|p|table|td|font|body|br|style|a)[\s>\/]/g) || []).length >= 2;
}

// ---------------------------------------------------------------- ZIP (for .docx)
const u16 = (b, o) => b[o] | (b[o + 1] << 8);
const u32 = (b, o) => (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16)) + b[o + 3] * 0x1000000;

export function zipEntries(bytes) {
  let eocd = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) {
    if (bytes[i] === 0x50 && bytes[i + 1] === 0x4b && bytes[i + 2] === 5 && bytes[i + 3] === 6) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error("not a zip archive");
  const count = u16(bytes, eocd + 10);
  if (count > LIMITS.maxEntries) throw new Error("too many files in the archive");
  let p = u32(bytes, eocd + 16);
  const out = new Map();
  for (let n = 0; n < count; n++) {
    if (p + 46 > bytes.length || u32(bytes, p) !== 0x02014b50) throw new Error("broken zip directory");
    const method = u16(bytes, p + 10), csize = u32(bytes, p + 20), usize = u32(bytes, p + 24);
    const nlen = u16(bytes, p + 28), xlen = u16(bytes, p + 30), clen = u16(bytes, p + 32), local = u32(bytes, p + 42);
    const name = new TextDecoder().decode(bytes.subarray(p + 46, p + 46 + nlen));
    out.set(name, {method, csize, usize, local});
    p += 46 + nlen + xlen + clen;
  }
  return out;
}

async function inflateRaw(data, cap) {
  const ds = new DecompressionStream("deflate-raw");
  const reader = new Blob([data]).stream().pipeThrough(ds).getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const {done, value} = await reader.read();
    if (done) break;
    total += value.length;
    if (total > cap) { await reader.cancel(); throw new Error("archive expands too much (possible zip bomb)"); }
    chunks.push(value);
  }
  const out = new Uint8Array(total);
  let o = 0;
  for (const c of chunks) { out.set(c, o); o += c.length; }
  return out;
}

export async function zipRead(bytes, entries, name, budget) {
  const e = entries.get(name);
  if (!e) return null;
  const p = e.local;
  if (u32(bytes, p) !== 0x04034b50) throw new Error("broken zip entry");
  const start = p + 30 + u16(bytes, p + 26) + u16(bytes, p + 28);
  const data = bytes.subarray(start, start + e.csize);
  const cap = Math.min(budget.left, Math.max(e.csize, 1) * LIMITS.maxRatio + 65536);
  let out;
  if (e.method === 0) out = data.slice();
  else if (e.method === 8) out = await inflateRaw(data, cap);
  else throw new Error(`unsupported zip compression (${e.method})`);
  budget.left -= out.length;
  if (budget.left < 0) throw new Error("archive expands too much (possible zip bomb)");
  return new TextDecoder("utf-8").decode(out);
}

// ---------------------------------------------------------------- DOCX
const valOn = (a) => !("w:val" in a) || !/^(0|false|off|none)$/i.test(a["w:val"]);
function whiteHex(v) {
  if (!v || !/^[0-9a-f]{6}$/i.test(v)) return false;
  return [0, 2, 4].every((i) => parseInt(v.slice(i, i + 2), 16) >= 0xf0);
}

function rprProps(a, name, into) {
  if (name === "w:vanish" || name === "w:specvanish" || name === "w:webhidden") into.vanish = valOn(a);
  else if (name === "w:color") into.color = (a["w:themecolor"] || "").toLowerCase() === "background1" ? "FFFFFF" : (a["w:val"] || "auto");
  else if (name === "w:sz") into.sz = parseInt(a["w:val"], 10);
  else if (name === "w:shd") into.shd = (a["w:fill"] || "auto");
  else if (name === "w:rstyle") into.rStyle = a["w:val"];
}

/** styles.xml -> {defaults: props, styles: {id: {basedOn, props}}} */
function readStyles(xml) {
  const res = {defaults: {}, styles: {}};
  if (!xml) return res;
  let style = null, inRpr = false, inDefaults = false;
  for (const tk of tokens(xml)) {
    if (tk.t === "open") {
      const a = tk.attrs;
      if (tk.name === "w:style") { style = {basedOn: null, props: {}}; res.styles[a["w:styleid"] || ""] = style; }
      else if (tk.name === "w:rprdefault") inDefaults = true;
      else if (tk.name === "w:rpr") inRpr = !tk.self;
      else if (tk.name === "w:basedon" && style) style.basedOn = a["w:val"];
      else if (inRpr) rprProps(a, tk.name, inDefaults ? res.defaults : style ? style.props : {});
    } else if (tk.t === "close") {
      if (tk.name === "w:style") style = null;
      else if (tk.name === "w:rprdefault") inDefaults = false;
      else if (tk.name === "w:rpr") inRpr = false;
    }
  }
  return res;
}

function resolveStyle(st, id, depth = 0) {
  const s = id && st.styles[id];
  if (!s || depth > 20) return {};
  return {...resolveStyle(st, s.basedOn, depth + 1), ...s.props};
}

function runHidden(p) {
  const out = [];
  if (p.vanish) out.push("vanish");
  if (whiteHex(p.color) && (!p.shd || p.shd === "auto" || whiteHex(p.shd))) out.push("white");
  if (Number.isFinite(p.sz) && p.sz <= 4) out.push("tiny");
  return out;
}

/** A WordprocessingML part -> segments (one per paragraph and visibility state). */
export function readWordXml(xml, st, where) {
  const segs = [];
  const paras = [];                        // stack: {style, parts: [{text, hidden}]}
  let run = null, inRpr = false, inPpr = false, fallback = 0, textMode = null;
  const pushText = (text) => {
    if (!run || !paras.length) return;
    const extra = textMode === "w:deltext" ? ["tracked_deletion"] : textMode === "w:instrtext" ? ["field_code"] : [];
    run.parts.push({text, extra});
  };
  for (const tk of tokens(xml)) {
    if (tk.t === "open" && tk.name === "mc:fallback" && !tk.self) { fallback++; continue; }
    if (tk.t === "close" && tk.name === "mc:fallback") { fallback = Math.max(0, fallback - 1); continue; }
    if (fallback) continue;
    if (tk.t === "open") {
      const a = tk.attrs;
      switch (tk.name) {
        case "w:p": if (!tk.self) paras.push({style: null, runs: []}); break;
        case "w:ppr": inPpr = !tk.self; break;
        case "w:pstyle": if (inPpr && !run && paras.length) paras[paras.length - 1].style = a["w:val"]; break;
        case "w:r": if (!tk.self) run = {props: {}, parts: []}; break;
        case "w:rpr": inRpr = !tk.self && Boolean(run); break;
        case "w:t": case "w:deltext": case "w:instrtext": if (!tk.self) textMode = tk.name; break;
        case "w:tab": if (run && !inRpr) pushText("\t"); break;
        case "w:br": case "w:cr": if (run && !inRpr) pushText("\n"); break;
        default: if (inRpr && run) rprProps(a, tk.name, run.props);
      }
      continue;
    }
    if (tk.t === "text") {
      if (textMode && run) pushText(decodeEntities(tk.text));
      continue;
    }
    if (tk.t === "close") {
      switch (tk.name) {
        case "w:t": case "w:deltext": case "w:instrtext": textMode = null; break;
        case "w:rpr": inRpr = false; break;
        case "w:ppr": inPpr = false; break;
        case "w:r":
          if (run && paras.length) paras[paras.length - 1].runs.push(run);
          run = null;
          break;
        case "w:p": {
          const p = paras.pop();
          if (!p) break;
          const pStyle = resolveStyle(st, p.style);
          let cur = null;
          for (const r of p.runs) {
            const eff = {...st.defaults, ...pStyle, ...resolveStyle(st, r.props.rStyle), ...r.props};
            const base = runHidden(eff);
            for (const part of r.parts) {
              const hidden = [...base, ...part.extra];
              const key = hidden.slice().sort().join(",");
              if (cur && cur.key === key) cur.text += part.text;
              else { if (cur) segs.push(cur); cur = {key, text: part.text, hidden}; }
            }
          }
          if (cur) segs.push(cur);
          break;
        }
        default:
      }
    }
  }
  return segs.filter((s) => s.text.trim()).map((s) => seg(s.text.replace(/[ \t]+/g, " ").trim(), where, s.hidden));
}

function readCore(xml, where) {
  const out = [];
  if (!xml) return out;
  let field = null;
  for (const tk of tokens(xml)) {
    if (tk.t === "open" && !tk.self) field = tk.name;
    else if (tk.t === "close") field = null;
    else if (tk.t === "text" && field && /^(dc:title|dc:subject|dc:description|cp:keywords|cp:category|dc:creator|cp:lastmodifiedby|company|manager|vt:lpwstr)$/.test(field)) {
      const t = decodeEntities(tk.text).trim();
      if (t) out.push(seg(t, where, ["doc_metadata"]));
    }
  }
  return out;
}

export async function readDocx(bytes) {
  const entries = zipEntries(bytes);
  const budget = {left: LIMITS.maxUnzipped};
  const read = (n) => zipRead(bytes, entries, n, budget);
  if (!entries.has("word/document.xml")) throw new Error("not a Word document (.docx)");
  const st = readStyles(await read("word/styles.xml"));
  const segs = readWordXml(await read("word/document.xml"), st, "body");
  const names = [...entries.keys()].sort();
  for (const n of names) {
    const m = n.match(/^word\/(header|footer)\d*\.xml$/);
    if (m) segs.push(...readWordXml(await read(n), st, m[1]));
  }
  for (const [n, where] of [["word/footnotes.xml", "footnote"], ["word/endnotes.xml", "endnote"]]) {
    if (entries.has(n)) segs.push(...readWordXml(await read(n), st, where));
  }
  if (entries.has("word/comments.xml")) {
    for (const s of readWordXml(await read("word/comments.xml"), st, "comment")) segs.push(seg(s.text, "comment", [...s.hidden, "doc_comment"]));
  }
  for (const n of ["docProps/core.xml", "docProps/app.xml", "docProps/custom.xml"]) {
    if (entries.has(n)) segs.push(...readCore(await read(n), "properties"));
  }
  const notes = [];
  if (names.some((n) => /^word\/(vbaProject\.bin|activeX\/)/.test(n))) notes.push("macros_present");
  if (names.some((n) => /^word\/embeddings\//.test(n))) notes.push("embedded_objects");
  if (names.some((n) => /^word\/media\//.test(n))) notes.push("images_not_checked");
  return {segments: segs, notes};
}

// ---------------------------------------------------------------- E-MAIL (MIME)
const latin1 = (bytes) => { let s = ""; for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]); return s; };
const toBytes = (s) => Uint8Array.from(s, (c) => c.charCodeAt(0) & 0xff);

function decodeCharset(bytes, charset) {
  const cs = (charset || "utf-8").trim().toLowerCase().replace(/^"|"$/g, "");
  try {
    return new TextDecoder(cs === "us-ascii" || cs === "ascii" ? "utf-8" : cs).decode(bytes);
  } catch (e) {
    return new TextDecoder("utf-8").decode(bytes);
  }
}

function qpDecode(s) {
  return toBytes(s.replace(/=\r?\n/g, "").replace(/=([0-9A-Fa-f]{2})/g, (m, h) => String.fromCharCode(parseInt(h, 16))));
}
function b64Bytes(s) {
  let clean = s.replace(/[^A-Za-z0-9+/]/g, "");
  if (clean.length % 4 === 1) clean = clean.slice(0, -1);
  clean += "=".repeat((4 - (clean.length % 4)) % 4);
  try { return toBytes(atob(clean)); } catch (e) { return new Uint8Array(0); }
}

/** RFC 2047 encoded words in a header. */
export function decodeHeader(v) {
  return v.replace(/=\?([^?]+)\?([bBqQ])\?([^?]*)\?=(\s+(?==\?))?/g, (m, cs, enc, data) => {
    const bytes = enc.toUpperCase() === "B" ? b64Bytes(data) : qpDecode(data.replace(/_/g, " "));
    return decodeCharset(bytes, cs);
  });
}

function parseHeaders(block) {
  const headers = [];
  for (const line of block.split(/\r?\n/)) {
    if (/^[ \t]/.test(line) && headers.length) headers[headers.length - 1][1] += " " + line.trim();
    else {
      const i = line.indexOf(":");
      if (i > 0) headers.push([line.slice(0, i).trim().toLowerCase(), line.slice(i + 1).trim()]);
    }
  }
  return headers;
}
const hget = (hs, k) => (hs.find(([n]) => n === k) || [null, ""])[1];
function param(v, k) {
  const m = v.match(new RegExp(`(?:^|;)\\s*${k}\\*?\\s*=\\s*(?:"([^"]*)"|([^;\\s]+))`, "i"));
  if (!m) return "";
  let s = m[1] ?? m[2];
  const ext = s.match(/^([^']*)'[^']*'(.*)$/);            // RFC 2231: charset''percent-encoded
  if (ext) s = decodeCharset(toBytes(ext[2].replace(/%([0-9A-Fa-f]{2})/g, (_, h) => String.fromCharCode(parseInt(h, 16)))), ext[1]);
  return decodeHeader(s);
}

export function looksLikeEmail(text) {
  const head = text.slice(0, 8000);
  const end = head.search(/\r?\n\r?\n/);
  if (end < 0) return false;
  const hs = parseHeaders(head.slice(0, end));
  const names = new Set(hs.map(([n]) => n));
  return hs.length >= 2 && hs.length === head.slice(0, end).split(/\r?\n/).filter((l) => !/^[ \t]/.test(l)).length &&
    (names.has("content-type") || names.has("mime-version")) && (names.has("from") || names.has("subject") || names.has("to"));
}

/** raw: a "binary string" (one char per byte). */
async function readMime(raw, where, depth, out) {
  if (depth > LIMITS.maxDepth) { out.notes.push("too_deep"); return; }
  const sep = raw.search(/\r?\n\r?\n/);
  const head = sep < 0 ? raw : raw.slice(0, sep);
  const body = sep < 0 ? "" : raw.slice(sep).replace(/^\r?\n\r?\n/, "");
  const hs = parseHeaders(head);
  const ctype = hget(hs, "content-type") || "text/plain";
  const type = ctype.split(";")[0].trim().toLowerCase();
  const cte = hget(hs, "content-transfer-encoding").toLowerCase();
  const disp = hget(hs, "content-disposition");
  const fname = param(disp, "filename") || param(ctype, "name");
  if (depth === 0) {
    for (const k of ["from", "reply-to", "to", "cc", "subject"]) {
      const v = hget(hs, k);
      if (v) out.headers[k] = decodeHeader(decodeCharset(toBytes(v), "utf-8"));
    }
    if (out.headers.subject) out.segments.push(seg(out.headers.subject, "subject"));
  }
  if (type.startsWith("multipart/")) {
    const boundary = param(ctype, "boundary");
    if (!boundary) return;
    const parts = body.split(new RegExp(`\\r?\\n?--${boundary.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:--)?[ \\t]*\\r?\\n?`));
    for (const p of parts.slice(1)) if (p.trim()) await readMime(p, where, depth + 1, out);
    return;
  }
  if (type === "message/rfc822") { await readMime(body, "forwarded", depth + 1, out); return; }
  const bytes = cte === "base64" ? b64Bytes(body) : cte === "quoted-printable" ? qpDecode(body) : toBytes(body);
  const isAttachment = /^attachment/i.test(disp) || (fname && !type.startsWith("text/"));
  const label = isAttachment ? `attachment:${fname || type}` : where;
  if (isAttachment) out.attachments.push({name: fname || "(no name)", type, size: bytes.length});
  if (type === "text/html") {
    out.segments.push(...readHtml(decodeCharset(bytes, param(ctype, "charset")), label));
  } else if (type.startsWith("text/") || /\.(txt|md|csv|json|ya?ml)$/i.test(fname)) {
    const t = decodeCharset(bytes, param(ctype, "charset"));
    if (t.trim()) out.segments.push(seg(t.trim(), label));
  } else if (/\.docx$/i.test(fname) || type.includes("wordprocessingml")) {
    try {
      const d = await readDocx(bytes);
      out.segments.push(...d.segments.map((s) => ({...s, where: `${label} › ${s.where}`})));
      out.notes.push(...d.notes);
    } catch (e) { out.notes.push("attachment_unreadable"); }
  } else if (isAttachment) {
    out.notes.push("attachments_not_checked");
  }
}

export async function readEmail(bytesOrText) {
  const raw = typeof bytesOrText === "string" ? latin1(new TextEncoder().encode(bytesOrText)) : latin1(bytesOrText);
  const out = {segments: [], headers: {}, attachments: [], notes: []};
  await readMime(raw, "body", 0, out);
  // multipart/alternative carries the same visible text twice (plain + HTML): keep one copy
  const seenText = new Set();
  out.segments = out.segments.filter((s) => {
    if (s.seen !== "visible") return true;
    const key = `${s.where}\u0000${s.text.replace(/\s+/g, " ")}`;
    if (seenText.has(key)) return false;
    seenText.add(key);
    return true;
  });
  const from = out.headers["from"] || "", reply = out.headers["reply-to"] || "";
  const dom = (v) => ((v.match(/@([A-Za-z0-9.-]+)/) || [])[1] || "").toLowerCase();
  if (reply && dom(reply) && dom(from) && dom(reply) !== dom(from)) out.notes.push("reply_to_differs");
  return out;
}

// ---------------------------------------------------------------- sniffing
export function sniff(name, bytes) {
  const n = (name || "").toLowerCase();
  const head = bytes.subarray(0, 8);
  if (head[0] === 0x50 && head[1] === 0x4b) {
    if (/\.(docx|docm|dotx)$/.test(n) || !/\.(xlsx|pptx|odt|ods|odp|zip|jar|apk)$/.test(n)) return "docx";
    return "unsupported";
  }
  if (head[0] === 0x25 && head[1] === 0x50 && head[2] === 0x44 && head[3] === 0x46) return "pdf";
  if (/\.(png|jpe?g|gif|webp|heic|bmp|svgz?)$/.test(n)) return "image";
  if (/\.(eml|mht|mhtml)$/.test(n)) return "email";
  if (/\.(html?|xhtml)$/.test(n)) return "html";
  if (/\.(doc|xls|ppt|rtf|odt|pages|key|numbers|zip|rar|7z|exe|dll|bin)$/.test(n)) return "unsupported";
  let ctrl = 0;
  const probe = bytes.subarray(0, 4096);
  for (const b of probe) if (b === 0 || (b < 9) || (b > 13 && b < 32 && b !== 27)) ctrl++;
  return ctrl > probe.length * 0.02 ? "unsupported" : "text";
}
