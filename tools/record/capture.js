const { chromium } = require('playwright');
const fs = require('fs');
const [player, out] = process.argv.slice(2);
const SHOTS = [
  [0, 2, 0, "01-agents", "nitaq agents — the documented support list"],
  [3, 3, 64, "02-discover", "nitaq (= discover) — read-only report"],
  [4, 4, 0, "03-scan-skill", "nitaq scan — poisoned SKILL.md (Egyptian Arabic + Arabizi)"],
  [5, 5, 62, "04-protect-dry-run", "nitaq protect --dry-run — exact diff, nothing written"],
  [6, 6, 26, "05-protect-apply", "nitaq protect --apply — typed confirmation + backup"],
  [7, 7, 0, "06-discover-after-protect", "nitaq discover after protect"],
  [8, 8, 0, "07-mcp-proxy-allowlist", "MCP proxy, allowlist mode: strict (the news page is blocked too)"],
  [9, 9, 0, "08-mcp-proxy-taint", "MCP proxy, taint mode: only the destination hidden in the page is blocked"],
  [10, 10, 0, "09-claude-code-hook", "Claude Code PreToolUse hook decision"],
  [11, 11, 24, "10-unprotect", "nitaq unprotect — restore from backup"],
  [12, 12, 0, "11-benchmark", "Nitaq research benchmark (worst-case simulator): D5-taint vs D6"],
  [13, 13, 0, "12-tests", "full test suite"],
];
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
  const p = await ctx.newPage();
  await p.goto('file://' + player);
  for (const [a, z, max, name, title] of SHOTS) {
    await p.evaluate(([a, z, max, title]) => window.shot(a, z, max, title), [a, z, max, title]);
    await p.locator('#win').screenshot({ path: `${out}/${name}.png` });
  }
  await ctx.close();
  const vctx = await b.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1,
                                    recordVideo: { dir: out + '/video', size: { width: 1280, height: 800 } } });
  const vp = await vctx.newPage();
  await vp.goto('file://' + player);
  await vp.evaluate(() => window.play());
  await vp.waitForFunction(() => window.done === true, null, { timeout: 300000 });
  const path = await vp.video().path();
  await vctx.close();
  await b.close();
  console.log('video', path);
})();
