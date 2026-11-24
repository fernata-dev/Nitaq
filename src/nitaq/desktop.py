"""Nitaq desktop app: the control center in its own native window, no terminal needed.

  * starts the local Nitaq UI server on 127.0.0.1 (random port, one-time token);
  * opens it in a native window with pywebview when installed (Windows: Edge WebView2, macOS: WebKit),
    otherwise as an app window of an installed Chromium-family browser, otherwise in the default browser;
  * closing the window stops everything.

The packaged app (PyInstaller, see packaging/) is one executable for everything: started with no arguments it
is the desktop app; started with arguments it behaves exactly like the `nitaq` command line (the control center
uses that to start the Gateway as a separate process).
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

TITLE = "نِطاق · Nitaq"
POLL, CLOSE_AFTER = 5.0, 40.0          # the page pings every 5 s; no ping for 40 s means the window was closed


def _icon() -> str | None:
    for base in (Path(getattr(sys, "_MEIPASS", "")), Path(__file__).resolve().parent):
        for rel in ("nitaq/web/icons/icon-512.png", "web/icons/icon-512.png"):
            p = base / rel
            if p.is_file():
                return str(p)
    return None


def run(home: Path | None = None, native: bool = True) -> int:
    from nitaq.ui.server import App, make_server, open_window
    app = App(Path(home or Path.home()), None)
    srv = make_server(app, 0)
    url = f"http://127.0.0.1:{srv.server_address[1]}/console/#token={app.token}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    app.prefetch()
    if native and not os.environ.get("NITAQ_NO_NATIVE"):
        try:
            import webview                                 # pywebview (optional)
        except ImportError:
            webview = None
        if webview is not None:
            webview.create_window(TITLE, url, width=1440, height=920, min_size=(1000, 660),
                                  background_color="#E4D9B5", text_select=True)
            try:
                try:
                    webview.start(icon=_icon())
                except TypeError:                          # older pywebview without the icon argument
                    webview.start()
            finally:
                srv.shutdown()
            return 0
    how = open_window(url)
    print(f"Nitaq is open ({how}). Close its window to stop.", flush=True)
    try:
        while True:
            time.sleep(POLL)
            if app.last_ping and time.time() - app.last_ping > CLOSE_AFTER:
                break
    except KeyboardInterrupt:
        pass
    srv.shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:                                               # the packaged app doubles as the `nitaq` command
        from nitaq.cli import main as cli_main
        return cli_main(argv)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
