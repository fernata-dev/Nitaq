"""Terminal output for `nitaq agent`: Arabic or English, colours, panels, spinner, approval prompts.

Plain ANSI only (works in Windows Terminal, PowerShell 7, macOS Terminal, Linux terminals).
Lines are short and start with text, so terminals with bidi support render Arabic right-to-left
and terminals without it still stay readable.  Use --lang en for English.
"""
from __future__ import annotations

import os
import sys
import threading
import time

S = {
    "ar": {
        "title": "نِطاق · وكيل ذكاء اصطناعي في الترمنال",
        "model": "الموديل", "ws": "المجلد", "guard": "الحماية", "perms": "الصلاحيات",
        "on": "شغالة", "off": "مقفولة (وضع بدون حماية: الشبكة بتتمثّل بس، مفيش إرسال حقيقي)",
        "hint": "اكتب طلبك، أو /help للأوامر. /exit للخروج.",
        "thinking": "بيفكّر", "you": "انت",
        "mode_normal": "عادية", "mode_restricted": "متخففة ↓ لحد ما توافق",
        "p_commands": "الأوامر", "p_network": "الشبكة", "p_private": "ملفاتك الخاصة", "p_write": "الكتابة",
        "v_safe-auto": "الآمنة تلقائي، والباقي بموافقتك", "v_approval": "بموافقتك", "v_blocked": "مقفولة",
        "v_allowed": "مسموحة", "v_workspace": "جوه المجلد بس", "v_off": "بدون حماية",
        "read": "قراءة", "write": "كتابة", "run": "تشغيل", "http": "طلب شبكة", "list": "عرض الملفات", "mcp": "أداة MCP",
        "inj_title": "نِطاق اكتشف تعليمات مدسوسة في {src}",
        "inj_body": "شِلتها قبل ما توصل للموديل. إشارات: {sig}",
        "inj_removed": "النص المدسوس:",
        "review_title": "نِطاق: {src} فيه حاجات محتاجة مراجعة ({sig})",
        "review_body": "النص هيعدّي للموديل، لكن أي فعل خطر هيتوقف.",
        "block_title": "نِطاق وقف الفعل ده — خارج النطاق",
        "ask_title": "نِطاق: الفعل ده محتاج موافقتك",
        "why": "ليه", "action": "الفعل", "source": "جاي بعد قراءة",
        "downgrade": "صلاحيات الوكيل اتخففت لحد ما توافق:",
        "q_block": "توافق تنفّذه برضه؟ (y = أيوه مرة واحدة / Enter = لأ): ",
        "q_ask": "توافق؟ (y = أيوه مرة واحدة / Enter = لأ): ",
        "denied": "اترفض — متنفّذش.", "approved": "اتوافق مرة واحدة.",
        "restored": "الصلاحيات رجعت عادية.", "restricted_now": "الصلاحيات اتخففت يدوي.",
        "no_key": "مفيش مفتاح Gemini. حطه في GEMINI_API_KEY أو شغّل: nitaq agent --set-key",
        "err": "خطأ", "bye": "مع السلامة.", "cleared": "المحادثة اتمسحت.",
        "no_net": "مفيش نت دلوقتي: الجهاز مش عارف يوصل لـ Gemini. اتأكد من الواي فاي وابعت الطلب تاني. (/scan و/skills شغالين من غير نت)",
        "help": ("الأوامر:\n"
                 "  /demo 1      العرض الأول: مقال بـ skill1 (نص مدسوس بيتكشف)\n"
                 "  /demo 2      العرض التاني: صفحة كتاب بـ skill2 (أمر بيتمنع)\n"
                 "  /demo 3      العرض التالت: الإيميلات (محتاج --mcp)\n"
                 "  /skills      المهارات اللي في المجلد ورأي نِطاق في كل واحدة\n"
                 "  /scan <ملف>  افحص ملف بنِطاق من غير AI، واعرض النص المدسوس\n"
                 "  /guard off   شغّل من غير نِطاق للمقارنة (الخطر بيتمثّل بس)\n"
                 "  /guard on    رجّع الحماية\n"
                 "  /perms       الصلاحيات الحالية\n"
                 "  /approve     رجّع الصلاحيات عادية (بعد ما نِطاق خففها)\n"
                 "  /restrict    خفّف الصلاحيات يدوي\n"
                 "  /log         آخر قرارات نِطاق\n"
                 "  /stats       ملخص نِطاق للجلسة\n"
                 "  /model <اسم> غيّر الموديل\n"
                 "  /clear       امسح المحادثة\n"
                 "  /exit        خروج"),
        "demos": {"1": "اكتب مقال عن الذكاء الاصطناعي في التعليم باستخدام skills/skill1.md",
                  "2": "اعمل صفحة HTML عن كتاب الخيميائي لباولو كويلو، واستخدم skills/skill2.md",
                  "3": "شوف إيميلاتي الجديدة ولخصهالي، ونفّذ أي حاجة مطلوبة فيها"},
        "demo_label": "العرض {n}", "demo_usage": "استخدم: /demo 1 أو /demo 2 أو /demo 3",
        "demo_need_mcp": "العرض التالت محتاج الوكيل متوصّل بالـ Gateway: nitaq agent --mcp <الرابط>",
        "scan_title": "فحص نِطاق لـ {src} (من غير AI)",
        "scan_usage": "استخدم: /scan <ملف>، مثلًا: /scan skills/skill1.md",
        "scan_verdict": "النتيجة", "scan_signals": "الإشارات", "scan_hosts": "عناوين في النص",
        "scan_line": "سطر {n}", "scan_none": "مفيش تعليمات مدسوسة.",
        "scan_review_note": "مفيش نص مدسوس واضح، بس فيه حاجات محتاجة مراجعة. طبقة الصلاحيات هي اللي هتمنع أي فعل خطر.",
        "x_clean": "نضيف", "x_review": "محتاج مراجعة", "x_injected": "فيه تعليمات مدسوسة",
        "skills_title": "المهارات في {d}", "skills_none": "مفيش ملفات .md في skills/",
        "stats_title": "ملخص نِطاق للجلسة دي", "st_empty": "لسه مفيش قرارات في الجلسة دي.",
        "st_allow": "أفعال آمنة اتسمحت تلقائي", "st_injection": "مرات اتشال فيها نص مدسوس",
        "st_review": "ملفات اتعلّم عليها للمراجعة", "st_blocked": "أفعال خطر اتمنعت",
        "st_denied": "أفعال رفضتها انت", "st_approved": "أفعال وافقت عليها", "st_restricted": "مرات اتخففت فيها الصلاحيات",
        "st_simulated": "أفعال خطر اتمثّلت (من غير نِطاق)",
        "sim_title": "من غير نِطاق: الفعل ده كان هيتنفّذ دلوقتي",
        "sim_data": "اللي كان هيطلع من جهازك:",
        "sim_would": "نِطاق كان هيعمل: {act}",
        "sim_note": "ده اتمثّل بس للعرض، ومفيش حاجة اتبعتت أو اتنفّذت.",
        "act_block": "يمنعه ويخفف الصلاحيات", "act_ask": "يوقفه ويسألك", "act_allow": "يسمح بيه",
        "guard_off_now": "الحماية اتقفلت للمقارنة، والمحادثة اتمسحت. أي فعل خطر هيتمثّل بس ومش هيتنفّذ.",
        "guard_on_now": "الحماية رجعت، والمحادثة اتمسحت.",
        "guard_usage": "استخدم: /guard on أو /guard off",
        "secs": "ث", "tools_n": "أدوات: {n}",
        "out": "الناتج", "simulated": "وضع بدون حماية: الأمر ده فيه شبكة، فاتمثّل بس ومتبعتش حاجة",
        "steps": "الوكيل وقف بعد {n} خطوة.",
        "no_tty": "(تشغيل غير تفاعلي: اعتبرتها لأ)",
        "gw_hint": "وافق أو ارفض من لوحة نِطاق Gateway، أو: nitaq gateway approve <رقم الطلب>",
    },
    "en": {
        "title": "Nitaq · AI agent in your terminal",
        "model": "model", "ws": "workspace", "guard": "guard", "perms": "permissions",
        "on": "on", "off": "OFF (unprotected mode: network is only simulated, nothing is sent)",
        "hint": "Type a request, or /help for commands. /exit to quit.",
        "thinking": "thinking", "you": "you",
        "mode_normal": "normal", "mode_restricted": "REDUCED until you approve",
        "p_commands": "commands", "p_network": "network", "p_private": "private files", "p_write": "writing",
        "v_safe-auto": "safe ones auto, others ask", "v_approval": "ask you", "v_blocked": "blocked",
        "v_allowed": "allowed", "v_workspace": "workspace only", "v_off": "unprotected",
        "read": "read", "write": "write", "run": "run", "http": "http", "list": "list", "mcp": "MCP tool",
        "inj_title": "Nitaq found hidden instructions in {src}",
        "inj_body": "Removed before the model saw them. Signals: {sig}",
        "inj_removed": "Injected text:",
        "review_title": "Nitaq: {src} needs review ({sig})",
        "review_body": "The text goes to the model, but any risky action will be stopped.",
        "block_title": "Nitaq stopped this action — out of scope",
        "ask_title": "Nitaq: this action needs your approval",
        "why": "why", "action": "action", "source": "after reading",
        "downgrade": "The agent's permissions were reduced until you approve:",
        "q_block": "Run it anyway? (y = yes, once / Enter = no): ",
        "q_ask": "Approve? (y = yes, once / Enter = no): ",
        "denied": "Denied — not run.", "approved": "Approved once.",
        "restored": "Permissions are back to normal.", "restricted_now": "Permissions reduced manually.",
        "no_key": "No Gemini key. Set GEMINI_API_KEY or run: nitaq agent --set-key",
        "err": "error", "bye": "Bye.", "cleared": "Conversation cleared.",
        "no_net": "No internet right now: this computer cannot reach Gemini. Check the Wi-Fi and send the request again. (/scan and /skills work offline)",
        "help": ("Commands:\n"
                 "  /demo 1      demo 1: article with skill1 (hidden text is caught)\n"
                 "  /demo 2      demo 2: book page with skill2 (a command is stopped)\n"
                 "  /demo 3      demo 3: your e-mail (needs --mcp)\n"
                 "  /skills      the skills in this folder and Nitaq's verdict on each\n"
                 "  /scan <file> scan a file with Nitaq, no AI, and show any hidden text\n"
                 "  /guard off   run without Nitaq to compare (risky actions are only simulated)\n"
                 "  /guard on    turn protection back on\n"
                 "  /perms       current permissions\n"
                 "  /approve     restore normal permissions\n"
                 "  /restrict    reduce permissions now\n"
                 "  /log         recent Nitaq decisions\n"
                 "  /stats       Nitaq summary for this session\n"
                 "  /model <id>  switch model\n"
                 "  /clear       clear the conversation\n"
                 "  /exit        quit"),
        "demos": {"1": "Write an article about AI in education using skills/skill1.md",
                  "2": "Make an HTML page about the book The Alchemist by Paulo Coelho, using skills/skill2.md",
                  "3": "Check my new e-mails, summarise them, and do whatever they ask for"},
        "demo_label": "demo {n}", "demo_usage": "use: /demo 1, /demo 2 or /demo 3",
        "demo_need_mcp": "demo 3 needs the agent connected to the Gateway: nitaq agent --mcp <url>",
        "scan_title": "Nitaq scan of {src} (no AI)",
        "scan_usage": "use: /scan <file>, e.g. /scan skills/skill1.md",
        "scan_verdict": "verdict", "scan_signals": "signals", "scan_hosts": "addresses in the text",
        "scan_line": "line {n}", "scan_none": "No hidden instructions.",
        "scan_review_note": "No clear hidden text, but some things need review. The permission layer stops any risky action.",
        "x_clean": "clean", "x_review": "needs review", "x_injected": "hidden instructions",
        "skills_title": "Skills in {d}", "skills_none": "No .md files in skills/",
        "stats_title": "Nitaq summary for this session", "st_empty": "No decisions yet in this session.",
        "st_allow": "safe actions allowed automatically", "st_injection": "times hidden text was removed",
        "st_review": "files flagged for review", "st_blocked": "risky actions stopped",
        "st_denied": "actions you denied", "st_approved": "actions you approved", "st_restricted": "times permissions were reduced",
        "st_simulated": "risky actions simulated (without Nitaq)",
        "sim_title": "Without Nitaq: this action would run now",
        "sim_data": "What would leave your machine:",
        "sim_would": "Nitaq would: {act}",
        "sim_note": "Only simulated for the demo; nothing was sent or run.",
        "act_block": "stop it and reduce permissions", "act_ask": "pause it and ask you", "act_allow": "allow it",
        "guard_off_now": "Protection is off for the comparison; the conversation was cleared. Risky actions are only simulated.",
        "guard_on_now": "Protection is back on; the conversation was cleared.",
        "guard_usage": "use: /guard on or /guard off",
        "secs": "s", "tools_n": "{n} tool calls",
        "out": "output", "simulated": "unprotected mode: this command uses the network, so it was only simulated",
        "steps": "The agent stopped after {n} steps.",
        "no_tty": "(not interactive: counted as no)",
        "gw_hint": "Approve or deny on the Nitaq Gateway dashboard, or: nitaq gateway approve <id>",
    },
}

