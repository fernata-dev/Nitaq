# Install Nitaq (نِطاق) — every system

Nitaq is a Python program (3.11 or newer, no other dependencies). After installing you get two
commands: `nitaq` (the tool and the app) and `nitaq-bench` (the research benchmark).

> Tested automatically on Linux (Ubuntu, Python 3.11 and 3.13), macOS and Windows (Python 3.12) by
> the CI on every push; see `.github/workflows/ci.yml`. The app-menu launcher is Linux-only.

> If the repository is private, git will ask you to sign in to GitHub.

## On a phone (Android / iPhone) — the web app

There is nothing to install from a store. The app is a static page that runs entirely in the
browser and keeps working offline once opened.

1. Open the hosted copy of the app. It exists only after the repository owner deploys it once:
   GitHub → Settings → Pages → Source: **GitHub Actions**, then Actions → **pages** → *Run
   workflow*. The address is then `https://<owner>.github.io/<repo>/`. (GitHub Pages for a
   private repository needs a paid plan; otherwise make the repository public or host the
   `src/nitaq/web/` folder on any static host.)
2. Android (Chrome): menu ⋮ → **Add to Home screen** / **Install app**.
   iPhone (Safari): Share → **Add to Home Screen**.
3. Use **Check** with a file from Files / Drive (download it first: e.g. Google Docs → Download →
   Word .docx) or paste text. For an e-mail, paste its original source (Gmail on the web: ⋮ →
   *Show original*) to see hidden HTML parts; copying the visible text is not enough for those.

To try it on a computer without installing anything: `cd src/nitaq/web && python3 -m http.server 8000`
and open `http://127.0.0.1:8000`.

## CachyOS / Arch Linux

Arch marks the system Python as "externally managed", so do **not** use `sudo pip install`;
use `pipx` (one isolated environment for Nitaq).

```bash
sudo pacman -S --needed git python python-pipx
pipx ensurepath            # then open a new terminal
pipx install "git+https://github.com/fernata-dev/Nitaq.git"
nitaq ui                  # opens the app in your browser
nitaq shortcut            # optional: adds "Nitaq / نِطاق" to your app menu
```

Local AI for the research pilot (Ollama from the Arch repositories):

```bash
sudo pacman -S ollama          # NVIDIA: ollama-cuda   AMD: ollama-rocm
sudo systemctl enable --now ollama
ollama pull qwen2.5:7b-instruct
```


## Debian / Ubuntu

```bash
sudo apt install git python3 python3-venv pipx
pipx ensurepath
pipx install "git+https://github.com/fernata-dev/Nitaq.git"
nitaq ui
```

## macOS

```bash
brew install python git pipx
pipx ensurepath
pipx install "git+https://github.com/fernata-dev/Nitaq.git"
nitaq ui
```

## Windows (PowerShell)

```powershell
winget install Python.Python.3.12 Git.Git      # or install Python from python.org ("Add to PATH")
py -m pip install --user pipx
py -m pipx ensurepath                           # then open a new PowerShell window
pipx install "git+https://github.com/fernata-dev/Nitaq.git"
nitaq ui
```

## For the research work (all systems)

The benchmark needs the repository itself (data, results, tests):

```bash
git clone https://github.com/fernata-dev/Nitaq.git
cd Nitaq
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m nitaq_bench restore-tags
python -m pytest
```

Then follow `docs/STUDENT_GUIDE.md`.

## Uninstall

```bash
nitaq unprotect          # first, if you applied protection (restores your configs)
nitaq shortcut --remove  # if you added the launcher
pipx uninstall nitaq
```
