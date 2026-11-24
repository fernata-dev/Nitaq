// One entry point for the app: check a file or pasted text, entirely on this device.
// Readers (docs.js) split the input into segments and mark what a person would not see; the
// skill/text scanner (skillscan.js, a byte-exact port of the Python one) looks for instruction-like
// text, invisible characters, encoded blobs, look-alike letters, addresses and shell commands.
//
// Verdicts are deliberately modest:
//   danger  -> hidden or unseen text that reads like instructions, or another high-severity sign
//   warn    -> hidden text, or medium-severity signs, that a person should look at
//   clear   -> nothing found by these checks (NOT proof that the content is safe)
//   unsupported -> this kind of file is not read at all (e.g. PDF, images)
import {LIMITS, looksLikeEmail, looksLikeHtml, readDocx, readEmail, readHtml, sniff} from "./docs.js";
import {scanText} from "./skillscan.js";

const SEV = {info: 0, low: 1, medium: 2, high: 3};
const TEXT_RULES_SKIPPED_IN_DOCS = new Set(["front_matter_missing", "front_matter_powerful_tools"]);
const SKILL_NAME = /(^|\/)(skill\.md|.*\.mdc?|agents\.md|claude\.md|gemini\.md|.*\.json|.*\.ya?ml)$/i;

/** Text -> paragraph segments with their first line number (1-based). */
function paragraphs(text) {
  const out = [];
  const lines = text.split("\n");
  let buf = [], start = 1;
  lines.forEach((line, i) => {
    if (line.trim()) { if (!buf.length) start = i + 1; buf.push(line); }
    else if (buf.length) { out.push({text: buf.join("\n"), line: start, end: i}); buf = []; }
  });
  if (buf.length) out.push({text: buf.join("\n"), line: start, end: lines.length});
  return out;
}

async function scanSegments(segments) {
  const out = [];
  for (const s of segments.slice(0, LIMITS.maxSegments)) {
    const rep = await scanText(s.text, "segment.txt");
    const findings = rep.findings.filter((f) => !TEXT_RULES_SKIPPED_IN_DOCS.has(f.rule));
    out.push({...s, findings});
  }
  return out;
}

function finish(base) {
  const segs = base.segments;
  const all = [];
  segs.forEach((s, i) => {
    s.instruction = s.findings.some((f) => f.rule.startsWith("injection_"));
    s.flagged = s.findings.some((f) => f.d2_flagged);
    for (const f of s.findings) all.push({...f, segment: i, seen: s.seen});
  });
  const hidden = segs.filter((s) => s.seen === "hidden");
  const unseen = segs.filter((s) => s.seen === "unseen");
  const top = all.reduce((m, f) => Math.max(m, SEV[f.severity]), 0);
  const hiddenInstr = segs.some((s) => s.seen !== "visible" && s.instruction &&
    s.findings.some((f) => f.rule.startsWith("injection_") && SEV[f.severity] >= SEV.medium));
  const signals = new Set(["reply_to_differs", "macros_present"]);
  let verdict = "clear";
  if (top >= SEV.high || hiddenInstr) verdict = "danger";
  // Hidden text in a Word file is unusual; in web pages and newsletters (menus, preview text,
  // screen-reader labels) it is everyday markup, so there it only matters with other signs.
  else if ((base.kind === "docx" && hidden.length) || top >= SEV.medium ||
           (base.notes || []).some((n) => signals.has(n))) verdict = "warn";
  const destinations = [...new Set(all.filter((f) => f.rule === "external_address").map((f) => f.evidence))];
  return {
    ...base, verdict, findings: all, destinations,
    counts: {segments: segs.length, hidden: hidden.length, unseen: unseen.length,
             high: all.filter((f) => f.severity === "high").length, medium: all.filter((f) => f.severity === "medium").length},
    note: "Checked on this device only. A clean result is not proof that the content is safe.",
  };
}

