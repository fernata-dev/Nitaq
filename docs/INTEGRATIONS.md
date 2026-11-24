# INTEGRATIONS — what Nitaq supports and the official source for each fact

Rule: an agent is supported only if its integration points were checked against its **official**
documentation, fetched during the build. Every fact below lists the URL and the date it was read.
If no documented mechanism for intervention exists, the agent is **scan-only**. If its official
documentation could not be read, it is **not supported** (Nitaq does not guess file locations).

Machine-readable list: [`data/supported_agents.json`](../data/supported_agents.json) (a byte-identical
copy ships inside the package as `src/nitaq/_data/supported_agents.json`; a test enforces that).

All documentation below was read on **2026-11-17**.

## Supported

### Claude Code (Anthropic) — discover + protect

| fact | source |
|---|---|
| Settings files: `~/.claude/settings.json` (user), `.claude/settings.json` (project), `.claude/settings.local.json` (local) | https://code.claude.com/docs/en/hooks ("Settings file locations") |
| Hooks are configured under `hooks.PreToolUse[]` with `matcher` (omitted or `"*"` matches all) and `hooks[]` of `{"type": "command", "command": ...}`; hook entries **merge** across settings levels | https://code.claude.com/docs/en/hooks |
| A PreToolUse hook receives JSON on stdin with `session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`, `tool_name`, `tool_input`, `tool_use_id` | https://code.claude.com/docs/en/hooks |
| To deny: exit 0 and print only `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": ...}}`; exit 2 also blocks; any other non-zero exit is a non-blocking error (the action goes ahead) | https://code.claude.com/docs/en/hooks |
| MCP servers: user and local scope in `~/.claude.json` (local scope under `projects.<path>.mcpServers`), project scope in `.mcp.json` at the project root; an entry with no `type` and a `command` is a stdio server with `command`, `args`, `env` | https://code.claude.com/docs/en/mcp |
| Skills: `~/.claude/skills/<skill-name>/SKILL.md` (personal), `.claude/skills/<skill-name>/SKILL.md` (project, also parent directories up to the repo root); YAML front matter, `description` recommended | https://code.claude.com/docs/en/skills |

| PostToolUse hooks receive `tool_input` and `tool_response` (the tool's output) and support the same `matcher` values as PreToolUse | https://code.claude.com/docs/en/hooks (PostToolUse section) |

Mechanisms Nitaq uses: **PostToolUse command hook** (records hosts seen in tool output; taint mode only), **PreToolUse command hook** (in `~/.claude/settings.json`) and the **MCP stdio
proxy** (wrapping stdio entries in `~/.claude.json` and project `.mcp.json`).

Not verified and therefore not used: the location of `~/.claude.json` on Windows beyond "home
directory"; managed (organization) settings; plugin hooks.

### Gemini CLI (Google) — discover + protect (MCP only)

| fact | source |
|---|---|
| MCP servers live in `mcpServers` of `~/.gemini/settings.json` (user) or `.gemini/settings.json` (project) | https://raw.githubusercontent.com/google-gemini/gemini-cli/main/docs/tools/mcp-server.md (official repository docs) |
| stdio entry fields: `command`, `args`, `env` (may reference `$VAR`/`${VAR}`), `cwd` | same |

Mechanism Nitaq uses: **MCP stdio proxy**. Gemini CLI hooks, extensions and context files were not
verified, so Nitaq neither reads nor changes them.

## The protocol behind the MCP proxy

| fact | source |
|---|---|
| stdio transport: JSON-RPC messages are UTF-8, delimited by newlines, MUST NOT contain embedded newlines; the server MUST NOT write anything to stdout that is not a valid MCP message; it MAY log to stderr | https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/docs/specification/2025-06-18/basic/transports.mdx |
| `tools/list` returns `result.tools[]` with `name`, `description`, `inputSchema` (+ `nextCursor`); `tools/call` params are `name` and `arguments`; tool execution errors are a normal result with `isError: true`; servers may send `notifications/tools/list_changed` | https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/docs/specification/2025-06-18/server/tools.mdx |

(The same specification is published on modelcontextprotocol.io, which was not reachable from the
build session; the GitHub repository is its source.)

The proxy denies a call by answering it itself with `{"content": [{"type": "text", "text": "Blocked by Nitaq policy: ..."}], "isError": true}`, so the model sees why.

## Not supported (and why)

| agent | status | reason |
|---|---|---|
| Claude Desktop | not supported | Its config file name (`claude_desktop_config.json`) appears in the Claude Code MCP docs, which also say it is read "from its standard location" on macOS and WSL, but no official page reachable from the build session gave the path. modelcontextprotocol.io was not reachable. |
| Cursor | not supported | cursor.com was not reachable from the build session. |
| VS Code / GitHub Copilot | not supported | code.visualstudio.com was not reachable; the docs path in microsoft/vscode-docs could not be located. |
| OpenAI Codex CLI | not supported | The repository's `docs/config.md` now covers only hooks and points to developers.openai.com, which was not tried after other hosts failed. |
| Windsurf, Cline, Continue, Zed, others | not supported | not checked |

You can still scan any file yourself: `nitaq scan PATH` (the skill scanner reads any text file).

## Real-CLI checks

See [`VERIFICATION.md`](VERIFICATION.md): MCP wrapping checked with Claude Code 2.1.326 and Gemini CLI
0.68.0 (`mcp list` health checks) on 2026-11-17; the Claude Code hook was not exercised by a real session.

## How to add an agent

1. Read its official documentation; quote the paths and the mechanism here with URL and date.
2. Add an entry to `data/supported_agents.json` and copy the file to `src/nitaq/_data/`.
3. Add fake-HOME fixtures and tests in `tests/test_nitaq_*.py` before touching any real machine.
4. If the agent documents no hook or MCP configuration, set `"support": "scan-only"`.
