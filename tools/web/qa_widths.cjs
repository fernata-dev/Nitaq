// Layout and loading check for the site (AR/EN) and the app: 7 widths, no horizontal overflow, no
// console errors, brand font loaded — and inside a sandboxed frame (opaque origin), the way embedded
// previews show pages. usage: python tools/site/build_site.py --out _site; serve _site on BASE;
//   node tools/web/qa_widths.cjs BASE      (e.g. http://127.0.0.1:8000/)
const {chromium} = require("playwright");
(async () => {
  const base = process.argv[2];
  const b = await chromium.launch(); const problems = [];
  const pages = [["site-ar", "index.html"], ["site-en", "en/index.html"], ["app", "app/index.html"]];
  for (const w of [320, 375, 414, 768, 1024, 1440, 1920]) for (const [tag, path] of pages) {
    const c = await b.newContext({viewport: {width: w, height: 900}}); const p = await c.newPage();
    p.on("pageerror", (e) => problems.push(`${tag}@${w}: ${e.message}`));
    p.on("console", (m) => { if (m.type() === "error") problems.push(`${tag}@${w}: ${m.text().slice(0, 120)}`); });
    await p.goto(base + path); await p.waitForTimeout(350);
    const r = await p.evaluate(() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
      font: document.fonts.check('700 20px "Plex Arabic"', "نِطاق")}));
    if (r.sw > r.cw) problems.push(`${tag}@${w}: horizontal overflow ${r.sw} > ${r.cw}`);
    if (!r.font) problems.push(`${tag}@${w}: brand font not loaded`);
    await c.close();
  }
  for (const [tag, path, probe] of [["site", "index.html", ".scn"], ["app", "app/index.html", ".drop"]]) {
    const c = await b.newContext({viewport: {width: 1280, height: 800}}); const p = await c.newPage();
    await p.setContent(`<iframe src="${base + path}" sandbox="allow-scripts" style="width:1200px;height:760px;border:0"></iframe>`);
    await p.waitForTimeout(1500);
    const fr = p.frames()[1];
    const n = await fr.locator(probe).count(), font = await fr.evaluate(() => document.fonts.check('700 20px "Plex Arabic"', "نِطاق"));
    if (!n) problems.push(`sandboxed ${tag}: did not render (${probe} missing)`);
    if (!font) problems.push(`sandboxed ${tag}: brand font not loaded`);
    await c.close();
  }
  await b.close();
  console.log(problems.length ? problems.join("\n") : "OK: 7 widths x 3 pages + sandboxed frames: no overflow, no errors, font loaded");
  process.exit(problems.length ? 1 : 0);
})();
