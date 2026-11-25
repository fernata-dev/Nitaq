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


def _log(home: Path, msg: str) -> None:
    """A small log next to the app's state, for the cases where a windowed app has no console."""
    try:
        d = home / ".nitaq"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "desktop.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def run(home: Path | None = None, native: bool = True) -> int:
    from nitaq.ui.server import App, make_server, open_window
    home = Path(home or Path.home())
    app = App(home, None)
    srv = make_server(app, 0)
    url = f"http://127.0.0.1:{srv.server_address[1]}/console/#token={app.token}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    app.prefetch()
    try:
        if native and not os.environ.get("NITAQ_NO_NATIVE") and _native_window(url, home):
            return 0
        how = open_window(url)
        _log(home, f"opened in {how}")
        print(f"Nitaq is open ({how}). Close its window to stop.", flush=True)
        try:
            while True:
                time.sleep(POLL)
                if app.last_ping and time.time() - app.last_ping > CLOSE_AFTER:
                    break
        except KeyboardInterrupt:
            pass
        return 0
    finally:
        app.shutdown_children()                            # the Gateway this app started stops with it
        srv.shutdown()


def _native_window(url: str, home: Path) -> bool:
    """Open a native window (pywebview). False if it is not available, so the caller falls back to a browser."""
    try:
        import webview                                     # pywebview (optional)
    except Exception as e:                                 # noqa: BLE001 - missing or broken: use a browser
        _log(home, f"no native window: {type(e).__name__}: {e}")
        return False
    try:
        webview.create_window(TITLE, url, width=1440, height=920, min_size=(1000, 660),
                              background_color="#E4D9B5", text_select=True)
        try:
            webview.start(icon=_icon())
        except TypeError:                                  # older pywebview without the icon argument
            webview.start()
        return True
    except Exception as e:                                 # noqa: BLE001 - e.g. no WebView2 runtime on Windows
        _log(home, f"native window failed, using a browser: {type(e).__name__}: {e}")
        return False


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:                                               # the packaged app doubles as the `nitaq` command
        from nitaq.cli import main as cli_main
        return cli_main(argv)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
