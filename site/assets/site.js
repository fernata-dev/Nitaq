// Nitaq website behaviour (classic script: works in sandboxed previews and from file://). Text from data is inserted with
// textContent only. No network calls, no tracking. The decisions shown are computed at build time (demo-data.js).
(function () {
"use strict";
const DEMO = self.NITAQ_DEMO;
const lang = document.documentElement.lang === "ar" ? "ar" : "en";
const T = DEMO.text[lang];
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const rtl = document.documentElement.dir === "rtl";
document.documentElement.classList.add("js");

function h(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) n.append(c.nodeType ? c : document.createTextNode(String(c)));
  return n;
}
function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg; el.classList.add("show");
  clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.remove("show"), 2200);
}
function stampDown(el, board) {
  if (!el) return;
  el.classList.remove("down");
  void el.offsetWidth;                                    // restart the animation
  el.classList.add("down");
  if (board && !reduce) { board.classList.remove("thud"); void board.offsetWidth; board.classList.add("thud"); }
}
// Latin runs (commands, paths, URLs, e-mail addresses) inside Arabic text get their own LTR island, so the
// browser's bidi algorithm cannot reorder "curl -d @notes.txt host" around the Arabic words.
const LATIN_RUN = /[A-Za-z0-9~@$(\[{"'<][A-Za-z0-9~@$._:/\\'"=+\-#%&?*|<>{}\[\](),;! ]*[A-Za-z0-9~@$._:/'">)\]}]|[A-Za-z0-9]/g;
function bidiNodes(text) {
  if (!/[\u0600-\u06FF]/.test(text)) return [text];
  const out = []; let last = 0;
  for (const m of text.matchAll(LATIN_RUN)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(h("bdi", {dir: "ltr", text: m[0]}));
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
function setText(el, text) { el.textContent = ""; el.append(...bidiNodes(text)); }
self.NitaqUI = {h, toast, stampDown, T, lang, reduce, setText};

// ------------------------------------------------------------ copy buttons (also for ones added later)
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-copy-target]");
  if (!btn) return;
  const holder = btn.closest("[data-copy]") || btn.parentElement.querySelector("[data-copy]");
  const text = holder ? holder.getAttribute("data-copy") : "";
  try { await navigator.clipboard.writeText(text); }
  catch (err) { const ta = h("textarea", {}); ta.value = text; document.body.append(ta); ta.select(); document.execCommand && document.execCommand("copy"); ta.remove(); }
  btn.textContent = btn.dataset.done; btn.classList.add("done");
  toast(btn.dataset.done);
  setTimeout(() => { btn.textContent = btn.dataset.label; btn.classList.remove("done"); }, 1800);
});

// ------------------------------------------------------------ index rail: the open tab follows the reader
const tabs = [...document.querySelectorAll(".tabs a")];
const byId = new Map(tabs.map((a) => [a.getAttribute("href").slice(1), a]));
if ("IntersectionObserver" in window) {
  const seen = new Map();
  const io = new IntersectionObserver((es) => {
    for (const e of es) seen.set(e.target.id, e.isIntersecting ? e.intersectionRatio : 0);
    let best = null, score = 0;
    for (const [id, r] of seen) if (r > score) { score = r; best = id; }
    if (!best) return;
    for (const a of tabs) a.removeAttribute("aria-current");
    const a = byId.get(best);
    if (a) { a.setAttribute("aria-current", "location"); if (matchMedia("(max-width: 900px)").matches) a.scrollIntoView({block: "nearest", inline: "nearest"}); }
  }, {threshold: [0, .15, .35, .6], rootMargin: "-20% 0px -45% 0px"});
  for (const id of byId.keys()) { const s = document.getElementById(id); if (s) io.observe(s); }
}

// ------------------------------------------------------------ OS tabs (arrow keys move between tabs)
const osTabs = [...document.querySelectorAll(".os-tabs [role=tab]")];
function selectOs(tab) {
  for (const t of osTabs) {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
  }
}
osTabs.forEach((t, i) => {
  t.addEventListener("click", () => selectOs(t));
  t.addEventListener("keydown", (e) => {
    const step = {ArrowRight: 1, ArrowLeft: -1}[e.key];
    if (!step) return;
    const next = osTabs[(i + (rtl ? -step : step) + osTabs.length) % osTabs.length];
    selectOs(next); next.focus(); e.preventDefault();
  });
});
const ua = navigator.userAgent;
const guess = /Windows/.test(ua) ? "win" : /Mac OS X/.test(ua) && !/iPhone|iPad/.test(ua) ? "mac" : /Ubuntu|Debian/.test(ua) ? "debian" : null;
if (guess && document.getElementById("tab-" + guess)) selectOs(document.getElementById("tab-" + guess));

// ------------------------------------------------------------ desktop downloads: the visitor's OS first
const dl = document.getElementById("dl-rows");
if (dl) {
  const os = /Windows/.test(ua) ? "win" : /Mac OS X|Macintosh/.test(ua) && !/iPhone|iPad/.test(ua) ? "mac" : /Linux/.test(ua) && !/Android/.test(ua) ? "linux" : null;
  const row = os && dl.querySelector(`li[data-os="${os}"]`);
  if (row) { row.classList.add("mine"); dl.prepend(row); }
}

// ------------------------------------------------------------ shared case state (hero board + cases section)
const SC = DEMO.data.scenarios;
const state = {cur: 0, variant: 0};
const listeners = [];
function select(i, v, from) {
  const changed = i !== state.cur;
  state.cur = i; state.variant = v;
  for (const fn of listeners) fn(changed, from);
}
function target(sc, d) { return d.hosts.join(", ") || Object.values(sc.call.args)[0]; }

// ------------------------------------------------------------ cases section
const list = document.getElementById("scn-list");
const stage = document.getElementById("demo-stage");
function verdictStamp(ok) {
  return h("div", {class: "stamp" + (ok ? " ok" : ""), "aria-hidden": "true"},
    h("b", {text: ok ? T.seq_ok : T.seq_no}), h("small", {text: ok ? T.seq_ok_sub : T.seq_no_sub}));
}
function renderStage(changed) {
  const sc = SC[state.cur], v = sc.variants[Math.min(state.variant, sc.variants.length - 1)], d = v.decision;
  stage.textContent = "";
  stage.setAttribute("aria-labelledby", "scn-" + sc.id);
  const vt = h("div", {class: "vtabs", role: "group", "aria-label": T.demo_lang},
    sc.variants.map((x, i) => h("button", {type: "button", "aria-pressed": String(i === state.variant), onclick: () => select(state.cur, i, "stage"), text: T["v_" + x.code]})));
  stage.append(h("div", {class: "stage-top"},
    h("div", {}, h("span", {class: "label", text: T.demo_lang + ":"}), vt),
    h("span", {class: "modechip", text: `${T.demo_mode}: ${T["mode_" + sc.mode]}`})));
  const s1 = h("div", {class: "st"}, h("h3", {text: T.demo_step1}),
    h("span", {class: "src-k", text: T["src_" + sc.source]}),
    h("p", {class: "said", dir: "auto"}, bidiNodes(v.text)),
    sc.source === "user" ? null : h("div", {class: "scanner"}, h("span", {text: T.demo_scanner + ":"}),
      h("span", {class: "pill " + (v.d2.flagged ? "ok" : "no"), text: v.d2.flagged ? T.demo_flagged : T.demo_missed}),
      h("span", {class: "pill ltr", text: `D2 ${v.d2.score}`})));
  const call = JSON.stringify({tool: sc.call.tool, args: sc.call.args}, null, 2);
  const s2 = h("div", {class: "st"}, h("h3", {text: T.demo_step2}), h("pre", {text: call}));
  const ok = d.allowed;
  const stamp = verdictStamp(ok);
  const verdict = h("div", {class: "verdict"}, stamp,
    h("p", {class: "sr-only", text: ok ? T.dec_allow : T.dec_block}),
    h("dl", {},
      h("dt", {text: T.demo_rule}), h("dd", {}, h("span", {text: T["rule_" + d.rule] || d.rule}), d.rule ? h("div", {}, h("code", {class: "ltr", text: d.rule})) : null),
      d.hosts.length ? [h("dt", {text: T.demo_hosts}), h("dd", {}, h("code", {class: "ltr", text: d.hosts.join(", ")}))] : null,
      d.detail ? [h("dt", {text: T.demo_detail}), h("dd", {}, h("code", {class: "ltr", text: d.detail}))] : null));
  const s3 = h("div", {class: "st"}, h("h3", {text: T.demo_step3}), verdict,
    sc.also ? h("p", {class: "also"}, T.demo_also + " ", h("code", {class: "ltr", text: `${sc.also.tool} ${sc.also.args.url || ""}`}), " → ",
      h("b", {text: sc.also.decision.allowed ? T.dec_allow : T.dec_block})) : null);
  stage.append(h("div", {class: "stage-flow"}, s1, s2, s3), h("p", {class: "stage-note", text: T.demo_scanner_note}));
  if (changed) stampDown(stamp); else stamp.style.opacity = ".94";
}
function renderList() {
  list.textContent = "";
  SC.forEach((sc, i) => {
    const allowed = sc.variants[0].decision.allowed;
    list.append(h("button", {class: "scn", type: "button", role: "tab", id: "scn-" + sc.id, "aria-selected": String(i === state.cur),
      "aria-controls": "demo-stage", tabindex: i === state.cur ? "0" : "-1",
      onclick: () => select(i, 0, "list"),
      onkeydown: (e) => {
        const flip = rtl ? -1 : 1;
        const step = {ArrowDown: 1, ArrowUp: -1, ArrowRight: flip, ArrowLeft: -flip}[e.key];
        if (!step) return;
        e.preventDefault();
        select((i + step + SC.length) % SC.length, 0, "list");
        document.getElementById("scn-" + SC[state.cur].id).focus();
      }}, h("i", {class: allowed ? "ok" : ""}), T["scn_" + sc.id]));
  });
}
if (list && stage) {
  listeners.push((changed) => { renderList(); renderStage(changed); });
  renderList(); renderStage(false);
}

// ------------------------------------------------------------ hero: the case board (title sequence + live controls)
const board = document.getElementById("board");
if (board) {
  const frames = [...board.querySelectorAll(".frame[data-scn]")];
  const ret = board.querySelector(".reticle");
  const grid = board.querySelector(".frames");
  const langs = document.getElementById("ic-langs");
  const said = document.getElementById("ic-said");
  const call = document.getElementById("ic-call");
  const stamp = document.getElementById("ic-stamp");
  const idx = (id) => SC.findIndex((s) => s.id === id);
  let typing = null, auto = !reduce, timer = null, visible = true;

  function aim(frame, lock) {
    const g = grid.getBoundingClientRect(), f = frame.getBoundingClientRect(), r = ret.getBoundingClientRect();
    const x = f.left - g.left + f.width / 2 - r.width / 2, y = f.top - g.top + f.height / 2 - r.height / 2;
    ret.style.setProperty("--rx", x + "px"); ret.style.setProperty("--ry", y + "px");
    ret.classList.add("on"); ret.classList.toggle("lock", !!lock);
  }
  function type(text, done) {
    clearInterval(typing);
    said.classList.add("typing");
    if (reduce) { setText(said, text); said.classList.remove("typing"); done && done(); return; }
    let n = 0; const chars = [...text], step = Math.max(1, Math.round(chars.length / 55));
    said.textContent = "";
    typing = setInterval(() => {
      n = Math.min(chars.length, n + step);
      setText(said, chars.slice(0, n).join(""));
      if (n >= chars.length) { clearInterval(typing); said.classList.remove("typing"); done && done(); }
    }, 28);
  }
  function show(changed) {
    const sc = SC[state.cur];
    const fr = frames.find((f) => f.dataset.scn === sc.id);
    for (const f of frames) { f.setAttribute("aria-selected", String(f === fr)); f.tabIndex = f === fr ? 0 : -1; }
    if (!fr) { ret.classList.remove("on"); }
    langs.textContent = "";
    sc.variants.forEach((x, i) => langs.append(h("button", {type: "button", "aria-pressed": String(i === state.variant), text: T["v_" + x.code],
      onclick: () => { stopAuto(); select(state.cur, i, "hero"); }})));
    const v = sc.variants[Math.min(state.variant, sc.variants.length - 1)], d = v.decision;
    call.textContent = `${sc.call.tool} → ${Object.values(sc.call.args)[0]}`;
    stamp.classList.toggle("ok", d.allowed);
    stamp.querySelector("b").textContent = d.allowed ? T.seq_ok : T.seq_no;
    stamp.querySelector("small").textContent = d.allowed ? T.seq_ok_sub : T.seq_no_sub;
    if (changed) { stamp.classList.remove("down"); stamp.style.opacity = "0"; }
    if (fr) aim(fr, false);
    type(v.text, () => {
      if (fr) aim(fr, !d.allowed);
      if (changed || stamp.style.opacity === "0") { stamp.style.opacity = ""; stampDown(stamp, board); }
    });
  }
  listeners.push((changed) => show(changed));

  frames.forEach((f, k) => {
    f.addEventListener("click", () => { stopAuto(); select(idx(f.dataset.scn), 0, "hero"); });
    f.addEventListener("keydown", (e) => {
      const flip = rtl ? -1 : 1;
      const step = {ArrowRight: flip, ArrowLeft: -flip, ArrowDown: 1, ArrowUp: -1}[e.key];
      if (!step) return;
      e.preventDefault(); stopAuto();
      const nf = frames[(k + step + frames.length) % frames.length];
      select(idx(nf.dataset.scn), 0, "hero"); nf.focus();
    });
  });
  board.addEventListener("focusin", stopAuto);
  board.addEventListener("pointerdown", stopAuto);

  // title sequence: every language of a case, then the next case
  const order = frames.map((f) => idx(f.dataset.scn)).filter((i) => i >= 0);
  function tick() {
    if (!auto) return;
    if (!document.hidden && visible) {
      const sc = SC[state.cur];
      if (state.variant + 1 < sc.variants.length && sc.variants.length > 1) select(state.cur, state.variant + 1, "auto");
      else select(order[(order.indexOf(state.cur) + 1) % order.length], 0, "auto");
    }
    timer = setTimeout(tick, 4200);
  }
  function stopAuto() { auto = false; clearTimeout(timer); }
  if ("IntersectionObserver" in window) new IntersectionObserver((es) => { visible = es[0].isIntersecting; }).observe(board);
  addEventListener("resize", () => { const fr = frames.find((f) => f.getAttribute("aria-selected") === "true"); if (fr) aim(fr, ret.classList.contains("lock")); });
  state.cur = order[0] ?? 0;
  if (list && stage) { renderList(); renderStage(false); }
  setTimeout(() => { show(true); if (auto) timer = setTimeout(tick, 5200); }, reduce ? 0 : 450);
}

// ------------------------------------------------------------ decision log (rows computed at build time, rotated)
const ledger = document.getElementById("ledger");
if (ledger && !reduce) {
  const lines = [];
  for (const sc of SC) for (const v of sc.variants) {
    const d = v.decision;
    lines.push([d.allowed, `${sc.call.tool} → ${target(sc, d)} · ${d.rule || "ok"} [${v.code}]`]);
  }
  let k = 7 % lines.length;
  setInterval(() => {
    if (document.hidden) return;
    const [ok, txt] = lines[k++ % lines.length];
    ledger.prepend(h("p", {class: (ok ? "ok" : "no") + " fresh"}, h("b", {text: ok ? "ALLOW" : "BLOCK"}), " " + txt));
    while (ledger.children.length > 8) ledger.lastElementChild.remove();
  }, 2600);
}

// ------------------------------------------------------------ film: chapters and timecode
const video = document.getElementById("film-video");
if (video) {
  const chapters = [...document.querySelectorAll("#chapters button")];
  const tc = document.getElementById("film-tc");
  const pad = (n) => String(Math.floor(n)).padStart(2, "0");
  // Static hosts (Cloudflare Pages, python -m http.server) do not answer byte ranges, and without them the browser
  // cannot seek at all. On the first play the film (about 12 MB, same origin) is loaded whole into memory and
  // played from there, so the timeline and the chapters can jump anywhere.
  let whole = null;
  const screen = video.closest(".screen");
  function loadWhole() {
    if (whole) return whole;
    const src = video.querySelector("source").src;
    screen.classList.add("loading");
    whole = fetch(src, {credentials: "same-origin"}).then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.blob();
    }).then((b) => new Promise((resolve) => {
      const keep = video.currentTime, playing = !video.paused;
      video.src = URL.createObjectURL(b);
      video.addEventListener("loadedmetadata", () => {
        video.currentTime = keep;
        if (playing) video.play().catch(() => {});
        screen.classList.remove("loading");
        resolve();
      }, {once: true});
    })).catch(() => { screen.classList.remove("loading"); whole = null; });
    return whole;
  }
  video.addEventListener("play", () => { loadWhole(); });
  const seek = (t) => {
    loadWhole().then(() => { video.currentTime = t; video.play().catch(() => {}); });
  };
  chapters.forEach((b) => b.addEventListener("click", () => seek(Number(b.dataset.t))));
  video.addEventListener("timeupdate", () => {
    const t = video.currentTime;
    tc.textContent = `${pad(t / 3600)}:${pad((t % 3600) / 60)}:${pad(t % 60)}`;
    let cur = chapters[0];
    for (const b of chapters) if (Number(b.dataset.t) <= t + .25) cur = b;
    for (const b of chapters) b.toggleAttribute("aria-current", b === cur);
  });
}

// ------------------------------------------------------------ stamps that land when they come into view
const late = [...document.querySelectorAll(".stamp.on-view")];
if ("IntersectionObserver" in window && late.length) {
  const io = new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting) { stampDown(e.target); io.unobserve(e.target); }
  }), {threshold: .6});
  for (const s of late) io.observe(s);
} else for (const s of late) s.classList.add("down");
})();
