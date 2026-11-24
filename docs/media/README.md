# Demo media — how they were made

- **What you see is real.** Every command in the screenshots (and in `demo/Nitaq_Full_Demo.mp4`, see
  `tools/video/README.md`) ran for real in a pseudo-terminal (pty) on the date shown in the replay page. The raw
  recording (every output byte with its timing) is `nitaq-session.cast.json`; open
  `nitaq-session-player.html` in a browser to replay it.
- **What is not real.** `HOME` was a **fake home directory** built by `python -m nitaq.testing.fake_home`
  with synthetic Claude Code and Gemini CLI configs (fake tokens, attacker = `attacker@test.local`).
  The typing of each command line is animated; the outputs are not edited.
- **Rendering.** The recording is drawn by a small HTML renderer (ANSI colours, wrapping at the
  recorded terminal width of 118 columns) instead of a terminal emulator, because xterm.js does not
  shape or reorder Arabic. Screenshots of long outputs show only the last lines (marked with ⋮).
- **Reproduce:** see `tools/record/` (`session.py` records, `make_player.py` builds the player,
  `capture.js` takes the screenshots and the video with Playwright; `ffmpeg` converts it to MP4).

| file | stage |
|---|---|
| `01-agents.png` | the documented support list |
| `02-discover.png` | `nitaq` (= discover), read-only |
| `03-scan-skill.png` | poisoned skill (Egyptian Arabic body + Arabizi HTML comment) |
| `04-protect-dry-run.png` | exact diff, nothing written |
| `05-protect-apply.png` | typed `APPLY`, backup first |
| `06-discover-after-protect.png` | servers now behind the proxy (risks of the real server still shown) |
| `07-mcp-proxy-allowlist.png` | allowlist mode: strict; the legitimate news page is blocked too (the cost) |
| `08-mcp-proxy-taint.png` | taint mode: news page allowed; only the destination hidden in it (Base64) is blocked |
| `09-claude-code-hook.png` | documented deny JSON |
| `10-unprotect.png` | typed `RESTORE`, files restored |
| `11-benchmark.png` | Nitaq benchmark, worst-case simulator: D5-taint vs D6 |
| `12-tests.png` | full test suite |

## The app (m18)

- `app/*.png` were captured with the pre-installed Playwright
  Chromium in headless mode, at iPhone 13 / Pixel 7 profiles and at 1440×900 — **not on a real
  phone**. The app was served from `src/nitaq/web/` by `python -m http.server` on 127.0.0.1; the
  "connected" screenshots used `nitaq ui` on a **fake HOME** (`nitaq.testing.fake_home`).
- The documents in the examples are the synthetic samples in `src/nitaq/web/samples/` (written by
  `tools/parity/make_doc_fixtures.py`; attacker = `attacker@test.local`).
- Reproduce: `node tools/web/shoot.mjs URL OUT`, `node tools/web/shoot_connected.mjs "URL#token=…" OUT`.
  The app part of the demo video: `tools/video/record_app.cjs`.
- The screenshots of the m15 app were removed (that design was replaced).
