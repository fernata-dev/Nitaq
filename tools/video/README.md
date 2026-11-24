# tools/video — how `demo/Nitaq_Full_Demo.mp4` is made

Everything in the video is a real run: terminal scenes are real commands recorded in a pseudo-terminal,
app scenes are the real app (`nitaq ui`) on a fake HOME. No number is typed by hand.

| file | what it does |
|---|---|
| `record_terminal.py` | runs each scene's commands in a real pty (`tools/record/recorder.py`, asciicast-v2 events) |
| `same_attack.py` | scene 3: one order in five forms vs. the text filter (D2) and the real `nitaq hook claude-code` |
| `record_app.cjs` | records the app with Playwright (DevTools screencast); the drawn cursor is the only addition |
| `stage.html` | brand stage: title/section cards, terminal window, captions, QR (driven frame by frame) |
| `render.cjs` | renders stage scenes at 30 fps into one MP4 per scene |
| `assemble.py` | places app scenes in their frame, joins all scenes (ffmpeg concat), encodes the final MP4 |
| `scenes.json` | scene order, captions (Arabic), speeds and the QR link |
| `landing.html` | the page that hosts the video and the app (published as a claude.ai artifact) |

Why not VHS / asciinema + agg: they draw text cell by cell (xterm.js / their own rasteriser), so Arabic
letters come out disconnected and in the wrong order. The recorder writes the same asciicast events;
Chromium draws them with proper Arabic shaping.

## Rebuild

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]' pillow
mkdir -p demo/build && (cd demo/build && mkdir -p node && cd node && npm init -y && npm i playwright qrcode)
export NODE_PATH=$PWD/demo/build/node/node_modules        # plus PLAYWRIGHT_BROWSERS_PATH if needed
F=$XDG_RUNTIME_DIR/nitaq-demo                             # a neutral path: it shows up in the diffs
PYTHONPATH=src python3 -m nitaq.testing.fake_home $F
.venv/bin/python tools/video/record_terminal.py demo/build/casts $F/home
HOME=$F/home PYTHONPATH=src python3 -m nitaq ui --home $F/home --project $F/project --no-browser --port 8794 &
node tools/video/record_app.cjs demo/build/app "<the link nitaq ui printed>"
node tools/video/render.cjs demo/build/scenes demo/build/casts "<QR link>"
python3 tools/video/assemble.py demo/build demo/Nitaq_Full_Demo.mp4
```

`demo/build/` is scratch (git-ignored). Speeds above 1× are shown on screen as a badge.
