# VERIFICATION with the real agent CLIs

Date: 2026-11-17. Where: the build container (Linux). Who ran it: the AI assistant, with
`tools/verify/verify_agents.sh`.

## What was verified

| claim | result |
|---|---|
| A stdio MCP server wrapped by `nitaq protect` still starts and completes the MCP handshake in **Claude Code 2.1.326** (`claude mcp list` health check) | **verified** |
| Same in **Gemini CLI 0.68.0** (`gemini mcp list`) | **verified** |
| The real client's requests go through the Nitaq proxy (the proxy logged hiding the poisoned tool when the client listed tools) | **verified** (log line below) |
| `nitaq unprotect` restores the configs and both CLIs still connect | **verified** |
| The PreToolUse hook blocks a real Claude Code tool call | **NOT verified**: that needs a model run with credentials, which this build did not use. `claude mcp list` was also run with a deliberately broken `hooks` value and reported nothing, so it does not validate hooks and gives no evidence either way. |
| A model actually calling a wrapped tool through the proxy | **NOT verified** (no model run) |

## Setup (clean environment)

- `npm install @anthropic-ai/claude-code @google/gemini-cli` into a scratch directory.
- `pip install .` into a scratch venv (gives `nitaq`).
- A fake HOME whose `~/.claude.json` and `~/.gemini/settings.json` each declare one stdio server:
  `python -m nitaq.testing.fake_mcp_server` (a local fake; no third-party server code was run).
- Every CLI ran under `env -i` with only `HOME`, `PATH`, `TERM`, `LANG`, proxy variables and
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, `DISABLE_AUTOUPDATER=1`, `NO_COLOR=1`: **no API key,
  token or credential of any kind** was available to them.
- Gemini CLI disables MCP servers in untrusted folders; its own error message names
  `GEMINI_CLI_TRUST_WORKSPACE=true` for headless use, which was set **only in this verification
  environment**. Nitaq never changes Gemini's trust settings.

## Output (verbatim; scratch paths shortened to `$SCRATCH`)

```text
===== BEFORE protect
--- claude 2.1.326 (Claude Code): claude mcp list
notes: $SCRATCH/venv/bin/python -m nitaq.testing.fake_mcp_server - ✔ Connected
--- gemini 0.68.0: gemini mcp list
✓ notes: $SCRATCH/venv/bin/python -m nitaq.testing.fake_mcp_server (stdio) - Connected
===== nitaq protect --apply
  • wrap MCP server 'notes' with the Nitaq policy proxy
  • wrap MCP server 'notes' with the Nitaq policy proxy
Applied 3 change(s). Backup: $SCRATCH/verify/home/.nitaq/backups/20261117T220137Z
===== AFTER protect (servers now start through: python -m nitaq mcp-proxy -- <original>)
--- claude 2.1.326 (Claude Code): claude mcp list
notes: $SCRATCH/venv/bin/python3 -m nitaq mcp-proxy --policy $SCRATCH/verify/home/.nitaq/policy.json --name notes -- $SCRATCH/venv/bin/python -m nitaq.testing.fake_mcp_server - ✔ Connected
--- gemini 0.68.0: gemini mcp list
✓ notes: $SCRATCH/venv/bin/python3 -m nitaq mcp-proxy --policy $SCRATCH/verify/home/.nitaq/policy.json --name notes -- $SCRATCH/venv/bin/python -m nitaq.testing.fake_mcp_server (stdio) - Connected
proxy decision log:
{"time": "2026-11-17T22:00:48Z", "source": "mcp-proxy:notes", "tool": "format_table", "allowed": false, "rule": "poisoned_description", "detail": "injection_body"}
{"time": "2026-11-17T22:01:37Z", "source": "mcp-proxy:notes", "tool": "format_table", "allowed": false, "rule": "poisoned_description", "detail": "injection_body"}
===== nitaq unprotect
Restored 3 file(s) from $SCRATCH/verify/home/.nitaq/backups/20261117T220137Z.
===== AFTER unprotect
--- claude 2.1.326 (Claude Code): claude mcp list
notes: $SCRATCH/venv/bin/python -m nitaq.testing.fake_mcp_server - ✔ Connected
--- gemini 0.68.0: gemini mcp list
✓ notes: $SCRATCH/venv/bin/python -m nitaq.testing.fake_mcp_server (stdio) - Connected
```
