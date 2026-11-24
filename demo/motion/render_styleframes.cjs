// Render the style frames (demo/motion/styleframes.html ?f=1..6) to demo/motion/styleframes/SF-0N.jpg.
// usage: node demo/motion/render_styleframes.cjs   (needs `playwright` on NODE_PATH)
const {chromium} = require("playwright");
const path = require("path"), fs = require("fs");
(async () => {
  const out = path.join(__dirname, "styleframes"); fs.mkdirSync(out, {recursive: true});
  const b = await chromium.launch();
  const p = await b.newPage({viewport: {width: 1920, height: 1080}});
  for (let f = 1; f <= 6; f++) {
    await p.goto("file://" + path.join(__dirname, "styleframes.html") + "?f=" + f);
    await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(300);
    await p.screenshot({path: path.join(out, `SF-0${f}.jpg`), type: "jpeg", quality: 88});
  }
  await b.close(); console.log("6 style frames ->", out);
})();
