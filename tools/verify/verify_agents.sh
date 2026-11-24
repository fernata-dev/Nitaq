#!/bin/bash
# Real-CLI verification of Nitaq's MCP wrapping. Clean env: no credentials from this session.
set -u
SP="$1"; V="$2"
clean() { env -i HOME="$V/home" PATH="$SP/agents/node_modules/.bin:$SP/venv/bin:/usr/local/bin:/usr/bin:/bin" TERM=dumb LANG=C.UTF-8 \
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 DISABLE_AUTOUPDATER=1 NO_COLOR=1 GEMINI_CLI_TRUST_WORKSPACE=true \
  HTTPS_PROXY="${HTTPS_PROXY:-}" HTTP_PROXY="${HTTP_PROXY:-}" NODE_EXTRA_CA_CERTS=/root/.ccr/ca-bundle.crt "$@"; }
check() {
  echo "--- claude $(clean claude --version 2>/dev/null | head -1): claude mcp list"
  clean timeout 90 claude mcp list 2>&1 | grep -E "notes|Connected|Failed" | sed "s#$SP#\$SCRATCH#g"
  echo "--- gemini $(clean gemini --version 2>/dev/null | head -1): gemini mcp list"
  clean timeout 90 gemini mcp list 2>&1 | grep -E "notes|Connected|Disconnected|Disabled" | sed "s#$SP#\$SCRATCH#g"
}
echo "===== BEFORE protect"; check
echo "===== nitaq protect --apply"
clean nitaq protect --apply --confirm APPLY --no-project --mechanism mcp-stdio-proxy --no-color | grep -E "Applied|wrap MCP"
echo "===== AFTER protect (servers now start through: python -m nitaq mcp-proxy -- <original>)"; check
echo "proxy decision log:"; tail -n 3 "$V/home/.nitaq/decisions.jsonl" 2>/dev/null | cut -c1-200 || echo "(no decisions logged)"
echo "===== nitaq unprotect"
clean nitaq unprotect --confirm RESTORE --no-color | tail -1 | sed "s#$SP#\$SCRATCH#g"
echo "===== AFTER unprotect"; check
