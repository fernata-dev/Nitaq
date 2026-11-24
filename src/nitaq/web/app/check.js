// "Check" screen: pick / drop / paste, then the X-ray result.
import {copyText, explain, h, icon, seg, state, t, toast} from "./dom.js";

const SEV = {info: 0, low: 1, medium: 2, high: 3};
const EXAMPLES = [["ex_docx", "hidden.docx", "file"], ["ex_eml", "mail.eml", "mail"],
                  ["ex_html", "page.html", "globe"], ["ex_txt", "smuggle.txt", "paste"],
                  ["ex_skill1", "skill1.md", "file"], ["ex_skill2", "skill2.md", "file"]];
const MAX_SEGMENTS = 400, MAX_SEG_CHARS = 1600, MAX_FINDINGS = 60;

let worker = null, seq = 0;
const pending = new Map();
let last = null;                 // {rep} kept while switching tabs
let xmode = "all";

function getWorker() {
  if (worker === null) {
    try {
      worker = new Worker(new URL("../engine/worker.js", import.meta.url), {type: "module"});
      worker.onmessage = (e) => { const p = pending.get(e.data.id); if (p) { pending.delete(e.data.id); e.data.error ? p.reject(new Error(e.data.error)) : p.resolve(e.data.rep); } };
      worker.onerror = () => { for (const p of pending.values()) p.reject(new Error("worker")); pending.clear(); worker = false; };
    } catch (e) { worker = false; }
  }
  return worker;
}

async function runCheck(input) {
  const w = getWorker();
  if (w) {
    try {
      return await new Promise((resolve, reject) => {
        const id = ++seq;
        pending.set(id, {resolve, reject});
        w.postMessage({id, name: input.name, text: input.text, bytes: input.bytes});     // copied, not transferred
      });
    } catch (e) {
      if (e.message !== "worker") throw e;           // module workers unsupported: fall back to this thread
    }
  }
  const eng = await import("../engine/check.js");
  return input.bytes ? eng.checkFile(input.name, input.bytes) : eng.checkText(input.text, input.name);
}

export function checkView(root) {
  const view = h("div", {class: "view"});
  root.append(view);
  if (last) { renderResult(view, last); return; }
  renderStart(view);
}

function renderStart(view) {
  view.textContent = "";
  const fileInput = h("input", {type: "file", class: "sr", tabindex: "-1", "aria-hidden": "true",
    accept: ".docx,.eml,.html,.htm,.txt,.md,.json,.yaml,.yml,.mht,.pdf,message/rfc822,text/*,application/vnd.openxmlformats-officedocument.wordprocessingml.document"});
  const ta = h("textarea", {class: "in", placeholder: t("paste_ph"), "aria-label": t("paste_toggle"), spellcheck: "false"});
  const pasteBox = h("div", {class: "pastebox"}, h("div", {},
    ta, h("div", {class: "row mt"}, h("button", {class: "btn", type: "button", onclick: () => {
      if (!ta.value.trim()) { ta.focus(); return; }
      go(view, {text: ta.value, name: state.lang === "ar" ? "نص ملصوق" : "pasted text"});
    }}, icon("scan"), t("run")))));
  const pasteBtn = h("button", {class: "btn line wide", type: "button", "aria-expanded": "false", onclick: () => {
    const open = !pasteBox.classList.contains("open");
    pasteBox.classList.toggle("open", open);
    pasteBtn.setAttribute("aria-expanded", String(open));
    if (open) setTimeout(() => ta.focus(), 250);
  }}, icon("paste"), t("paste_toggle"));
  fileInput.addEventListener("change", () => { if (fileInput.files[0]) readFile(view, fileInput.files[0]); });

  const drop = h("section", {class: "drop", "aria-label": t("drop_title")},
    h("div", {class: "glyph"}, icon("upload")),
    h("h2", {text: t("drop_title")}),
    h("p", {class: "muted small", text: t("drop_sub")}),
    h("div", {class: "formats"}, [".docx", ".eml", ".html", ".txt", ".md", "SKILL.md"].map((f) => h("span", {class: "tag mute ltr", text: f}))),
    h("div", {class: "row mt"}, h("button", {class: "btn big wide", type: "button", onclick: () => fileInput.click()}, icon("file"), t("choose"))),
    fileInput,
    h("div", {class: "or", text: t("or")}),
    pasteBtn, pasteBox,
    h("div", {class: "examples"}, h("p", {class: "muted small", text: t("examples")}),
      h("div", {class: "chips"}, EXAMPLES.map(([k, url, ic]) => h("button", {class: "chip", type: "button", onclick: () => example(view, url)}, icon(ic), t(k))))));

  const dragOn = (e) => { if (e.dataTransfer && [...e.dataTransfer.types].includes("Files")) { e.preventDefault(); drop.classList.add("over"); } };
  view.addEventListener("dragover", dragOn);
  view.addEventListener("dragleave", (e) => { if (!view.contains(e.relatedTarget)) drop.classList.remove("over"); });
  view.addEventListener("drop", (e) => {
    e.preventDefault(); drop.classList.remove("over");
    const f = e.dataTransfer && e.dataTransfer.files[0];
    if (f) readFile(view, f);
  });

  view.append(h("div", {class: "hero"},
    h("div", {class: "head"},
      h("span", {class: "eyebrow"}, icon("lock"), t("eyebrow")),
      h("h1", {}, t("hero_1"), h("br"), h("em", {text: t("hero_2")}))),
    drop,
    h("div", {class: "more"},
      h("p", {class: "lead", text: t("hero_lead")}),
      h("div", {class: "trust"},
        h("span", {}, icon("phone"), t("trust_local")), h("span", {}, icon("wifi_off"), t("trust_offline")),
        h("span", {}, icon("cloud_off"), t("trust_nothing"))))));
}

