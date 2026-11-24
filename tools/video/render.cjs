// Render the stage scenes (title, cards, terminal recordings, QR) of the demo video frame by frame
// at 30 fps with Playwright's Chromium, piping JPEG frames into ffmpeg (one MP4 per scene), and the
// static backgrounds (frame + caption) of the app scenes as PNG.
//
//   node tools/video/render.cjs OUTDIR CASTDIR QR_URL [scene-id ...]
//
// Needs the `playwright` and `qrcode` packages (NODE_PATH) and ffmpeg on PATH.
const {chromium} = require("playwright");
const QRCode = require("qrcode");
const {spawn} = require("child_process");
const fs = require("fs");
const path = require("path");

const [OUT, CASTS, QR_URL, ...ONLY] = process.argv.slice(2);
const CFG = JSON.parse(fs.readFileSync(path.join(__dirname, "scenes.json"), "utf-8"));
const FPS = CFG.fps;
fs.mkdirSync(OUT, {recursive: true});

function encoder(file) {
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-",
    "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p", "-r", String(FPS), file], {stdio: ["pipe", "inherit", "inherit"]});
  const done = new Promise((res, rej) => ff.on("close", (c) => (c === 0 ? res() : rej(new Error("ffmpeg " + c)))));
  const write = (buf) => new Promise((res) => (ff.stdin.write(buf) ? res() : ff.stdin.once("drain", res)));
  return {write, end: async () => { ff.stdin.end(); await done; }};
}

(async () => {
  const b = await chromium.launch();
  const page = await b.newPage({viewport: {width: 1920, height: 1080}, deviceScaleFactor: 1});
  for (const sc of CFG.scenes) {
    if (ONLY.length && !ONLY.includes(sc.id)) continue;
    const scene = {...sc};
    if (scene.kind === "term") scene.cast = JSON.parse(fs.readFileSync(path.join(CASTS, `${sc.cast}.cast.json`), "utf-8"));
    if (scene.kind === "qr") {
      scene.url = QR_URL;
      scene.qr_svg = await QRCode.toString(QR_URL, {type: "svg", margin: 0, errorCorrectionLevel: "M", color: {dark: "#0C3B3C", light: "#ffffff"}});
    }
    await page.goto("file://" + path.join(__dirname, "stage.html"));
    await page.evaluate(() => document.fonts.ready);
    const dur = await page.evaluate((s) => window.setup(s), scene);
    if (scene.kind === "app") {                                   // static background for an app scene
      await page.evaluate(() => window.setTime(3));
      await page.screenshot({path: path.join(OUT, `${sc.id}.bg.png`)});
      console.log(sc.id, "background");
      continue;
    }
    const n = Math.round(dur * FPS);
    const enc = encoder(path.join(OUT, `${sc.id}.mp4`));
    let buf = null;
    for (let f = 0; f < n; f++) {
      const changed = await page.evaluate((t) => window.setTime(t), f / FPS);
      if (changed || !buf) buf = await page.screenshot({type: "jpeg", quality: 94});
      await enc.write(buf);
    }
    await enc.end();
    console.log(sc.id, `${n} frames, ${(n / FPS).toFixed(1)} s`);
  }
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
