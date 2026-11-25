## نِطاق · Nitaq — desktop app

The Nitaq control center in its own window: no terminal, no Python needed.

| System | Download | How to open |
|---|---|---|
| **Windows 10/11** | `Nitaq-Setup-Windows-x64.exe` (installer) or `Nitaq-Windows-x64.exe` (portable) | Run the installer: Nitaq goes to the Start menu and the desktop, with an uninstaller. If SmartScreen says "Windows protected your PC", click **More info → Run anyway** (not code-signed yet). |
| **macOS (Apple Silicon)** | `Nitaq-macOS.dmg` or `Nitaq-macOS.zip` | Open the DMG, drag **Nitaq** to Applications, then **right-click → Open** the first time (not notarized yet). |
| **Linux (x64)** | `Nitaq-Linux-x64.deb` (Ubuntu/Debian) or `Nitaq-Linux-x64.tar.gz` | `sudo apt install ./Nitaq-Linux-x64.deb`, or unpack the tar.gz and run `Nitaq/install.sh`. Opens in Chrome/Chromium/Edge/Brave as an app window, or your default browser. |

What is inside: your AI agents (Claude Code, Gemini CLI) and their protection, every skill file with Nitaq's
verdict, MCP servers, the Nitaq Gateway with approve/deny buttons, the Nitaq agent (Gemini) with the two demo
skills, the policy with a live "try a decision", and the activity log. Arabic and English.

Everything runs on your computer (127.0.0.1 only). The agent needs a free Gemini API key, which you paste in
the app once; it is stored on your computer only.