async function readFile(view, f) {
  const buf = new Uint8Array(await f.arrayBuffer());
  go(view, {bytes: buf, name: f.name, size: f.size});
}

async function example(view, name) {
  try {
    const {default: SAMPLES} = await import("../samples/samples.js");     // bundled: works on any static host
    const bin = atob(SAMPLES[name]);
    const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
    go(view, {bytes, name, size: bytes.length});
  } catch (e) { toast(`${t("error")}: ${e.message}`, true); }
}

async function go(view, input) {
  view.textContent = "";
  view.append(h("div", {class: "card scanning", role: "status", "aria-live": "polite"},
    h("div", {class: "glyph"}, icon("scan")),
    h("div", {class: "grow"}, h("b", {text: t("scanning")}), h("div", {class: "muted small", text: t("scanning_sub")}),
      h("div", {class: "progress"}, h("i")))));
  const started = performance.now();
  try {
    const rep = await runCheck(input);
    const wait = Math.max(0, 450 - (performance.now() - started));        // let the progress read, not flash
    await new Promise((r) => setTimeout(r, wait));
    last = {rep, size: input.size ?? (input.text ? new TextEncoder().encode(input.text).length : 0)};
    xmode = "all";
    renderResult(view, last);
    window.scrollTo({top: 0, behavior: "smooth"});
  } catch (e) {
    toast(`${t("error")}: ${e.message}`, true);
    renderStart(view);
  }
}

