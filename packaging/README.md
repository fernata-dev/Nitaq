# Packaging the Nitaq desktop app

`.github/workflows/desktop.yml` builds the app with PyInstaller on GitHub's Windows, macOS and Linux runners and
attaches the files to a GitHub release. To publish a new version: Actions → **desktop** → Run workflow → tag
`v1.0.1` (or push a tag `v*`). The website links to `releases/latest/download/<file>`, so it always serves the newest.

- Entry point: `packaging/nitaq_app.py` → `nitaq.desktop.main()`. With no arguments it opens the app; with
  arguments it is the `nitaq` command (the app starts the Gateway as `Nitaq gateway …`).
- Windows and macOS open a native window (pywebview: Edge WebView2 / WebKit). Linux opens an app window of an
  installed Chromium-family browser, or the default browser.
- Icons: `packaging/icons/` (made from `src/nitaq/web/icon.svg`; the `.icns` is built on the macOS runner).
- The builds are not code-signed yet (Windows SmartScreen and macOS Gatekeeper ask once; see RELEASE_NOTES.md).

From a checkout you can run the same app without packaging: `pip install ".[desktop]"` then `nitaq app`
(or `nitaq app --browser`).
