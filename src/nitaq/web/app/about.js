// "About" screen: the name, the three faces, privacy, honest limits.
import {h, icon, t} from "./dom.js";

export const VERSION = "1.1.0";

export function aboutView(root, ctx) {
  const v = h("div", {class: "view"});
  v.append(
    h("span", {class: "eyebrow"}, icon("scope"), t("ab_eyebrow")),
    h("h1", {text: t("ab_title")}),
    h("p", {class: "lead", text: t("ab_lead")}),
    h("div", {class: "honest mt"}, icon("info"), h("span", {text: t("honest_line")})),
    h("h2", {class: "mt3", text: t("faces_t")}),
    h("div", {class: "faces"}, [["phone", "f1"], ["laptop", "f2"], ["terminal", "f3"]].map(([ic, k]) =>
      h("div", {class: "card face"}, h("div", {class: "ic"}, icon(ic)), h("h3", {text: t(k + "_t")}), h("p", {text: t(k + "_p")}),
        h("div", {class: "where ltr", text: t(k + "_w")})))),
    h("div", {class: "grid g2 mt3"},
      h("section", {class: "card pad-l"}, h("h2", {}, t("privacy_t")), h("p", {class: "muted", text: t("privacy_p")}),
        ctx.installPrompt ? h("button", {class: "btn ghost mt", type: "button", onclick: ctx.install}, icon("phone"), t("install_app"))
          : h("p", {class: "small muted", text: t("install_hint")})),
      h("section", {class: "card pad-l"}, h("h2", {text: t("limits_t")}),
        h("ul", {class: "plain"}, ["lim1", "lim2", "lim3", "lim4"].map((k) => h("li", {text: t(k)}))))),
    h("p", {class: "small muted mt2"}, `${t("version")} ${VERSION}`, ctx.serverVersion ? ` · desktop ${ctx.serverVersion}` : "", " · ", t("licenses")));
  root.append(v);
}
