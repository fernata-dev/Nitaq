// "Connect your AI": talks MCP (Streamable HTTP, JSON-RPC over POST) to the Nitaq Gateway URL the visitor pastes.
// The only network calls on this site are here, and they go only to that pasted URL; nothing is stored or sent elsewhere.
// The Gateway answers a website only when it was started with --allow-origin <this site> (localhost always works).
(function () {
"use strict";
const UI = self.NitaqUI;
const DEMO = self.NITAQ_DEMO;
if (!UI || !document.getElementById("cx-url")) return;
const {h, stampDown, T} = UI;
const $ = (id) => document.getElementById(id);
const input = $("cx-url"), go = $("cx-go"), out = $("cx-out"), scanBox = $("cx-scan");
const text = $("cx-text"), scanGo = $("cx-scan-go"), sample = $("cx-sample"), scanOut = $("cx-scan-out");

// ---- step 1: the command, with this site's own address
const loop = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
const web = location.protocol === "https:" || location.protocol === "http:";
const cmd = loop ? "nitaq gateway" : `nitaq gateway --allow-origin ${web ? location.origin : "https://<your-site>"}`;
$("cx-cmd").setAttribute("data-copy", cmd);
$("cx-cmd-text").textContent = cmd;
if (!web) $("cx-origin-note").hidden = false;

// ---- MCP over HTTP
let url = "", session = null, proto = null, seq = 0;
class HttpError extends Error { constructor(code) { super("HTTP " + code); this.code = code; } }
async function rpc(method, params, notify) {
  const body = notify ? {jsonrpc: "2.0", method, params} : {jsonrpc: "2.0", id: ++seq, method, params};
  const headers = {"content-type": "application/json", "accept": "application/json, text/event-stream"};
  if (session) headers["mcp-session-id"] = session;
  if (proto) headers["mcp-protocol-version"] = proto;
  const r = await fetch(url, {method: "POST", headers, body: JSON.stringify(body), mode: "cors", credentials: "omit",
    cache: "no-store", referrerPolicy: "no-referrer"});
  if (!r.ok && r.status !== 202) throw new HttpError(r.status);
  const sid = r.headers.get("mcp-session-id");
  if (sid) session = sid;
  if (notify || r.status === 202) return null;
  let msg;
  if ((r.headers.get("content-type") || "").includes("text/event-stream")) {
    const data = (await r.text()).split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).filter(Boolean);
    msg = JSON.parse(data[data.length - 1]);
  } else msg = await r.json();
  if (msg.error) throw new Error(msg.error.message || "MCP error");
  return msg.result;
}
async function tool(name, args) {
  const res = await rpc("tools/call", {name, arguments: args || {}});
  const t = (res.content || []).filter((c) => c.type === "text").map((c) => c.text).join("\n");
  try { return JSON.parse(t); } catch (e) { return t; }
}
function explain(err) {
  if (err instanceof HttpError) return err.code === 404 ? T.cx_err_404 : err.code === 403 ? T.cx_err_403 : `${T.cx_err_net} (HTTP ${err.code})`;
  return T.cx_err_net;
}

// ---- step 3: ready-made settings for the pasted URL
function cfgs(u) {
  const p = new URL(u);
  const claude = p.protocol === "https:" ? u : `https://<tunnel>${p.pathname}`;
  const sets = {"cfg-claude": [claude, claude],
    "cfg-code": [`claude mcp add --transport http nitaq ${u}`, null],
    "cfg-gemini": [JSON.stringify({mcpServers: {nitaq: {httpUrl: u}}}), null]};
  for (const [id, [txt]] of Object.entries(sets)) {
    const pre = $(id);
    pre.textContent = "";
    if (id === "cfg-code") pre.append(h("span", {class: "c", text: "$"}), " ");
    pre.append(txt);
    pre.parentElement.setAttribute("data-copy", txt);
  }
}

function row(k, v) { return h("div", {class: "row"}, h("b", {text: k}), h("code", {class: "ltr", text: v})); }
function fail(msg) {
  out.hidden = false; out.textContent = ""; out.classList.add("cx-err-box");
  out.append(h("p", {class: "err", text: msg}));
}

go.addEventListener("click", async () => {
  const u = input.value.trim();
  if (!/^https?:\/\/[^/\s]+\/mcp\/[\w-]{8,}\/?$/.test(u)) { fail(T.cx_err_bad); input.focus(); return; }
  url = u; session = null; proto = null;
  const label = go.textContent;
  go.disabled = true; go.textContent = go.dataset.busy;
  try {
    const init = await rpc("initialize", {protocolVersion: "2025-06-18", capabilities: {},
      clientInfo: {name: "nitaq-site", version: "1"}});
    proto = init.protocolVersion || null;
    await rpc("notifications/initialized", {}, true);
    const tools = (await rpc("tools/list", {})).tools || [];
    let st = null;
    if (tools.some((t) => t.name === "nitaq_status")) { try { st = await tool("nitaq_status"); } catch (e) { st = null; } }
    out.hidden = false; out.textContent = ""; out.classList.remove("cx-err-box");
    const si = init.serverInfo || {};
    out.append(h("p", {class: "ok-line", text: T.cx_ok}),
      row(T.cx_server, `${si.title || si.name || "MCP"} ${si.version || ""}`.trim()),
      row(T.cx_proto, init.protocolVersion || "?"));
    if (st && typeof st === "object") {
      out.append(row(T.cx_status, st.mode === "restricted" ? T.cx_mode_restricted : T.cx_mode_normal),
        row(T.cx_pending, String((st.pending || []).length)));
    }
    out.append(h("p", {class: "cfg-k", text: `${T.cx_tools} (${tools.length})`}),
      h("ul", {class: "roster"}, tools.map((t) => h("li", {}, h("code", {class: "ltr", text: t.name}),
        h("span", {lang: "en", dir: "ltr", text: (t.description || "").split(/(?<=\.)\s/)[0]})))));
    scanBox.hidden = !tools.some((t) => t.name === "nitaq_scan");
    cfgs(u);
  } catch (err) {
    fail(explain(err));
  } finally {
    go.disabled = false; go.textContent = label;
  }
});
input.addEventListener("keydown", (e) => { if (e.key === "Enter") go.click(); });

sample.addEventListener("click", () => { text.value = (DEMO.samples && DEMO.samples.skill1) || ""; text.focus(); });
scanGo.addEventListener("click", async () => {
  const s = text.value.trim();
  if (!s || !url) return;
  scanGo.disabled = true;
  scanOut.textContent = "";
  try {
    const r = await tool("nitaq_scan", {text: s, source: "pasted text"});
    if (typeof r !== "object") { scanOut.append(h("pre", {text: String(r)})); return; }
    const bad = r.verdict === "injected";
    const word = bad ? T.cx_injected : r.verdict === "review" ? T.cx_review : T.cx_clean;
    const lines = [`${word}  (${(r.signals || []).join(", ") || "—"})`];
    for (const part of r.removed_parts || []) lines.push("", "« " + part + " »");
    for (const f of (r.findings || []).slice(0, 6)) lines.push(`${f.severity}  L${f.line}  ${f.rule}: ${f.message}`);
    scanOut.append(h("pre", {dir: "auto", text: lines.join("\n")}));
    if (bad) {
      const st = h("div", {class: "stamp", "aria-hidden": "true"}, h("b", {text: T.seq_no}), h("small", {text: T.seq_no_sub}));
      scanOut.append(st); stampDown(st);
    }
  } catch (err) {
    scanOut.append(h("p", {class: "err", text: explain(err)}));
  } finally { scanGo.disabled = false; }
});
})();