const reasonLabel = (r) => t("r_" + r);
function whereLabel(w) {
  if (!w) return "";
  return w.split(" › ").map((part) => {
    if (part.startsWith("attachment:")) return `${t("w_attachment")}: ${part.slice(11)}`;
    if (part.startsWith("line ")) return `${t("w_line")} ${part.slice(5)}`;
    return t("w_" + part) !== "w_" + part ? t("w_" + part) : part;
  }).join(" › ");
}
const fmtSize = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n > 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`);

function renderResult(view, {rep, size}) {
  view.textContent = "";
  const v = rep.verdict;
  const vIcon = {danger: "bad", warn: "warn", clear: "ok", unsupported: "info"}[v];
  const desc = v === "unsupported" ? t("u_" + (rep.reason || "unsupported")) : t(`v_${v}_d`);
  const segs = rep.segments || [];
  const instr = segs.filter((s) => s.seen !== "visible" && s.instruction).length;
  const res = h("div", {class: "result"});

  res.append(h("section", {class: `verdict ${v}`, role: "status", "aria-live": "polite"},
    h("div", {class: "vi"}, icon(vIcon)),
    h("div", {}, h("h2", {text: t("v_" + v)}), h("p", {text: desc})),
    h("div", {class: "file"}, icon("file"), h("bdi", {text: rep.name || ""}), rep.kind ? h("span", {class: "tag mute ltr", text: rep.kind}) : null,
      size ? h("span", {class: "ltr", text: fmtSize(size)}) : null)));

  if (v === "unsupported") {
    res.append(actions(view, rep));
    view.append(res);
    return;
  }

  if (rep.headers && Object.keys(rep.headers).length) {
    const hd = rep.headers;
    res.append(h("div", {class: "card"}, h("div", {class: "stack small"},
      hd.from ? h("div", {}, h("b", {text: t("from") + ": "}), h("bdi", {text: hd.from})) : null,
      hd["reply-to"] ? h("div", {}, h("b", {text: t("reply_to") + ": "}), h("bdi", {text: hd["reply-to"]})) : null,
      hd.subject ? h("div", {}, h("b", {text: t("subject") + ": "}), h("bdi", {text: hd.subject})) : null,
      rep.attachments && rep.attachments.length ? h("div", {}, h("b", {text: t("attachments") + ": "}),
        rep.attachments.map((a, i) => [i ? " · " : "", h("bdi", {text: `${a.name} (${fmtSize(a.size)})`})])) : null)));
  }

  const main = h("div", {class: "stack"}), side = h("aside", {class: "side"});
  side.append(h("div", {class: "stats"},
    h("div", {class: "stat amber"}, h("b", {text: rep.counts.hidden}), h("span", {text: t("st_hidden")})),
    h("div", {class: "stat bad"}, h("b", {text: instr}), h("span", {text: t("st_instr")})),
    h("div", {class: "stat"}, h("b", {text: rep.counts.unseen}), h("span", {text: t("st_unseen")}))));

  if (rep.notes && rep.notes.length) {
    side.append(h("div", {class: "card soft"}, h("ul", {class: "plain small"}, [...new Set(rep.notes)].map((n) => h("li", {text: t("n_" + n)})))));
  }

  // X-ray
  const paper = h("div", {class: "paper reveal"});
  const applyMode = () => {
    paper.classList.toggle("only-hidden", xmode === "hidden");
    paper.classList.toggle("reader", xmode === "reader");
  };
  const shown = segs.slice(0, MAX_SEGMENTS);
  if (!segs.length || segs.every((s) => !s.text.trim())) paper.append(h("div", {class: "empty", text: t("no_text")}));
  appendFolded(paper, shown);
  setTimeout(() => paper.classList.remove("reveal"), 1400 + 140 * Math.min(12, shown.filter((s) => s.seen === "hidden").length));
  if (segs.length > MAX_SEGMENTS) {
    const more = h("button", {class: "btn line mt", type: "button", onclick: () => { more.remove(); appendFolded(paper, segs.slice(MAX_SEGMENTS)); }},
      `+ ${segs.length - MAX_SEGMENTS}`);
    paper.append(more);
  }
  applyMode();
  main.append(h("section", {class: "xray"},
    h("header", {}, h("h3", {}, icon("xray"), t("xray")),
      seg([["all", t("x_all")], ["hidden", t("x_hidden")], ["reader", t("x_reader")]], () => xmode, (m) => { xmode = m; applyMode(); }, t("xray"))),
    paper,
    h("div", {class: "legend"},
      h("span", {}, h("i", {class: "lh"}), t("lg_hidden")), h("span", {}, h("i", {class: "lu"}), t("lg_unseen")),
      h("span", {}, h("i", {class: "li"}), t("lg_instr")))));

  // findings
  const fs = (rep.findings || []).filter((f) => f.rule !== "external_address").sort((a, b) => SEV[b.severity] - SEV[a.severity]);
  const addrs = rep.destinations || [];
  const list = h("div", {});
  if (!fs.length) list.append(h("p", {class: "muted", text: t("no_findings")}));
  const groups = new Map();                       // one card per kind of finding, worst first
  for (const f of fs) {
    const g = groups.get(f.rule) || {rule: f.rule, severity: f.severity, items: []};
    if (SEV[f.severity] > SEV[g.severity]) g.severity = f.severity;
    g.items.push(f);
    groups.set(f.rule, g);
  }
  const ordered = [...groups.values()].sort((a, b) => SEV[b.severity] - SEV[a.severity] || b.items.length - a.items.length);
  for (const g of ordered.slice(0, MAX_FINDINGS)) list.append(findingNode(g, segs));
  main.append(h("section", {class: "card pad-l"}, h("h2", {text: t("findings")}), list,
    addrs.length ? h("div", {class: "mt"}, h("p", {class: "small muted", text: explain("external_address").text}),
      h("div", {class: "chips"}, addrs.slice(0, 20).map((a) => h("span", {class: "tag info ltr", text: a})))) : null));

  // what to do
  side.append(h("section", {class: "card pad-l"}, h("h2", {text: t("todo")}),
    h("ol", {class: "todo"}, t("todo_" + v).map((x) => h("li", {text: x})))));
  side.append(actions(view, rep));
  side.append(h("div", {class: "honest"}, icon("lock"), h("span", {text: t("note_local")})));
  res.append(h("div", {class: "rgrid"}, main, side));
  view.append(res);
}

// Runs of more than 4 visible paragraphs fold to their first 2 and last 1: the X-ray stays about
// what is hidden, and the page never needs a scroll area inside it.
function appendFolded(paper, list) {
  let i = 0, hiddenIndex = 0;
  while (i < list.length) {
    if (list[i].seen !== "visible") { paper.append(segmentNode(list[i], hiddenIndex++)); i++; continue; }
    let j = i;
    while (j < list.length && list[j].seen === "visible") j++;
    const run = list.slice(i, j);
    if (run.length <= 4) run.forEach((s) => paper.append(segmentNode(s)));
    else {
      run.slice(0, 2).forEach((s) => paper.append(segmentNode(s)));
      const rest = run.slice(2, -1);
      const tail = segmentNode(run[run.length - 1]);
      const fold = h("button", {class: "fold", type: "button", onclick: () => {
        const frag = document.createDocumentFragment();
        rest.forEach((s) => frag.append(segmentNode(s)));
        fold.replaceWith(frag);
      }}, icon("chev"), `${rest.length} ${t("more_paras")}`);
      paper.append(fold, tail);
    }
    i = j;
  }
}

function segmentNode(s, order = 0) {
  const cls = `sg ${s.seen}${s.seen !== "visible" && s.instruction ? " instr" : ""}`;
  const node = h("div", {class: cls});
  if (s.seen === "hidden") node.style.setProperty("--i", String(Math.min(order, 12)));
  const reasons = [...(s.hidden || []), ...(s.carriers || [])];
  if (s.seen !== "visible" || reasons.length) {
    node.append(h("div", {class: "meta"},
      reasons.length ? h("span", {class: "why", text: [...new Set(reasons.map(reasonLabel))].join(" · ")}) : null,
      s.where ? h("span", {class: "at", text: whereLabel(s.where)}) : null,
      s.seen !== "visible" && s.instruction ? h("span", {class: "ord"}, icon("warn"), t("instr_tag")) : null));
  }
  const text = s.text.length > MAX_SEG_CHARS ? s.text.slice(0, MAX_SEG_CHARS) : s.text;
  const span = h("bdi", {class: "txt", text});
  node.append(span);
  if (s.text.length > MAX_SEG_CHARS) {
    const more = h("button", {class: "link small", type: "button", text: "…", "aria-label": t("more_paras"),
      onclick: () => { span.textContent = s.text; more.remove(); }});
    node.append(more);
  }
  return node;
}

function findingNode(g, segs) {
  const ex = explain(g.rule);
  const first = g.items[0];
  const ic = g.severity === "high" ? "bad" : g.severity === "medium" ? "warn" : "info";
  const places = [...new Set(g.items.map((f) => segs[f.segment]).filter(Boolean).map((s) => s.seen !== "visible" ? `${whereLabel(s.where)} · ${t(s.seen === "hidden" ? "lg_hidden" : "lg_unseen")}` : whereLabel(s.where)))];
  const anyHidden = g.items.some((f) => segs[f.segment] && segs[f.segment].seen !== "visible");
  const ev = [];
  for (const f of g.items.slice(0, 6)) {
    const s = segs[f.segment];
    const where = s && s.where ? `${whereLabel(s.where)}: ` : "";
    if (f.evidence) ev.push(where + f.evidence);
    if (f.decoded) ev.push(`${t("decoded")}: ${f.decoded}`);
  }
  return h("div", {class: `finding ${g.severity}`},
    h("div", {class: "dot"}, icon(ic)),
    h("div", {},
      h("div", {class: "row"}, h("span", {class: `tag ${g.severity === "high" ? "bad" : g.severity === "medium" ? "warn" : "mute"}`, text: t("sev_" + g.severity)}),
        g.items.length > 1 ? h("span", {class: "tag mute ltr", text: `×${g.items.length}`}) : null,
        anyHidden ? h("span", {class: "tag amber", text: t("lg_hidden")}) : null),
      h("h3", {text: ex.text || first.message}),
      ex.fix ? h("p", {text: "→ " + ex.fix}) : null,
      places.length ? h("p", {class: "small muted", text: `${t("where")}: ${places.slice(0, 5).join(" · ")}${places.length > 5 ? " …" : ""}`}) : null,
      ev.length ? h("details", {class: "ev"}, h("summary", {}, icon("chev"), t("evidence")),
        ev.map((line) => h("div", {class: "code", text: line})),
        h("div", {class: "code", text: `${g.rule} · ${first.message}`})) : null));
}

function actions(view, rep) {
  return h("div", {class: "actions"},
    h("button", {class: "btn", type: "button", onclick: () => { last = null; renderStart(view); window.scrollTo({top: 0, behavior: "smooth"}); }}, icon("upload"), t("again")),
    rep.verdict !== "unsupported" ? h("button", {class: "btn line", type: "button", onclick: async () => {
      toast((await copyText(summary(rep))) ? t("copied") : t("error"));
    }}, icon("clipboard"), t("copy")) : null);
}

function summary(rep) {
  const lines = [`${t("name")} — ${rep.name}`, `${t("v_" + rep.verdict)}`,
    `${t("st_hidden")}: ${rep.counts.hidden} · ${t("st_unseen")}: ${rep.counts.unseen}`];
  for (const s of rep.segments.filter((x) => x.seen !== "visible").slice(0, 12)) {
    lines.push(`- [${(s.hidden || []).map(reasonLabel).join(", ")}] ${s.text.slice(0, 200)}`);
  }
  lines.push("", t("note_local"));
  return lines.join("\n");
}