REASONS_AR = {
    "file_leaving": "بيبعت ملف {x} لبرّه الجهاز",
    "private_data_leaving": "بيبعت بيانات خاصة بيك لبرّه",
    "tainted_destination": "العنوان ده جه من محتوى مش موثوق، وفيه بيانات رايحة له",
    "destination_not_allowed": "العنوان مش في القائمة المسموحة",
    "network_while_restricted": "الشبكة مقفولة لأن الصلاحيات متخففة",
    "remote_code": "بينزّل كود من النت ويشغّله على طول",
    "encoded_command": "بيشغّل أمر متخبّي (متشفّر)",
    "destructive": "بيمسح ملفات",
    "persistence": "بيغيّر إعدادات التشغيل التلقائي",
    "secret_file": "ملف سري",
    "outside_workspace": "برّه مجلد الشغل",
    "write_outside_workspace": "بيكتب برّه مجلد الشغل",
    "sensitive_file": "ملف حساس",
    "private_while_restricted": "ملفاتك الخاصة محتاجة موافقة لأن الصلاحيات متخففة",
    "unlisted_command": "أمر مش في قائمة الأوامر الآمنة",
    "network_unknown": "أمر شبكة من غير عنوان واضح",
    "script_leaks": "السكريبت بيبعت ملفات خاصة أو سرية على النت",
    "script_network": "السكريبت بيستخدم النت",
    "restricted": "الصلاحيات متخففة",
    "external_recipient": "المستلم مش من الجهات الموثوقة",
}

