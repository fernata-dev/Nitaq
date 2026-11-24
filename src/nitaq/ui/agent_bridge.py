"""The Nitaq terminal agent inside the control center.

The same `Agent` (Gemini + the Nitaq guard) runs in a background thread; its UI is replaced by one that
turns every step into an event the page draws (a tool step, a Nitaq panel, the model's reply), and an
approval question becomes two buttons in the window instead of a y/Enter prompt in a terminal.
Workspace: ~/nitaq-demo (created with the two test skills if missing). Nothing else on the computer is used.
"""
from __future__ import annotations

import io
import threading
import time
from pathlib import Path

from nitaq.agent.ui import UI, init_color


class EventUI(UI):
    """A UI that records events instead of printing (no colours, no spinner)."""

    def __init__(self, lang: str, sink: "AgentSession") -> None:
        super().__init__(lang, out=io.StringIO())
        self.sink = sink

    def say(self, text: str = "") -> None:
        if text.strip():
            self.sink.emit("say", text=text.strip("\n"))

    def tool(self, kind: str, text: str) -> None:
        self.sink.emit("tool", kind=kind, label=self.t.get(kind, kind), text=text)

    def output(self, text: str, limit: int = 10) -> None:
        lines = text.rstrip().splitlines()
        self.sink.emit("output", lines=lines[:limit], more=max(0, len(lines) - limit))

    def panel(self, kind: str, title: str, lines: list[str]) -> None:
        self.sink.emit("panel", kind=kind, title=title, lines=lines)

    def model_text(self, text: str) -> None:
        if text.strip():
            self.sink.emit("model", text=text.strip())

    def footer(self, model: str, secs: float, tools: int) -> None:
        self.sink.emit("footer", model=model, secs=round(secs, 1), tools=tools)

    def perms(self, perms: dict, mode: str) -> None:
        self.sink.emit("perms", mode=mode, perms={k: v for k, v in perms.items()},
                       labels={k: self.t["p_" + k] for k in perms}, values={k: self.t["v_" + v] for k, v in perms.items()})

    def banner(self, *a, **k) -> None:
        pass

    def start_spinner(self) -> None:
        self.sink.emit("thinking")

    def stop_spinner(self) -> None:
        pass

    def ask(self, prompt: str) -> str:
        return "y" if self.sink.ask(prompt) else ""


class AgentSession:
    def __init__(self, home: Path, lang: str = "ar", workspace: Path | None = None, llm=None) -> None:
        from nitaq.agent.app import Agent, init_demo
        from nitaq.agent.gemini import MODELS, Gemini, find_key
        from nitaq.guard import GuardSession
        init_color(False)
        self.ws = Path(workspace or Path(home) / "nitaq-demo")
        if not (self.ws / "skills").is_dir():
            init_demo(self.ws)
        if llm is None:
            key = find_key(self.ws)
            if not key:
                raise LookupError("no Gemini key: run `nitaq agent --set-key` once, or set GEMINI_API_KEY")
            llm = Gemini(key, list(MODELS))
        self.events: list[dict] = []
        self.lock = threading.Lock()
        self.busy = False
        self._ask: dict | None = None
        self._answer = threading.Event()
        self._yes = False
        self.ui = EventUI(lang, self)
        self.agent = Agent(self.ws, llm, self.ui, GuardSession(self.ws, home=Path(home)))
        self.emit("ready", model=getattr(llm, "last_model", "?"), workspace="~/" + self.ws.name if self.ws.parent == Path(home) else str(self.ws))
        self.ui.perms(self.agent.g.permissions(), self.agent.g.mode)

    # -- events -------------------------------------------------------------------------------
    def emit(self, _type: str, /, **data) -> None:
        with self.lock:
            n = self.events[-1]["n"] + 1 if self.events else 0
            self.events.append({**data, "n": n, "type": _type, "time": time.strftime("%H:%M:%S")})
            del self.events[:-600]

    def since(self, n: int) -> dict:
        with self.lock:
            evs = [e for e in self.events if e["n"] >= n]
        return {"events": evs, "busy": self.busy, "asking": self._ask, "guard": self.agent.g.enabled,
                "mode": self.agent.g.mode}

    # -- approvals ----------------------------------------------------------------------------
    def ask(self, prompt: str) -> bool:
        self._answer.clear()
        self._ask = {"id": len(self.events), "prompt": prompt}
        self.emit("ask", id=self._ask["id"], prompt=prompt)
        answered = self._answer.wait(timeout=600)
        yes = answered and self._yes
        self.emit("answer", id=self._ask["id"], yes=yes)
        self._ask = None
        return yes

    def answer(self, yes: bool) -> bool:
        if not self._ask:
            return False
        self._yes = bool(yes)
        self._answer.set()
        return True

    # -- requests -----------------------------------------------------------------------------
    def send(self, text: str) -> bool:
        text = text.strip()
        if not text or self.busy:
            return False
        self.busy = True
        self.emit("user", text=text)
        threading.Thread(target=self._run, args=(text,), daemon=True).start()
        return True

    def _run(self, text: str) -> None:
        from nitaq.agent.app import run_turn, slash
        try:
            if text.startswith("/"):
                if text.split()[0].lower() in ("/exit", "/quit", "/q"):
                    self.emit("say", text="—")
                else:
                    slash(self.agent, text)
                    if text.split()[0].lower() in ("/approve", "/restore", "/allow", "/restrict", "/guard"):
                        self.ui.perms(self.agent.g.permissions(), self.agent.g.mode)
            else:
                run_turn(self.agent, text)
                self.ui.perms(self.agent.g.permissions(), self.agent.g.mode)
        except Exception as e:                                  # noqa: BLE001 - shown in the window
            self.emit("error", text=f"{type(e).__name__}: {e}")
        finally:
            self.busy = False
            self.emit("idle")
