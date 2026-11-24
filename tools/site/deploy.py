"""Build the Nitaq website and upload it to Cloudflare Pages.

  python tools/site/deploy.py                  build dist/site and deploy it to the Pages project "nitaq"
  python tools/site/deploy.py --project NAME   another project name
  python tools/site/deploy.py --build-only     only build dist/site (upload it yourself, e.g. drag-and-drop in the dashboard)

Needs Node.js (for `npx wrangler`) and a Cloudflare login (`npx wrangler login`, once). Works on Linux, macOS
and Windows. The custom domain is added once in the Cloudflare dashboard (see docs/DEPLOY.md).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dist" / "site"
WRANGLER = "wrangler@4.165.0"


def npx() -> str:
    exe = shutil.which("npx") or shutil.which("npx.cmd")
    if not exe:
        sys.exit("npx not found: install Node.js (https://nodejs.org) first, or use --build-only and upload dist/site by hand.")
    return exe


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print("$ " + " ".join(Path(args[0]).name if i == 0 else a for i, a in enumerate(args)))
    return subprocess.run(args, cwd=ROOT, check=check, text=True)


def main(argv: list[str]) -> int:
    project = argv[argv.index("--project") + 1] if "--project" in argv else "nitaq"
    run([sys.executable, str(ROOT / "tools" / "site" / "build_site.py"), "--no-images", "--out", str(OUT)])
    big = [p for p in OUT.rglob("*") if p.is_file() and p.stat().st_size > 25 * 1024 * 1024]
    if big:
        sys.exit("Cloudflare Pages refuses files over 25 MiB: " + ", ".join(str(p) for p in big))
    if "--build-only" in argv:
        print(f"built {OUT}")
        return 0
    x = npx()
    listed = subprocess.run([x, "--yes", WRANGLER, "pages", "project", "list"], cwd=ROOT, text=True, capture_output=True)
    if listed.returncode != 0:
        print(listed.stdout[-800:] + listed.stderr[-800:])
        sys.exit("wrangler could not list projects. Run `npx wrangler login` once, then try again.")
    if f" {project} " not in listed.stdout:
        # --force keeps it a classic Pages project (newer wrangler otherwise tries to turn it into a Worker)
        run([x, "--yes", WRANGLER, "pages", "project", "create", project, "--production-branch", "main", "--force"])
    run([x, "--yes", WRANGLER, "pages", "deploy", str(OUT), "--project-name", project, "--branch", "main",
         "--commit-dirty=true"])
    print(f"\nDone. The production address is printed by `npx {WRANGLER} pages project list` "
          "(for this repo: https://nitaq-f0z.pages.dev); custom domain: docs/DEPLOY.md, step 4.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
