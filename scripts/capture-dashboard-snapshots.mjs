import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const baseUrl = process.env.SNAPSHOT_BASE_URL ?? "http://127.0.0.1:5173";
const outputDir = new URL("../artifacts/dashboard-snapshots/", import.meta.url);

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, deviceScaleFactor: 1 });

for (const [name, path] of [
  ["01-login", "/login"],
  ["02-dashboard-sign-in-required", "/"],
  ["03-project-settings-sign-in-required", "/settings"],
  ["04-account-sign-in-required", "/account"],
]) {
  await page.goto(`${baseUrl}${path}`, { waitUntil: "networkidle" });
  if (path !== "/login") await page.locator(".connection-error").waitFor({ timeout: 5_000 });
  await page.screenshot({ path: new URL(`${name}.png`, outputDir).pathname, fullPage: true });
}

await page.setViewportSize({ width: 390, height: 844 });
await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
await page.locator(".connection-error").waitFor({ timeout: 5_000 });
await page.screenshot({ path: new URL("05-dashboard-mobile-sign-in-required.png", outputDir).pathname, fullPage: true });

await browser.close();
console.log(`Saved dashboard snapshots to ${outputDir.pathname}`);
