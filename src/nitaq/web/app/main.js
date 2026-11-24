// App shell: top bar, tab bar / side rail, router, language, theme, connection to `nitaq ui`.
import {aboutView, VERSION} from "./about.js";
import {checkView} from "./check.js";
import {computerView} from "./computer.js";
import {h, icon, state, store, t} from "./dom.js";
import {learnView} from "./learn.js";

// ------------------------------------------------------------------ connection (desktop only)
const LOCAL = ["127.0.0.1", "localhost", "[::1]"].includes(location.hostname);
const TOKEN = (() => {
  const m = location.hash.match(/token=([A-Za-z0-9_-]+)/);
  if (m) {
    store.set("sessionStorage", "nitaq-token", m[1]);
    history.replaceState(null, "", location.pathname + "#computer");
  }
  return LOCAL ? store.get("sessionStorage", "nitaq-token") || m?.[1] || "" : "";
})();

async function api(path, body) {
  const r = await fetch(path, {
    method: body === undefined ? "GET" : "POST", cache: "no-store",
    headers: Object.assign({"X-Nitaq-Token": TOKEN}, body === undefined ? {} : {"Content-Type": "application/json"}),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let j = {};
  try { j = await r.json(); } catch (e) { /* not JSON */ }
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

let STATUS = null;
const ctx = {
  connected: false, serverVersion: null, installPrompt: null, api,
  status: async () => (STATUS ||= await api("/api/status")),
  invalidate: () => { STATUS = null; },
  rerender: () => render(false),
  install: async () => { if (ctx.installPrompt) { ctx.installPrompt.prompt(); ctx.installPrompt = null; } },
};

// ------------------------------------------------------------------ shell
const ROUTES = [["check", "scan", "nav_check"], ["learn", "book", "nav_learn"], ["computer", "laptop", "nav_computer"], ["about", "scope", "nav_about"]];
let route = (location.hash.match(/^#(\w+)/) || [])[1];
if (!ROUTES.some(([r]) => r === route)) route = "check";

function applyLang() {
  document.documentElement.lang = state.lang;
  document.documentElement.dir = state.lang === "ar" ? "rtl" : "ltr";
  document.title = state.lang === "ar" ? "نِطاق — افحص قبل ما المساعد يقرا" : "Nitaq — check before your AI assistant reads it";
}
// Appearance follows the system setting only (HIG dark-mode: no app-specific appearance switch).
function applyTheme() {
  store.del("localStorage", "nitaq-theme");
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", dark ? "#0e1311" : "#f6f1e7");
}

function navButtons(cls) {
  return ROUTES.map(([id, ic, label]) => h("a", {class: cls, href: "#" + id, "aria-current": route === id ? "page" : null,
    onclick: (e) => { e.preventDefault(); nav(id); }}, h("span", {class: "pill-bg"}), icon(ic), h("span", {text: t(label)})));
}

function shell() {
  const app = document.getElementById("app");
  app.textContent = "";
  app.className = "app" + (ctx.connected ? " connected" : "");
  const top = h("header", {class: "top"},
    h("a", {class: "mark", href: "#check", onclick: (e) => { e.preventDefault(); nav("check"); }},
      h("img", {src: "icon.svg", alt: "", width: "34", height: "34"}),
      h("span", {}, h("b", {text: t("name")}))),
    h("span", {class: "grow"}),
    h("span", {class: "conn", title: t("connected")}, h("i"), h("span", {text: "127.0.0.1"})),
    h("button", {class: "langbtn", type: "button", lang: state.lang === "ar" ? "en" : "ar", onclick: () => {
      state.lang = state.lang === "ar" ? "en" : "ar"; store.set("localStorage", "nitaq-lang", state.lang); applyLang(); render(false);
    }, text: t("lang_switch")}));
  const rail = h("nav", {class: "rail", "aria-label": t("name")}, navButtons("tab"), h("div", {class: "spacer"}),
    h("div", {class: "foot"}, `v${VERSION}`, h("br"), t("trust_local")));
  const main = h("main", {class: "main", id: "main", tabindex: "-1"});
  const tabbar = h("nav", {class: "tabbar", "aria-label": t("name") + " · tabs"}, navButtons("tab"));
  app.append(top, rail, main, tabbar);
  return main;
}

function render(focus) {
  const main = shell();
  ({check: checkView, learn: learnView, computer: computerView, about: aboutView}[route])(main, route === "learn" ? nav : ctx);
  if (focus) main.focus({preventScroll: true});
}

function nav(id) {
  if (id === route) { window.scrollTo({top: 0, behavior: "smooth"}); return; }
  route = id;
  try { history.replaceState(null, "", "#" + id); } catch (e) { /* the view still changes */ }
  const go = () => { render(true); window.scrollTo({top: 0}); };
  if (document.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) document.startViewTransition(go);
  else go();
}

window.addEventListener("scroll", () => {
  const top = document.querySelector(".top");
  if (top) top.classList.toggle("scrolled", window.scrollY > 4);
}, {passive: true});
window.addEventListener("hashchange", () => {
  const r = (location.hash.match(/^#(\w+)/) || [])[1];
  if (r && r !== route && ROUTES.some(([x]) => x === r)) { route = r; render(true); }
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); ctx.installPrompt = e; });

// ------------------------------------------------------------------ boot
applyLang();
applyTheme();
render(false);
if (TOKEN) {
  api("/api/status").then((st) => {
    STATUS = st; ctx.connected = true; ctx.serverVersion = st.version; render(false);
  }).catch(() => { store.del("sessionStorage", "nitaq-token"); });
}
try {                                  // refused in sandboxed frames: the app still works, only not offline
  if ("serviceWorker" in navigator && (location.protocol === "https:" || LOCAL)) {
    navigator.serviceWorker.register("sw.js").catch(() => { /* offline mode unavailable */ });
  }
} catch (e) { /* offline mode unavailable */ }
