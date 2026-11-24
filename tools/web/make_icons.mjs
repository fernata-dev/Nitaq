// Render the PNG app icons (home screen / install) from src/nitaq/web/icon.svg with the
// pre-installed Playwright Chromium. usage: node tools/web/make_icons.mjs
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
const require = createRequire(import.meta.url);
const {chromium} = require("playwright");
const svg = readFileSync(new URL("../../src/nitaq/web/icon.svg", import.meta.url), "utf-8");
const out = new URL("../../src/nitaq/web/icons/", import.meta.url).pathname;
const b = await chromium.launch();
const p = await b.newPage();
for (const [name, size, maskable] of [["icon-192", 192, false], ["icon-512", 512, false], ["maskable-512", 512, true]]) {
  const inner = maskable ? Math.round(size * 0.72) : size;
  await p.setViewportSize({width: size, height: size});
  await p.setContent(`<html><body style="margin:0;display:grid;place-items:center;width:${size}px;height:${size}px;background:${maskable ? "#0b4f48" : "transparent"}">
    <div style="width:${inner}px;height:${inner}px">${svg.replace("<svg ", `<svg width="${inner}" height="${inner}" `)}</div></body></html>`);
  await p.screenshot({path: `${out}${name}.png`, omitBackground: !maskable});
}
await b.close();
console.log("icons written");