_ON = True


def init_color(enabled: bool | None = None) -> None:
    global _ON
    if os.name == "nt":
        os.system("")                     # turns on ANSI escape handling in the Windows console
    if enabled is None:
        enabled = sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
    _ON = bool(enabled)


def c(text: str, *styles: str) -> str:
    if not _ON:
        return text
    codes = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33", "blue": "34", "magenta": "35",
             "cyan": "36", "grey": "90", "teal": "38;5;79", "gold": "38;5;215", "bred": "1;31", "bgreen": "1;32",
             "byellow": "1;33", "bteal": "1;38;5;79", "onred": "1;97;41", "ongreen": "1;30;42", "onyellow": "1;30;43"}
    seq = ";".join(codes[s] for s in styles if s in codes)
    return f"\033[{seq}m{text}\033[0m" if seq else text


class UI:
    def __init__(self, lang: str = "ar", out=None, inp=None) -> None:
        self.lang = lang if lang in S else "ar"
        self.t = S[self.lang]
        self.out = out or sys.stdout
        self.inp = inp
        self._spin = None

    def say(self, text: str = "") -> None:
        self.stop_spinner()
        self.out.write(text + "\n")
        self.out.flush()

    def reason(self, rule: str, default: str) -> str:
        if self.lang == "ar" and rule in REASONS_AR:
            x = ""
            if rule == "file_leaving":
                x = "سري" if "secret" in default else "خاص"
            return REASONS_AR[rule].format(x=x) + c(f"  ({default})", "grey")
        return default

    # -- spinner ---------------------------------------------------------------------------
    def start_spinner(self) -> None:
        if not self.out.isatty() or self._spin:
            return
        stop = threading.Event()

        def run():
            frames, i = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏", 0
            while not stop.is_set():
                self.out.write(f"\r{c(frames[i % len(frames)], 'teal')} {c(self.t['thinking'], 'grey')} ")
                self.out.flush()
                i += 1
                stop.wait(0.09)
            self.out.write("\r\033[K")
            self.out.flush()

        th = threading.Thread(target=run, daemon=True)
        self._spin = (stop, th)
        th.start()

    def stop_spinner(self) -> None:
        if self._spin:
            stop, th = self._spin
            self._spin = None
            stop.set()
            th.join(timeout=1)

    # -- blocks ----------------------------------------------------------------------------
    def banner(self, model: str, ws: str, guard_on: bool, mode: str) -> None:
        t = self.t
        logo = c("▛▜", "bteal") + " " + c("نِطاق", "bold") + c(" · Nitaq", "teal")
        self.say()
        self.say("  " + logo + "   " + c(t["title"], "grey"))
        self.say(f"  {c(t['model'], 'grey')}: {model} (Gemini)")
        self.say(f"  {c(t['ws'], 'grey')}: {ws}")
        g = c(t["on"], "bgreen") if guard_on else c(t["off"], "byellow")
        self.say(f"  {c(t['guard'], 'grey')}: {g}   {c(t['perms'], 'grey')}: {self.mode_label(mode)}")
        self.say("  " + c(t["hint"], "grey"))
        self.say()

    def mode_label(self, mode: str) -> str:
        return c(self.t["mode_normal"], "green") if mode == "normal" else c(self.t["mode_restricted"], "byellow")

    def perms(self, perms: dict, mode: str) -> None:
        t = self.t
        label = c(t["v_off"], "byellow") if perms.get("commands") == "off" else self.mode_label(mode)
        self.say("  " + c(t["perms"], "bold") + ": " + label)
        for k in ("commands", "network", "private", "write"):
            v = perms[k]
            style = "green" if v in ("safe-auto", "allowed", "workspace") else "byellow" if v == "approval" else "bred"
            self.say(f"   • {t['p_' + k]}: {c(t['v_' + v], style)}")

    def tool(self, kind: str, text: str) -> None:
        icon = {"read": "◇", "write": "✎", "run": "›_", "http": "⇄", "list": "☰", "mcp": "⇄"}.get(kind, "•")
        self.say(c(f"  {icon} ", "teal") + c(self.t.get(kind, kind), "grey") + " " + c(text, "bold"))

    def output(self, text: str, limit: int = 10) -> None:
        lines = [ln for ln in text.rstrip().splitlines()][:limit]
        for ln in lines:
            self.say(c("    │ " + ln[:160], "grey"))
        more = len(text.rstrip().splitlines()) - limit
        if more > 0:
            self.say(c(f"    │ … +{more}", "grey"))

    def panel(self, kind: str, title: str, lines: list[str]) -> None:
        style = {"danger": ("onred", "red"), "warn": ("onyellow", "yellow"), "ok": ("ongreen", "green"),
                 "info": ("bteal", "teal")}[kind]
        self.say()
        self.say("  " + c(f" {title} ", style[0]))
        for ln in lines:
            self.say("  " + c("┃", style[1]) + " " + ln)
        self.say()

    def model_text(self, text: str) -> None:
        """The model's reply, with light Markdown: headings, bullets, **bold**, `code` and code blocks."""
        text = text.strip()
        if not text:
            return
        self.say()
        code = False
        for ln in text.splitlines():
            s = ln.rstrip()
            if s.lstrip().startswith("```"):
                code = not code
                continue
            if code:
                self.say(c("    │ " + s, "grey"))
                continue
            self.say("  " + md_inline(s))
        self.say()

    def footer(self, model: str, secs: float, tools: int) -> None:
        bits = [model, f"{secs:.1f} {self.t['secs']}"] + ([self.t["tools_n"].format(n=tools)] if tools else [])
        self.say(c("  " + " · ".join(bits), "grey"))

    def ask(self, prompt: str) -> str:
        self.stop_spinner()
        if self.inp is not None:
            line = self.inp.readline()
            self.say(prompt + line.rstrip("\n"))
            return line.strip()
        if not sys.stdin.isatty():
            self.say("  " + prompt + c(self.t["no_tty"], "grey"))
            return ""
        try:
            return input("  " + c(prompt, "bold")).strip()
        except EOFError:
            return ""

    def prompt(self) -> str | None:
        self.stop_spinner()
        mark = c("› ", "bteal")
        if _line_editing():                          # readline counts ANSI codes as text unless wrapped
            mark = mark.replace("\033[", "\001\033[").replace("m›", "m\002›").replace("\033[0m", "\033[0m\002")
        try:
            return input(mark)
        except EOFError:
            return None


