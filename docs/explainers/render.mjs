// Renders each step of an explainer page to a PNG: node render.mjs flow.html out-dir
import fs from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const [page_, outDir] = process.argv.slice(2);
fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir);
const browser = await puppeteer.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
  defaultViewport: { width: 960, height: 600, deviceScaleFactor: 1 },
});
const page = await browser.newPage();
await page.goto("file://" + path.resolve(page_), { waitUntil: "networkidle0" });
await page.waitForFunction(() => window.ready === true);
const n = await page.evaluate(() => window.steps);
for (let i = 0; i < n; i++) {
  await page.evaluate((i) => window.show(i), i);
  await page.screenshot({ path: `${outDir}/${String(i).padStart(2, "0")}.png`, clip: { x: 0, y: 0, width: 960, height: 600 } });
}
console.log(`${n} frames`);
await browser.close();
