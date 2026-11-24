// Compare the browser engine with the Python results in a corpus file.
// usage: node tools/parity/check_parity.mjs corpus.json [--d2-only]
import {readFileSync} from "node:fs";
import {screen} from "../../src/nitaq/web/engine/scanner.js";

const corpus = JSON.parse(readFileSync(process.argv[2], "utf-8"));
const d2Only = process.argv.includes("--d2-only");
const norm = (x) => JSON.parse(JSON.stringify(x), (k, v) => (typeof v === "number" ? Math.round(v * 1000) / 1000 : v));
let bad = 0, n = 0;
function cmp(kind, i, got, exp, text) {
  n++;
  const a = JSON.stringify(norm(got)), b = JSON.stringify(norm(exp));
  if (a !== b) {
    bad++;
    if (bad <= 6) console.log(`MISMATCH ${kind}#${i}: ${JSON.stringify(text.slice(0, 90))}\n  js: ${a.slice(0, 400)}\n  py: ${b.slice(0, 400)}`);
  }
}
corpus.d2.forEach((c, i) => cmp("d2", i, screen(c.text), c.expect, c.text));
if (!d2Only) {
  const {scanText} = await import("../../src/nitaq/web/engine/skillscan.js");
  for (const [i, c] of corpus.skill.entries()) cmp("skill", i, await scanText(c.text, c.name), c.expect, c.text);
}
console.log(`${n - bad}/${n} identical`);
process.exit(bad ? 1 : 0);
