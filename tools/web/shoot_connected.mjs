// Screenshot the desktop ("connected") mode against a running `nitaq ui` (fake HOME in tests).
// usage: node tools/web/shoot_connected.mjs "http://127.0.0.1:PORT/#token=..." OUT_DIR
import {createRequire} from "node:module";
const require = createRequire(import.meta.url);
const {chromium, devices} = require("playwright");
const [url, out] = process.argv.slice(2);
const errors = [];
const b = await chromium.launch();
for (const [tag, opts] of [["desktop", {viewport: {width: 1440, height: 900}}], ["phone", {...devices["Pixel 7"]}]]) {
  const ctx = await b.newContext(opts);
  const p = await ctx.newPage();
  p.on("console", (m) => { if (m.type() === "error") errors.push(`${tag}: ${m.text()}`); });
  p.on("pageerror", (e) => errors.push(`${tag}: ${e.message}`));
  await p.goto(url);
  await p.waitForSelector(".connected .status-hero", {timeout: 15000});
  await p.waitForTimeout(900);
  await p.screenshot({path: `${out}/connected-${tag}-1-status.png`});
  await p.getByRole("button", {name: "الحماية", exact: true}).click();
  await p.waitForTimeout(500);
  await p.getByRole("button", {name: "عاين التغييرات"}).click();
  await p.waitForSelector(".diff", {timeout: 15000});
  await p.waitForTimeout(600);
  await p.screenshot({path: `${out}/connected-${tag}-2-protect.png`, fullPage: tag === "desktop"});
  await p.getByRole("button", {name: "جرّب قرار", exact: true}).click();
  await p.waitForTimeout(400);
  await p.getByRole("button", {name: "~/.ssh/id_rsa"}).click();
  await p.waitForSelector(".verdict", {timeout: 15000});
  await p.waitForTimeout(800);
  await p.screenshot({path: `${out}/connected-${tag}-3-decision.png`});
  await ctx.close();
}
await b.close();
if (errors.length) { console.log(errors.join("\n")); process.exit(1); }
console.log("connected mode: no console errors");
