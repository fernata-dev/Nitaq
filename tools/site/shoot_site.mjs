// Screenshot the website (AR/EN, desktop/phone) and fail on console errors.
// usage: node tools/site/shoot_site.mjs BASE_URL OUT_DIR
import {createRequire} from "node:module";
const require = createRequire(import.meta.url);
const {chromium, devices} = require("playwright");
const [base, out] = process.argv.slice(2);
const errors = [];
const b = await chromium.launch();
for (const [tag, opts, path] of [["desk-ar", {viewport: {width: 1440, height: 900}}, ""], ["desk-en", {viewport: {width: 1440, height: 900}}, "en/"],
                                  ["phone-ar", {...devices["iPhone 13"]}, ""]]) {
  const ctx = await b.newContext({...opts, reducedMotion: "reduce"});
  const p = await ctx.newPage();
  p.on("console", (m) => { if (m.type() === "error") errors.push(`${tag}: ${m.text()}`); });
  p.on("pageerror", (e) => errors.push(`${tag}: ${e.message}`));
  await p.goto(base + path); await p.waitForTimeout(600);
  for (let y = 0; y < 40000; y += 700) { await p.evaluate((yy) => window.scrollTo(0, yy), y); await p.waitForTimeout(40); }
  await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(500);
  await p.screenshot({path: `${out}/${tag}-full.png`, fullPage: true});
  await ctx.close();
}
await b.close();
console.log(errors.length ? errors.join("\n") : "no console errors");
