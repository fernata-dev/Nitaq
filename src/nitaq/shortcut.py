"""`nitaq shortcut`: opt-in app-menu launcher (Linux freedesktop .desktop entry).

Writes only Nitaq's own two files:
  $XDG_DATA_HOME/applications/nitaq.desktop      (default ~/.local/share/...)
  $XDG_DATA_HOME/icons/hicolor/scalable/apps/nitaq.svg
--dry-run prints them; --remove deletes only these two files.  macOS / Windows:
not implemented (untested there); run `nitaq ui` from a terminal instead.
"""
from __future__ import annotations

import os
import shlex
import sys
from importlib import resources
from pathlib import Path

MARK = "X-Nitaq-Launcher=1"


def _data_home(home: Path) -> Path:
    x = os.environ.get("XDG_DATA_HOME")
    return Path(x) if x else home / ".local" / "share"


def paths(home: Path) -> tuple[Path, Path]:
    d = _data_home(home)
    return d / "applications" / "nitaq.desktop", d / "icons" / "hicolor" / "scalable" / "apps" / "nitaq.svg"


def desktop_entry(icon: Path) -> str:
    cmd = " ".join(shlex.quote(p) for p in (sys.executable, "-m", "nitaq", "ui"))
    return "\n".join([
        "[Desktop Entry]", "Type=Application", "Name=Nitaq", "Name[ar]=نِطاق",
        "GenericName=AI agent guard", "GenericName[ar]=نطاق صلاحيات وكلاء الذكاء الاصطناعي",
        "Comment=Discover, scan and protect your AI agent setup (local only)",
        "Comment[ar]=اكتشف وافحص واحمِ إعدادات وكلاء الذكاء الاصطناعي (على جهازك بس)",
        f"Exec={cmd}", f"Icon={icon}", "Terminal=false", "StartupNotify=true", "Categories=Utility;Security;", MARK, ""])


def run(home: Path, action: str, dry_run: bool) -> int:
    if not sys.platform.startswith("linux"):
        print("The app-menu launcher is implemented for Linux only. On this system run:  nitaq ui")
        return 0
    desk, icon = paths(home)
    if action == "remove":
        for p in (desk, icon):
            if p.exists() and (p == icon or MARK in p.read_text(encoding="utf-8", errors="replace")):
                print(f"{'would remove' if dry_run else 'removed'} {p}")
                if not dry_run:
                    p.unlink()
        return 0
    entry = desktop_entry(icon)
    if dry_run:
        print(f"would write {desk}:\n\n{entry}\nwould write {icon} (the Nitaq logo)")
        return 0
    if desk.exists() and MARK not in desk.read_text(encoding="utf-8", errors="replace"):
        print(f"{desk} exists and was not created by Nitaq; leaving it alone.")
        return 1
    icon.parent.mkdir(parents=True, exist_ok=True)
    desk.parent.mkdir(parents=True, exist_ok=True)
    icon.write_bytes(resources.files("nitaq").joinpath("web/icon.svg").read_bytes())
    desk.write_text(entry, encoding="utf-8")
    print(f"Added 'Nitaq' to your app menu ({desk}). Remove with: nitaq shortcut --remove")
    return 0
