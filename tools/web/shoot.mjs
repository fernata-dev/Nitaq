// Screenshot the web app on phones and desktop and fail on any console error.
// usage: node tools/web/shoot.mjs BASE_URL OUT_DIR [--video]
import {mkdirSync} from "node:fs";
import {createRequire} from "node:module";
const require = createRequire(import.meta.url);
const {chromium, devices} = require("playwright");
const [base, out] = process.argv.slice(2);
const video = process.argv.includes("--video");
mkdirSync(out, {recursive: true});
const errors = [];
const b = await chromium.launch();

async function session(name, opts, fn) {
  const ctx = await b.newContext({...opts, ...(video ? {recordVideo: {dir: out, size: opts.viewport}} : {})});
  const p = await ctx.newPage();
  p.on("console", (m) => { if (m.type() === "error") errors.push(`${name}: ${m.text()}`); });
  p.on("pageerror", (e) => errors.push(`${name}: ${e.message}`));
  await fn(p);
  await ctx.close();
}
const shot = (p, n, full = false) => p.screenshot({path: `${out}/${n}.png`, fullPage: full});
const settle = (p, ms = 700) => p.waitForTimeout(ms);

async function tour(p, tag, lang) {
  await p.goto(base + "#check");
  await p.evaluate((l) => { localStorage.setItem("nitaq-lang", l); }, lang);
  await p.reload();
  await settle(p, 900);
  await shot(p, `${tag}-1-check`);
  await p.getByRole("button", {name: lang === "ar" ? "وورد فيه نص أبيض" : "Word file with white text"}).click();
  await p.waitForSelector(".verdict", {timeout: 15000});
  await settle(p, 1100);
  await shot(p, `${tag}-2-result`);
  await shot(p, `${tag}-2-result-full`, true);
  await p.getByRole("button", {name: lang === "ar" ? "المخفي" : "Hidden", exact: true}).click();
  await settle(p, 400);
  await p.locator(".xray").scrollIntoViewIfNeeded();
  await shot(p, `${tag}-3-xray-hidden`);
  await p.getByRole("button", {name: lang === "ar" ? "افحص حاجة تانية" : "Check something else"}).click();
  await settle(p, 500);
  await p.getByRole("button", {name: lang === "ar" ? "إيميل مشبوه" : "Suspicious e-mail"}).click();
  await p.waitForSelector(".verdict", {timeout: 15000});
  await settle(p, 1000);
  await shot(p, `${tag}-4-email`, true);
  for (const [r, n] of [["learn", "5-learn"], ["computer", "6-computer"], ["about", "7-about"]]) {
    await p.goto(base + "#" + r);
    await settle(p, 900);
    await shot(p, `${tag}-${n}`);
  }
}

await session("iphone-ar", {...devices["iPhone 13"]}, (p) => tour(p, "iphone-ar", "ar"));
await session("pixel-en", {...devices["Pixel 7"]}, (p) => tour(p, "pixel-en", "en"));
await session("iphone-dark", {...devices["iPhone 13"], colorScheme: "dark"}, async (p) => {
  await p.goto(base + "#check"); await settle(p, 900); await shot(p, "iphone-dark-1-check");
  await p.getByRole("button", {name: "صفحة ويب"}).click();
  await p.waitForSelector(".verdict"); await settle(p, 1000); await shot(p, "iphone-dark-2-page", true);
});
await session("desktop", {viewport: {width: 1440, height: 900}, deviceScaleFactor: 1}, async (p) => {
  await p.goto(base + "#check"); await settle(p, 900); await shot(p, "desktop-1-check");
  await p.getByRole("button", {name: "وورد فيه نص أبيض"}).click();
  await p.waitForSelector(".verdict"); await settle(p, 1100); await shot(p, "desktop-2-result"); await shot(p, "desktop-2-result-full", true);
  await p.goto(base + "#learn"); await settle(p, 900); await shot(p, "desktop-3-learn", true);
});
await b.close();
if (errors.length) { console.log("CONSOLE ERRORS:\n" + errors.join("\n")); process.exit(1); }
console.log("no console errors");
