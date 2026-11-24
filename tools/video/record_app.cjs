// Record the app scenes of the demo video from the REAL app (`nitaq ui` on a fake HOME) with
// Playwright's Chromium. Frames come from the DevTools screencast (what is really painted, at full
// quality); each scene becomes one MP4 at 30 fps. A drawn cursor shows where the clicks happen; it is
// the only thing added to the page.
//
//   node tools/video/record_app.cjs OUTDIR APP_URL
//      APP_URL  the link `nitaq ui --no-browser` prints (with its #token)
const {chromium} = require("playwright");
const {spawnSync} = require("child_process");
const fs = require("fs");
const path = require("path");

const [OUT0, URL] = process.argv.slice(2);
const OUT = path.resolve(OUT0);
const W = 1618, H = 838, FPS = 30;          // the hole of the window frame in stage.html
fs.mkdirSync(OUT, {recursive: true});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const CURSOR = `
#vc{position:fixed;left:1400px;top:700px;width:30px;height:30px;z-index:2147483647;pointer-events:none}
#vc svg{position:absolute;left:0;top:0;width:30px;height:30px;filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}
#vc i{position:absolute;border-radius:50%;background:rgba(94,211,180,.55);width:0;height:0;left:0;top:0}
*:focus{outline:none !important}`;

async function addCursor(p) {
  await p.evaluate((css) => {
    if (document.getElementById("vc")) return;
    const st = document.createElement("style"); st.textContent = css; document.head.append(st);
    const c = document.createElement("div"); c.id = "vc";
    c.innerHTML = '<i></i><svg viewBox="0 0 24 24"><path d="M4 2l16 9-7 2-3 7z" fill="#fff" stroke="#0C3B3C" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.body.append(c);
  }, CURSOR);
}
async function moveTo(p, loc) {
  await loc.scrollIntoViewIfNeeded();
  const bx = await loc.boundingBox();
  const x = bx.x + bx.width / 2, y = bx.y + bx.height / 2;
  await p.evaluate(([x, y]) => new Promise((done) => {
    const c = document.getElementById("vc"), x0 = parseFloat(c.style.left) || 1400, y0 = parseFloat(c.style.top) || 700, t0 = performance.now();
    const ease = (u) => (u < .5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
    (function step(now) { const u = Math.min(1, (now - t0) / 700), e = ease(u);
      c.style.left = (x0 + (x - x0) * e) + "px"; c.style.top = (y0 + (y - y0) * e) + "px";
      if (u < 1) requestAnimationFrame(step); else done(); })(t0);
  }), [x, y]);
  await sleep(150);
}
async function click(p, loc) {
  await moveTo(p, loc);
  await p.evaluate(() => new Promise((done) => {
    const r = document.querySelector("#vc i"), t0 = performance.now();
    (function step(now) { const u = Math.min(1, (now - t0) / 450), d = 10 + 54 * u;
      r.style.width = r.style.height = d + "px"; r.style.left = r.style.top = (-d / 2) + "px"; r.style.opacity = String(1 - u);
      if (u < 1) requestAnimationFrame(step); else done(); })(t0);
    setTimeout(done, 600);
  }));
  await loc.click();
}
async function scroll(p, dy, ms) {             // smooth wheel scrolling over `ms`
  const steps = Math.max(1, Math.round(ms / 40));
  for (let i = 0; i < steps; i++) { await p.mouse.wheel(0, dy / steps); await sleep(40); }
}

async function scene(p, cdp, id, body) {
  const dir = path.join(OUT, id + ".frames");
  fs.rmSync(dir, {recursive: true, force: true}); fs.mkdirSync(dir);
  const frames = [];
  const onFrame = async (f) => {
    const file = path.join(dir, `f${String(frames.length).padStart(5, "0")}.jpg`);
    fs.writeFileSync(file, Buffer.from(f.data, "base64"));
    frames.push([file, f.metadata.timestamp]);
    try { await cdp.send("Page.screencastFrameAck", {sessionId: f.sessionId}); } catch {}
  };
  cdp.on("Page.screencastFrame", onFrame);
  await cdp.send("Page.startScreencast", {format: "jpeg", quality: 95, maxWidth: W, maxHeight: H, everyNthFrame: 1});
  const t0 = Date.now() / 1000;
  await p.evaluate(() => { const c = document.getElementById("vc"); if (c) c.style.opacity = "1"; });
  await body();
  const t1 = Date.now() / 1000;
  await cdp.send("Page.stopScreencast");
  cdp.off("Page.screencastFrame", onFrame);
  // constant 30 fps: each frame lasts until the next one; the last until the end of the scene
  const list = [];
  frames.forEach(([file, ts], i) => {
    const start = i === 0 ? t0 : ts, end = i + 1 < frames.length ? frames[i + 1][1] : t1;
    list.push(`file '${file}'`, `duration ${Math.max(0.001, end - start).toFixed(4)}`);
  });
  list.push(`file '${frames[frames.length - 1][0]}'`);
  fs.writeFileSync(path.join(dir, "list.txt"), list.join("\n") + "\n");
  const r = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", path.join(dir, "list.txt"),
    "-vf", `fps=${FPS},scale=${W}:${H}:flags=lanczos,format=yuv420p`, "-t", (t1 - t0).toFixed(3),   // concat repeats the last frame: cut at the real length
    "-c:v", "libx264", "-preset", "medium", "-crf", "14",
    path.join(OUT, id + ".app.mp4")], {stdio: "inherit"});
  if (r.status !== 0) throw new Error("ffmpeg failed for " + id);
  console.log(id, `${frames.length} frames, ${(t1 - t0).toFixed(1)} s`);
}