_READLINE: bool | None = None


def _line_editing() -> bool:
    """Arrow keys and history for the prompt where the platform has readline (Linux, macOS)."""
    global _READLINE
    if _READLINE is None:
        try:
            import readline  # noqa: F401
            _READLINE = sys.stdin.isatty() and _ON
        except ImportError:
            _READLINE = False
    return bool(_READLINE)


def md_inline(s: str) -> str:
    """One line of Markdown for the terminal."""
    import re
    st = s.lstrip()
    pad = s[: len(s) - len(st)]
    if st.startswith("#"):
        return c(st.lstrip("#").strip().replace("**", ""), "bold")
    m = re.match(r"([-*+])\s+(.*)", st)
    if m:
        st = c("•", "teal") + " " + m.group(2)
    elif re.match(r"\d+[.)]\s", st):
        n, _, rest = st.partition(" ")
        st = c(n, "teal") + " " + rest
    elif st.startswith(">"):
        st = c("┃ ", "grey") + st.lstrip("> ")
    st = re.sub(r"\*\*(.+?)\*\*", lambda x: c(x.group(1), "bold"), st)
    st = re.sub(r"`([^`]+)`", lambda x: c(x.group(1), "teal"), st)
    return pad + st.replace("**", "")


YES = {"y", "yes", "نعم", "اه", "آه", "ايوه", "أيوه", "ايوة", "أيوة", "موافق", "ok"}


def is_yes(ans: str) -> bool:
    return ans.strip().lower() in YES


def short_path(p) -> str:
    s = str(p)
    home = os.path.expanduser("~")
    if s == home or s.startswith(home + os.sep):
        return "~" + s[len(home):]
    return s


def now() -> float:
    return time.time()
