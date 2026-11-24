// "Learn" screen: how indirect prompt injection reaches cloud assistants, and habits that help.
import {h, icon, t} from "./dom.js";

export function learnView(root, nav) {
  const v = h("div", {class: "view"});
  v.append(
    h("span", {class: "eyebrow"}, icon("book"), t("l_eyebrow")),
    h("h1", {text: t("l_title")}),
    h("p", {class: "lead", text: t("l_lead")}),
    h("div", {class: "flow mt2"},
      h("article", {class: "step"},
        h("div", {class: "mock", "aria-hidden": "true"},
          h("b", {text: t("mock_doc")}), h("div", {class: "ln m"}), h("div", {class: "ln"}),
          h("span", {class: "ghost", text: t("mock_hidden")}), h("div", {class: "ln s"})),
        h("h3", {text: t("s1_t")}), h("p", {text: t("s1_p")})),
      h("article", {class: "step"},
        h("div", {class: "mock", "aria-hidden": "true"},
          h("span", {class: "bubble me", text: t("mock_ask")}), h("span", {class: "bubble", text: t("mock_reply")})),
        h("h3", {text: t("s2_t")}), h("p", {text: t("s2_p")})),
      h("article", {class: "step"},
        h("div", {class: "mock", "aria-hidden": "true"},
          h("span", {class: "bubble", text: t("mock_reply")}), h("div", {class: "act"}, icon("send"), h("span", {text: t("mock_act")}))),
        h("h3", {text: t("s3_t")}), h("p", {text: t("s3_p")}))),

    h("h2", {class: "mt3", text: t("places_t")}),
    h("div", {class: "places"}, [["drive", "p_drive"], ["mail", "p_mail"], ["globe", "p_web"], ["calendar", "p_cal"],
      ["puzzle", "p_skill"], ["clipboard", "p_chat"]].map(([ic, k]) =>
      h("div", {class: "card place"}, h("div", {class: "ic"}, icon(ic)), h("div", {}, h("h3", {text: t(k + "_t")}), h("p", {text: t(k + "_p")}))))),

    h("div", {class: "grid g2 mt3"},
      h("section", {class: "card pad-l"}, h("h2", {text: t("habits_t")}),
        h("ul", {class: "habits"}, ["h1", "h2", "h3", "h4", "h5"].map((k) =>
          h("li", {}, icon("check"), h("div", {}, h("b", {text: t(k + "_b")}), h("span", {text: t(k + "_s")})))))),
      h("section", {class: "card pad-l soft"}, h("h2", {text: t("cant_t")}),
        h("ul", {class: "habits cant"}, ["c1", "c2", "c3"].map((k) => h("li", {}, icon("info"), h("span", {text: t(k)})))),
        h("button", {class: "btn mt", type: "button", onclick: () => nav("check")}, icon("scan"), t("cta_check")))));
  root.append(v);
}
