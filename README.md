# Nitaq — نِطاق

> **نِطاق — أي فعل خارج النطاق.. مرفوض.** Any action outside the scope is refused.

**Nitaq reduces the damage an injected instruction can cause; it does not stop a model from following it.**

**Why "Nitaq"?** *Nitaq* (نِطاق) is Arabic for **scope**. Every task an AI agent runs gets a scope:
the tools, destinations and files it actually needs. Nitaq checks each tool call against that scope
and decides from the call itself (where it goes, what it reads or carries), never from the language
of the text, so Egyptian Arabic, Arabizi or Base64 make no difference to it. That is also the
research question of this project: content filters depend on language; scope (capability) guards
do not.

Nitaq is **one product with three faces** and a research benchmark behind it:

| face | for whom | what it does |
|---|---|---|
| **Web app** (phone or any browser; installs to the home screen, works offline) | people who use **cloud assistants** (Gemini in Drive/Gmail, ChatGPT, Copilot…) | checks a Word file, an e-mail, a web page or pasted text **on the device** and shows, as an X-ray, the text a person does not see but an assistant reads (white / tiny / hidden-format text, CSS-hidden parts, comments, metadata, invisible Unicode, encoded blobs) |
| **Desktop app** (`nitaq ui`; Linux, macOS, Windows) | people who run agents on their computer | the same app, plus discovery and opt-in protection of **Claude Code** and **Gemini CLI**: MCP policy proxy, tool hook, policy editor, backups, activity log |
| **Command line** (`nitaq`) | developers, CI | discover, scan skills / tool manifests (SARIF), protect / unprotect, policy |
| **Terminal agent** (`nitaq agent`) | anyone who wants a light Codex-style agent | a small AI agent on **Gemini** (files, commands, HTTP) where every tool call goes through Nitaq: injected text is cut out of what it reads, risky actions stop and the agent's permissions are reduced until you approve |
| **Gateway** (`nitaq gateway`) | people who connect a **cloud agent** (claude.ai, ChatGPT, any MCP client) to their e-mail and files | an MCP server (Streamable HTTP or stdio) between the agent and your tools: results are scanned, risky calls wait for your approval on a local dashboard; built-in demo mailbox or `--upstream` any MCP server |

