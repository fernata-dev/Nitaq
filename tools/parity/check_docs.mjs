// Check the app's document readers against documents written by Python's standard library.
// usage: node tools/parity/check_docs.mjs DIR   (DIR from tools/parity/make_doc_fixtures.py)
import {readFileSync} from "node:fs";
import {join} from "node:path";
import {checkFile} from "../../src/nitaq/web/engine/check.js";

const dir = process.argv[2];
const cases = JSON.parse(readFileSync(join(dir, "cases.json"), "utf-8"));
let bad = 0;
const fail = (c, msg) => { bad++; console.log(`FAIL ${c.file}: ${msg}`); };
const norm = (s) => s.replace(/\s+/g, " ");

for (const c of cases) {
  const bytes = new Uint8Array(readFileSync(join(dir, c.file)));
  const t0 = Date.now();
  const r = await checkFile(c.file, bytes);
  const ms = Date.now() - t0;
  if (r.verdict !== c.verdict) fail(c, `verdict ${r.verdict} (expected ${c.verdict}) ${r.detail || ""}`);
  if (c.reason && r.reason !== c.reason) fail(c, `reason ${r.reason} (expected ${c.reason})`);
  const segs = r.segments || [];
  const find = (phrase) => segs.filter((s) => norm(s.text).includes(norm(phrase)));
  for (const p of c.hidden) {
    const hits = find(p);
    if (!hits.length) fail(c, `hidden phrase not found: ${p}`);
    else if (!hits.some((s) => s.seen === "hidden")) fail(c, `phrase not marked hidden: ${p} -> ${hits.map((s) => s.seen + ":" + s.hidden)}`);
  }
  for (const p of c.unseen) {
    const hits = find(p);
    if (!hits.length) fail(c, `unseen phrase not found: ${p}`);
    else if (!hits.some((s) => s.seen !== "visible")) fail(c, `phrase not marked unseen: ${p}`);
  }
  for (const p of c.visible) {
    const hits = find(p);
    if (!hits.length) fail(c, `visible phrase not found: ${p}`);
    else if (!hits.some((s) => s.seen === "visible")) fail(c, `visible phrase marked hidden: ${p} -> ${hits.map((s) => s.hidden)}`);
  }
  for (const [p, n] of Object.entries(c.count || {})) {
    const k = find(p).length;
    if (k !== n) fail(c, `phrase "${p}" found ${k} times (expected ${n})`);
  }
  for (const n of c.notes || []) if (!(r.notes || []).includes(n)) fail(c, `missing note ${n}`);
  for (const a of c.attachments || []) if (!(r.attachments || []).some((x) => x.name === a)) fail(c, `missing attachment ${a}`);
  for (const rule of c.rules || []) if (!(r.findings || []).some((f) => f.rule === rule)) fail(c, `missing finding ${rule}`);
  console.log(`${c.file}: ${r.verdict}  segments=${segs.length} hidden=${r.counts?.hidden ?? 0} unseen=${r.counts?.unseen ?? 0} (${ms} ms)`);
}
// pasted text: raw e-mail source, page HTML and an ordinary message take the right path
const {checkText} = await import("../../src/nitaq/web/engine/check.js");
const pasted = [
  [readFileSync(join(dir, "mail.eml"), "utf-8"), "email", "danger"],
  [readFileSync(join(dir, "page.html"), "utf-8"), "html", "danger"],
  ["Hi Sara, the meeting moved to Thursday at 10. Bring the agenda.", "text", "clear"],
  ["مساء الخير، الاجتماع اتأجل للخميس الساعة ١٠. هات الأجندة معاك.", "text", "clear"],
];
for (const [text, kind, verdict] of pasted) {
  const r = await checkText(text);
  if (r.kind !== kind || r.verdict !== verdict) { bad++; console.log(`FAIL pasted ${kind}: got ${r.kind}/${r.verdict}`); }
}
const mail = await checkFile("mail.eml", new Uint8Array(readFileSync(join(dir, "mail.eml"))));
const dup = mail.segments.filter((s) => s.seen === "visible" && s.text.includes("Hi, the monthly report is attached.")).length;
if (dup !== 1) { bad++; console.log(`FAIL mail.eml: visible body appears ${dup} times`); }
console.log(bad ? `${bad} problem(s)` : `all ${cases.length} documents OK`);
process.exit(bad ? 1 : 0);