(async () => {
  const b = await chromium.launch();
  // bypassCSP: the app forbids inline styles; the drawn cursor needs one (recording browser only)
  const ctx = await b.newContext({viewport: {width: W, height: H}, deviceScaleFactor: 1, locale: "ar-EG", bypassCSP: true});
  const p = await ctx.newPage();
  const cdp = await ctx.newCDPSession(p);
  const base = URL.split("#")[0];
  await p.goto(URL); await sleep(1500);                       // the token is read from the link once
  await p.goto(base + "#check"); await sleep(1500);
  await addCursor(p);
  await p.evaluate(() => document.activeElement && document.activeElement.blur());
  const btn = (name) => p.getByRole("button", {name, exact: true});
  const again = async () => { await p.evaluate(() => window.scrollTo(0, 0)); await btn("افحص حاجة تانية").first().click(); await sleep(900);
    await p.evaluate(() => document.activeElement && document.activeElement.blur()); };

  await scene(p, cdp, "s11_app_home", async () => {
    await sleep(1600);
    await moveTo(p, p.locator(".drop h2"));
    await sleep(900);
    await moveTo(p, btn("وورد فيه نص أبيض"));
    await sleep(700);
    await moveTo(p, btn("حروف مخفية"));
    await sleep(1300);
  });
  await scene(p, cdp, "s12_app_email", async () => {
    await click(p, btn("إيميل مشبوه"));
    await sleep(2600);
    await moveTo(p, p.locator(".xray"));
    await scroll(p, 620, 2600);
    await sleep(2200);
    await scroll(p, 760, 2600);
    await sleep(2400);
  });
  await again();
  await scene(p, cdp, "s13_app_docx", async () => {
    await sleep(500);
    await click(p, btn("وورد فيه نص أبيض"));
    await sleep(2600);
    await click(p, btn("المخفي"));
    await sleep(2200);
    await scroll(p, 260, 1500);
    await sleep(2600);
  });
  await again();
  await scene(p, cdp, "s14_app_hidden", async () => {
    await sleep(500);
    await click(p, btn("حروف مخفية"));
    await sleep(3200);
    await scroll(p, 420, 2200);
    await sleep(2800);
  });
  await p.evaluate(() => window.scrollTo(0, 0));
  await scene(p, cdp, "s15_app_computer", async () => {
    await sleep(400);
    await click(p, p.getByRole("link", {name: "جهازي"}).or(p.getByRole("button", {name: "جهازي"})).first());
    await sleep(2600);
    await scroll(p, 420, 2000);
    await sleep(1600);
    await p.evaluate(() => window.scrollTo({top: 0, behavior: "smooth"}));
    await sleep(900);
    await click(p, btn("الحماية"));
    await sleep(1800);
    const prev = btn("عاين التغييرات");
    if (await prev.count()) { await click(p, prev.first()); await sleep(2400); await scroll(p, 520, 2400); }
    await sleep(2600);
  });
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
