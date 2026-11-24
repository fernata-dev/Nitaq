"""Assemble demo/Nitaq_Full_Demo.mp4 from the rendered scenes (ffmpeg).

One scene = one file, all 1920x1080 at 30 fps; app scenes are placed into their stage frame
(background PNG with window and caption) and faded in/out; then everything is joined with the
concat demuxer and encoded once (H.264 + a silent AAC track, for players that expect audio).

  python tools/video/assemble.py BUILD OUT.mp4 [--maxrate 900k]
      BUILD  folder with scenes/ (render.cjs) and app/ (record_app.cjs)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "scenes.json").read_text(encoding="utf-8"))
BUILD, OUT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
RATE = sys.argv[sys.argv.index("--maxrate") + 1] if "--maxrate" in sys.argv else "900k"
FPS = CFG["fps"]
HOLE = (151, 67)                      # top-left of the app area inside the window (stage.html)


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def duration(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


parts = []
for sc in CFG["scenes"]:
    sid = sc["id"]
    if sc["kind"] == "app":
        bg, app = BUILD / "scenes" / f"{sid}.bg.png", BUILD / "app" / f"{sid}.app.mp4"
        d = duration(app)
        out = BUILD / "scenes" / f"{sid}.mp4"
        ff("-loop", "1", "-framerate", str(FPS), "-i", str(bg), "-i", str(app), "-filter_complex",
           f"[0:v][1:v]overlay={HOLE[0]}:{HOLE[1]}:shortest=1,"
           f"fade=t=in:st=0:d=0.35:color=0x0C3B3C,fade=t=out:st={d - 0.35:.3f}:d=0.35:color=0x0C3B3C,format=yuv420p",
           "-t", f"{d:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "14", str(out))
    else:
        out = BUILD / "scenes" / f"{sid}.mp4"
    if not out.exists():
        sys.exit(f"missing scene {out}")
    parts.append(out)
    print(f"{sid:20s} {duration(out):6.2f} s")

lst = BUILD / "concat.txt"
lst.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
total = sum(duration(p) for p in parts)
OUT.parent.mkdir(parents=True, exist_ok=True)
ff("-f", "concat", "-safe", "0", "-i", str(lst), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
   "-map", "0:v", "-map", "1:a", "-shortest", "-c:v", "libx264", "-preset", "slow", "-crf", "20",
   "-maxrate", RATE, "-bufsize", "4M", "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", str(FPS * 4),
   "-c:a", "aac", "-b:a", "32k", "-movflags", "+faststart",
   "-metadata", "title=نِطاق — فيديو العرض (ISEF)", str(OUT))
print(f"total {total:.1f} s -> {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