The **Nitaq benchmark** (`nitaq bench …` / `python -m nitaq_bench …`) is the research measurement below.
Supported agents for protection: **Claude Code** and **Gemini CLI** only (official docs checked, see
[`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md)). Nitaq does **not** support "any AI", and **no app
on a phone can sit between you and a cloud assistant**: for cloud assistants Nitaq checks content
*before* you hand it over (limits: [`docs/LIMITATIONS.md` §11](docs/LIMITATIONS.md)), and
`nitaq gateway` guards only the tools you connect to a cloud agent **through it** (§12).

**Live demo, command by command:** [`demo/AGENT_DEMO_COMMANDS.md`](demo/AGENT_DEMO_COMMANDS.md) — the
terminal agent with two booby-trapped skills (`skill1.md` in Franco, `skill2.md` with a `curl` that
uploads `.env`), and the Gateway with a cloud AI. Real runs: [`docs/media/agent-skill1.txt`](docs/media/agent-skill1.txt),
[`docs/media/agent-skill2.txt`](docs/media/agent-skill2.txt), [`docs/media/agent-gateway.txt`](docs/media/agent-gateway.txt).

**Website** — live at **https://byhamo.bond** (`site/`, built by `tools/site/build_site.py`): the case board (real policy decisions across languages),
the demo film with chapters, the agent's real runs, and a live **Connect your AI** panel that talks MCP to your own
`nitaq gateway --allow-origin <site>` from the browser. Deploy to Cloudflare Pages with `python3 tools/site/deploy.py`
([`docs/DEPLOY.md`](docs/DEPLOY.md), custom domain included).

<p>
<img src="docs/media/app/phone-2-result-ar.png" width="260" alt="Result of checking a Word file with hidden text (Arabic)">
<img src="docs/media/app/phone-3-xray-hidden-ar.png" width="260" alt="X-ray view: only the hidden parts">
<img src="docs/media/app/phone-8-result-en.png" width="260" alt="The same result in English">
</p>

Video: [`demo/Nitaq_Full_Demo.mp4`](demo/Nitaq_Full_Demo.mp4) — the full demo for the judges (1920×1080, real commands and the real app; narration in [`demo/SCRIPT.md`](demo/SCRIPT.md)).

Behind the product is a mock-environment benchmark and toolkit for **indirect prompt injection** against
tool-using LLM agents, built around one question:

> Do defenses against indirect prompt injection (keyword filters, scanners, classifiers) degrade
> when the attack is written in Egyptian Arabic (arz), Modern Standard Arabic (msa), Arabizi
> (Arabic in Latin letters) or mixed text, and/or is encoded (Base64, leetspeak, zero-width
> characters, ROT13, spaced letters)? Does a language-agnostic, task-bound capability guard hold
> regardless of language, what does it cost (blocked legitimate tasks), and what does it miss
> (attacks that stay inside allowed capabilities)?

Injection sources covered: e-mails, web pages, third-party skill files (`SKILL.md`) and tool
descriptions.

> نِطاق مشروع ISEF (برمجيات / أمن سيبراني). كل حاجة بتشتغل في بيئة وهمية: العنوان الوحيد للمهاجم
> هو `attacker@test.local` ومفيش أي إرسال حقيقي. نصوص الهجوم الحقيقية لازم يكتبها الطالب بنفسه
> (شوف `data/attacks/student_written/README.md`).

## Status

This repository contains **tables, not conclusions**. What the numbers do and do not support is
generated into [`CLAIMS_ALLOWED.md`](CLAIMS_ALLOWED.md) and
[`CLAIMS_NOT_ALLOWED.md`](CLAIMS_NOT_ALLOWED.md); the go/no-go rule is in
[`docs/PILOT_DECISION.md`](docs/PILOT_DECISION.md); weaknesses are in
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md). Read the limitations before quoting any number.

### Worst-case simulator, test split (generated)

<!-- BEGIN GENERATED:summary -->
Source: `results/sim_test.json` (digest `50a64bebdd01649c`, commit `588894bf95`, seed 1337). Agent: **worst-case simulated agent, not a real model**.

| defense | attack success (Wilson 95% CI) | benign utility | benign flagged |
|---|---|---|---|
| D0 | 100.0% [99.7%, 100.0%] (1224/1224) | 100.0% [93.2%, 100.0%] (53/53) | 0.0% [0.0%, 6.8%] (0/53) |
| D1 | 100.0% [99.7%, 100.0%] (1224/1224) | 100.0% [93.2%, 100.0%] (53/53) | 0.0% [0.0%, 6.8%] (0/53) |
| D2 | 94.1% [92.7%, 95.3%] (1152/1224) | 100.0% [93.2%, 100.0%] (53/53) | 0.0% [0.0%, 6.8%] (0/53) |
| D5-tools | 45.8% [43.1%, 48.6%] (561/1224) | 100.0% [93.2%, 100.0%] (53/53) | 0.0% [0.0%, 6.8%] (0/53) |
| D5-args | 33.3% [30.7%, 36.0%] (408/1224) | 90.6% [79.7%, 95.9%] (48/53) | 0.0% [0.0%, 6.8%] (0/53) |
| D5-taint | 42.2% [39.4%, 44.9%] (516/1224) | 90.6% [79.7%, 95.9%] (48/53) | 0.0% [0.0%, 6.8%] (0/53) |
| D6 | 33.3% [30.7%, 36.0%] (408/1224) | 90.6% [79.7%, 95.9%] (48/53) | 0.0% [0.0%, 6.8%] (0/53) |
| D5 | 33.3% [30.7%, 36.0%] (408/1224) | 90.6% [79.7%, 95.9%] (48/53) | 0.0% [0.0%, 6.8%] (0/53) |
| D2+D5 | 33.3% [30.7%, 36.0%] (408/1224) | 90.6% [79.7%, 95.9%] (48/53) | 0.0% [0.0%, 6.8%] (0/53) |

Attack cases: 1224 from 15 authored texts; authors: {'ai-draft': 15}. Benign cases: 53.

Not run: D4 (skipped: D4: tiktoken is not installed (pip install tiktoken)).

Scanner freeze: OK; post-freeze changes recorded: 2 (`src/nitaq_bench/defenses/d4_cpt.py`, affects results: False; `src/nitaq_bench/ (all 7 frozen files: package name only)`, affects results: False; see CHANGELOG.md).
<!-- END GENERATED:summary -->

### Real-model pilot (generated)

<!-- BEGIN GENERATED:pilot -->
Real-model pilot: **NOT RUN** (2026-11-17T08:38:46Z). Reason: Ollama not reachable: URLError: <urlopen error [Errno 111] Connection refused>. Source: `results/pilot_status.json`. No statement about real models is supported.
<!-- END GENERATED:pilot -->

Every number above is written by `python -m nitaq_bench report` from a file in `results/`;
[`docs/CLAIM_AUDIT.md`](docs/CLAIM_AUDIT.md) maps each one to its file and JSON path.

## Safety

- Every tool (`read_page`, `read_email`, `read_file`, `send_email`, `http_post`) is a Python
  function over in-memory dictionaries. Nothing is sent, fetched or written outside the process.
- The only attacker destinations are `attacker@test.local` and `http://test.local/attacker-inbox`
  (`.local` is never resolved). The data validator rejects any other address or URL.
- Mock "secrets" are synthetic strings (`FAKE-PASSWORD-nitaq-...`).
- The skill scanner reads files as text. It never executes, imports or fetches anything; shell
  patterns are reported only (a test checks a canary file is never created).
- No network calls, except to an LLM endpoint **you** configure for the optional real-model runs.
  D4 never downloads its tokenizer (a test blocks all sockets during a full simulator run).

## Install Nitaq (one command)

```bash
pipx install "git+https://github.com/fernata-dev/Nitaq.git"   # or from a checkout: pipx install .
nitaq                     # = nitaq discover: READ-ONLY report of what is on this machine
```

`pip install .` works too. Then:

```bash
nitaq agents              # the supported list and the official doc behind each integration
nitaq discover --json --out nitaq-report.json
nitaq scan ~/.claude/skills            # scan skills / tool manifests (reads text only; --sarif for CI)
nitaq protect --dry-run   # OPT-IN: exact diff of every file that would change (nothing is written)
nitaq protect --apply     # asks you to type APPLY, writes a timestamped backup first
nitaq unprotect           # restores that backup (asks you to type RESTORE)
nitaq policy show         # the policy; set "destination_mode": "taint" in ~/.nitaq/policy.json
                           # to block only destinations that appeared in untrusted tool output
```

Two destination modes: **allowlist** (default; strict: only `allowed_hosts`) and **taint** (any
destination except those seen in untrusted tool output, even Base64/zero-width/look-alike encoded).
MCP wrapping was checked with the real Claude Code 2.1.326 and Gemini CLI 0.68.0
([`docs/VERIFICATION.md`](docs/VERIFICATION.md)); the hooks were not exercised by a real session.

Nothing runs automatically: installing Nitaq changes nothing, and `discover` never writes.
(The `@ccr-…` branch suffix is needed until this work is merged into the default branch.)
Read [`docs/LIMITATIONS.md` §9](docs/LIMITATIONS.md) before `--apply`: MCP wrapping was checked with the
real CLIs, but the hook was never exercised in a real Claude Code session and no model was run.

**Try it against a real agent and your own jailbreak:** [`docs/TRY_WITH_AN_AGENT.md`](docs/TRY_WITH_AN_AGENT.md)
(Claude Code: supported; Google Antigravity: manual MCP wiring only, unsupported).

## Website

`site/` is the product website (Arabic first, English at `site/en/`). Its "Try the door" demo shows
decisions computed at build time by Nitaq's own policy code and the frozen D2 scanner
(`tools/site/build_site.py`; `tests/test_site.py` fails if a page is stale). Preview it with the app:

```bash
python tools/site/build_site.py --out _site && cd _site && python3 -m http.server 8000   # http://127.0.0.1:8000
```

It is published together with the app (at `/app/`) by the manual `pages` workflow.

<img src="docs/media/site/site-desktop-hero-ar.png" width="720" alt="Nitaq website, Arabic hero">

## The app on a phone or in a browser

The app is a folder of static files (`src/nitaq/web/`): no server code, no tracking, no
dependency. Every check runs in the browser (a Web Worker); files are never uploaded.

- **Desktop:** `nitaq ui` opens it at `http://127.0.0.1:<port>`, connected to this computer.
- **Phone:** open the hosted copy (GitHub Pages, deployed by hand with the `pages` workflow) and use
  the browser's **Add to Home screen**. It then works offline. See [`docs/INSTALL.md`](docs/INSTALL.md).
- **Try it locally without installing:** `cd src/nitaq/web && python3 -m http.server 8000`, then
  open `http://127.0.0.1:8000`.

The scanners in the app are a JavaScript port of the Python ones. `tools/export_engine_data.py`
generates their rule tables from the Python files and `tests/test_nitaq_engine_parity.py` checks
that both give byte-identical reports on a shared corpus (434 cases); Word / e-mail / HTML readers
are checked against documents written independently by Python's standard library.

## Demo (real recording)

[`demo/Nitaq_Full_Demo.mp4`](demo/Nitaq_Full_Demo.mp4) (the full demo, 3 min) and the screenshots in
[`docs/media/`](docs/media/) were recorded from real commands in a pseudo-terminal and from the real
app; `HOME` was a **fake** home with synthetic configs ([how they were made](docs/media/README.md),
[`tools/video/`](tools/video/README.md)). Replay the raw terminal session in
[`docs/media/nitaq-session-player.html`](docs/media/nitaq-session-player.html).

![discover](docs/media/02-discover.png)
![MCP proxy, taint mode](docs/media/08-mcp-proxy-taint.png)

## Quick start (research benchmark, from a checkout)

Python 3.11+, standard library only. `pytest` for tests. Optional: `numpy` (faster bootstrap),
`tiktoken` with a locally cached `cl100k_base` vocabulary (enables D4).

```bash
python -m pytest                                  # all tests
python -m nitaq_bench validate                          # check data files, show the matrix
python -m nitaq_bench eval --split dev                  # development split (scanner was tuned here)
python -m nitaq_bench eval --split test                 # refuses if frozen scanners changed (unrecorded)
python -m nitaq_bench verify-repro                      # re-run and compare digests with results/
python -m nitaq_bench report                            # report/index.html + claims + generated blocks
python -m nitaq_bench demo                              # Arabic UI on http://127.0.0.1:8765/
python -m nitaq_bench scan-skill fixtures/malicious_skill.md
python -m nitaq_bench scan-skill path/to/skills --allow docs.example.test --sarif > scan.sarif
```

`python -m nitaq_bench` works from a fresh checkout (a small `nitaq_bench.py` shim puts `src/` on the path);
`pip install -e .` also installs a `nitaq-bench` command.

## What is in the box

| part | what it does |
|---|---|
| `env/` | mock world, three tasks (`summarize_page`, `reply_email`, `search_notes`), each bound to a permission manifest (allowed tools + argument constraints) |
| `agents/obedient_mock.py` | **worst-case simulated agent, not a real model**: obeys every injection in every language and encoding using the attack's ground truth |
| `agents/llm_adapter.py` | Ollama and OpenAI-compatible adapters (temperature 0, fixed seed, N repeats, raw logs, call cap) |
| `attacks/` | JSONL schema + validators, encoders: core (`b64`, `leet`, `zwsp`, `rot13`, `spaced`), extended (`tatweel`, `tashkeel`, `homoglyph`, `translit` Arabic→Arabizi, `arabizi_noise`), stacked (`translit+leet`, …) |
| `defenses/` | D0 none · D1 English keyword list · D2 normaliser + concept lexicon (en/msa/arz/arabizi, Arabizi consonant skeletons, cross-script matching, Base64/ROT13/tag decoding) · D3 LLM judge (real model only) · D4 chars-per-token (local tokenizer only) · D5 capability guard (tool allowlist, argument constraints, taint) with ablation variants |
| `skillscan/` | static scanner for `SKILL.md` / tool manifests: hidden carriers, decoded blobs, bidi/zero-width/tag characters, homoglyphs, concealment and exfiltration instructions in four language varieties, external destinations, shell patterns; JSON or SARIF |
| `eval/` | runner, ASR / utility / false positives, Wilson 95% CI, cluster bootstrap by authored text, exact McNemar (text level and case level), freeze check, reproduction check, report |
| `demo/` | local Arabic RTL page: playground, results matrix, skill scanner; calls the evaluator's own functions |

Design details, threat model and metric definitions: [`docs/DESIGN.md`](docs/DESIGN.md).

## Research integrity

- **Dev/test discipline.** The D2 lexicon was written from the `dev` split only. The test split
  was committed first (tag `data-test-before-lexicon`), then the scanners were frozen (tag
  `freeze-scanner`). `eval --split test` refuses to run if a frozen file changed unless the
  change is sha256-pinned in `docs/post_freeze_changes.json` and described in `CHANGELOG.md`.
- **No hand-typed numbers.** Report, claims, go/no-go and the blocks above are generated.
- **Reproducible.** Fixed seed, digests over all rows and tables, `verify-repro`.
- **AI use.** All code and the starter texts were written by an AI assistant; see
  [`docs/AI_PROVENANCE.md`](docs/AI_PROVENANCE.md) and [`docs/prompt_log.md`](docs/prompt_log.md).
  The attack texts that count must be written by the student; AI drafts are capped at 5 per
  language and labelled `author: ai-draft`.

## For the student

Start with [`docs/STUDENT_GUIDE.md`](docs/STUDENT_GUIDE.md) (Arabic) and
[`docs/HANDOFF.md`](docs/HANDOFF.md).