/** A pasted text: raw e-mail source, HTML, or plain text / Markdown. */
export async function checkText(text, name = "pasted text") {
  if (looksLikeEmail(text)) {
    const e = await readEmail(text);
    return finish({kind: "email", name, headers: e.headers, attachments: e.attachments, notes: e.notes,
                   segments: await scanSegments(e.segments)});
  }
  if (looksLikeHtml(text)) {
    return finish({kind: "html", name, notes: [], segments: await scanSegments(readHtml(text))});
  }
  return checkPlain(text, name);
}

/** Plain text, Markdown, SKILL.md, JSON manifests: the full skill/text scanner on the whole text. */
async function checkPlain(text, name) {
  const asSkill = SKILL_NAME.test(name);
  const rep = await scanText(text, name);
  const findings = asSkill ? rep.findings : rep.findings.filter((f) => !TEXT_RULES_SKIPPED_IN_DOCS.has(f.rule));
  const paras = paragraphs(text);
  const segments = paras.map((p) => ({text: p.text, where: `line ${p.line}`, hidden: [], seen: "visible", line: p.line, findings: []}));
  if (!segments.length) segments.push({text: "", where: "line 1", hidden: [], seen: "visible", line: 1, findings: []});
  // Hidden carriers inside a visible paragraph: the paragraph stays visible and carries a marker;
  // what the carrier hides (decoded) becomes its own hidden segment right after it, for the X-ray.
  const CARRIERS = {hidden_comment: "html_comment", hidden_html: "css_display", tag_characters: "tag_characters",
                    encoded_blob: "encoded", zero_width: "zero_width", bidi_control: "bidi", homoglyph_mix: "homoglyph"};
  const revealed = segments.map(() => []);
  for (const f of findings) {
    let i = paras.findIndex((p) => f.line >= p.line && f.line <= p.end);
    if (i < 0) i = 0;
    segments[i].findings.push(f);
    const c = CARRIERS[f.rule];
    if (!c) continue;
    segments[i].carriers = [...new Set([...(segments[i].carriers || []), c])];
    const shown = f.decoded ?? (f.rule === "hidden_comment" || f.rule === "hidden_html" ? f.evidence : null);
    if (shown && shown.trim() && c !== "homoglyph") {
      revealed[i].push({text: shown, where: `line ${f.line}`, hidden: [c], seen: "hidden", line: f.line, findings: [], from: f.id});
    }
  }
  const out = segments.flatMap((s, i) => [s, ...revealed[i]]);
  return finish({kind: asSkill ? "skill" : "text", name, notes: [], segments: out, frontMatter: rep.front_matter});
}

/** A file picked or dropped by the user. */
export async function checkFile(name, bytes) {
  if (bytes.length > LIMITS.maxInput) return {kind: "unsupported", name, verdict: "unsupported", reason: "too_large", segments: [], findings: []};
  const kind = sniff(name, bytes);
  if (kind === "pdf" || kind === "image" || kind === "unsupported") {
    return {kind, name, verdict: "unsupported", reason: kind, segments: [], findings: []};
  }
  try {
    if (kind === "docx") {
      const d = await readDocx(bytes);
      return finish({kind, name, notes: d.notes, segments: await scanSegments(d.segments)});
    }
    if (kind === "email") {
      const e = await readEmail(bytes);
      return finish({kind, name, headers: e.headers, attachments: e.attachments, notes: e.notes, segments: await scanSegments(e.segments)});
    }
    const text = new TextDecoder("utf-8", {ignoreBOM: true}).decode(bytes);
    if (kind === "html") return finish({kind, name, notes: [], segments: await scanSegments(readHtml(text))});
    if (/\.(eml)$/i.test(name) || looksLikeEmail(text)) return checkText(text, name);
    if (looksLikeHtml(text) && !SKILL_NAME.test(name)) return checkText(text, name);
    return checkPlain(text, name);
  } catch (e) {
    const detail = String(e.message || e);
    return {kind, name, verdict: "unsupported", reason: /zip bomb|too many/.test(detail) ? "too_large" : "unreadable", detail,
            segments: [], findings: []};
  }
}
