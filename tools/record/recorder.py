"""Record REAL commands in a pseudo-terminal into an asciicast-v2-like file.

Each command really runs (bash -c) in a pty with colours; its output bytes and
their real timing are captured. Only the typing of the command line is
animated (virtual clock). Answers to interactive prompts are typed into the pty.
"""
import codecs, fcntl, json, os, pty, random, select, struct, sys, termios, time

COLS, ROWS = 118, 34


class Rec:
    def __init__(self, env, cwd, prompt):
        self.env, self.cwd, self.prompt = env, cwd, prompt
        self.t = 0.0
        self.events, self.marks = [], []
        random.seed(7)

    def out(self, s, dt=0.0):
        self.t += dt
        self.events.append([round(self.t, 4), "o", s])

    def typed(self, cmd, comment=False):
        self.out(self.prompt, 0.5)
        for ch in cmd:
            self.out(f"\x1b[90m{ch}\x1b[0m" if comment else ch, random.uniform(0.025, 0.07))
        self.out("\r\n", 0.35)

    def run(self, cmd, answers=(), title=None, display=None):
        start = len(self.events)
        self.typed(display or cmd)
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(self.cwd)
            os.execvpe("bash", ["bash", "-c", cmd], self.env)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
        dec = codecs.getincrementaldecoder("utf-8")("replace")
        seen, pending = "", list(answers)
        last = time.monotonic()
        while True:
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    break
                if not data:
                    break
                now = time.monotonic()
                s = dec.decode(data)
                if s:
                    self.out(s, min(now - last, 2.0))
                    last = now
                    seen += s
                if pending and pending[0][0] in seen:
                    trigger, answer = pending.pop(0)
                    time.sleep(0.8)
                    for ch in answer:
                        os.write(fd, ch.encode())
                        time.sleep(0.12)
                    os.write(fd, b"\r")
                    seen = ""
                    last = time.monotonic()
            else:
                done, _ = os.waitpid(pid, os.WNOHANG)
                if done:
                    try:
                        while True:
                            data = os.read(fd, 65536)
                            if not data:
                                break
                            self.out(dec.decode(data))
                    except OSError:
                        pass
                    break
        self.marks.append({"title": title or cmd, "start": start, "end": len(self.events)})

    def comment(self, text):
        start = len(self.events)
        self.typed("# " + text, comment=True)
        self.marks.append({"title": text, "start": start, "end": len(self.events), "comment": True})

    def save(self, path, meta):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"version": 2, "width": COLS, "height": ROWS, "meta": meta, "marks": self.marks,
                       "events": self.events}, fh, ensure_ascii=False)
