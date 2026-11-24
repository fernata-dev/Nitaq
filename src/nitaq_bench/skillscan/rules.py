"""Skill-scanner rule tables (not part of the frozen benchmark scanners)."""
from __future__ import annotations

import re

SEVERITIES = ("info", "low", "medium", "high")

# Shell patterns: REPORTED ONLY.  Nothing in this project ever runs them.
SHELL_PATTERNS: list[tuple[str, str, str]] = [
    ("shell_pipe_to_shell", "high", r"(curl|wget|iwr|Invoke-WebRequest)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b"),
    ("shell_decode_exec", "high", r"base64\s+(-d|--decode)[^\n]*\|\s*(ba|z)?sh\b"),
    ("shell_reverse_shell", "high", r"/dev/tcp/|\bnc\b[^\n]*\s-e\s|\bncat\b[^\n]*--exec|bash\s+-i\s*>&"),
    ("shell_credential_read", "high", r"(~|\$HOME)/\.(ssh|aws|gnupg|config/gcloud)\b|\bid_rsa\b|\.aws/credentials|\.netrc\b"),
    ("shell_env_dump", "medium", r"\b(printenv|env)\s*(\||>)|cat\s+[^\n]*\.env\b"),
    ("shell_destructive", "high", r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\$HOME)(\s|$)|\bmkfs\.|\bdd\s+if=.*of=/dev/"),
    ("shell_persistence", "medium", r"\bcrontab\b|\.bashrc\b|\.zshrc\b|launchctl\s+load|systemctl\s+enable"),
    ("shell_powershell_encoded", "high", r"powershell[^\n]*\s-(e|enc|encodedcommand)\s"),
    ("shell_inline_interpreter", "medium", r"\b(python3?|node|perl|ruby)\s+-(c|e)\s"),
    ("shell_chmod_exec", "low", r"\bchmod\s+\+?[0-7]*x"),
    ("shell_network_upload", "medium", r"\bcurl\b[^\n]*\s(-d|--data|-F|--upload-file|-T)\s"),
]
SHELL_RES = [(rid, sev, re.compile(rx, re.I)) for rid, sev, rx in SHELL_PATTERNS]

# D2 rule -> skill-finding severity
D2_RULE_SEVERITY = {
    "override": "high", "conceal": "high", "secret_flow": "high", "redirect": "medium",
    "send_to_address": "medium", "ai_addressed": "low", "d1_override": "high", "hidden_text": "medium",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"\b(?:https?|ftp|wss?)://[^\s\"'<>)\]]+", re.I)
HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)
MD_COMMENT_RE = re.compile(r"^\s*\[(?://|comment)\]:\s*#\s*[\"(](.*)[\")]\s*$", re.M | re.I)
HIDDEN_HTML_RE = re.compile(r"<(\w+)[^>]*style\s*=\s*[\"'][^\"']*(display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0)[^\"']*[\"'][^>]*>(.*?)</\1>", re.S | re.I)
DATA_URI_RE = re.compile(r"data:([\w/+.-]+);base64,([A-Za-z0-9+/=]{16,})")
HEX_BLOB_RE = re.compile(r"(?<![0-9a-fA-F])(?:[0-9a-fA-F]{2}){24,}(?![0-9a-fA-F])")

BIDI = {"‪": "LRE", "‫": "RLE", "‬": "PDF", "‭": "LRO", "‮": "RLO",
        "⁦": "LRI", "⁧": "RLI", "⁨": "FSI", "⁩": "PDI"}
ZERO_WIDTH = {"​": "ZWSP", "‌": "ZWNJ", "‍": "ZWJ", "⁠": "WJ", "﻿": "BOM/ZWNBSP",
              "­": "SOFT HYPHEN", "᠎": "MVS", "͏": "CGJ"}
MAX_BYTES = 2_000_000
