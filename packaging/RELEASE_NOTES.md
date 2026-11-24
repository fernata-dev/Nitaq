## نِطاق · Nitaq — desktop app

The Nitaq control center in its own window: no terminal, no Python needed.

| System | Download | How to open |
|---|---|---|
| **Windows 10/11** | `Nitaq-Windows-x64.exe` | Double-click. If Windows SmartScreen says "Windows protected your PC", click **More info → Run anyway** (the app is not code-signed yet). |
| **macOS (Apple Silicon)** | `Nitaq-macOS.zip` | Unzip, move **Nitaq** to Applications, then **right-click → Open** the first time (the app is not notarized yet). |
| **Linux (x64)** | `Nitaq-Linux-x64.tar.gz` | `tar xzf Nitaq-Linux-x64.tar.gz && Nitaq/install.sh`, then open **Nitaq** from your app menu. It opens in Chrome/Chromium/Edge/Brave as an app window, or in your default browser. |

What is inside: your AI agents (Claude Code, Gemini CLI) and their protection, every skill file with Nitaq's
verdict, MCP servers, the Nitaq Gateway with approve/deny buttons, the Nitaq agent (Gemini) with the two demo
skills, the policy with a live "try a decision", and the activity log. Arabic and English.

Everything runs on your computer (127.0.0.1 only). The agent needs a free Gemini API key, which you paste in
the app once; it is stored on your computer only.
