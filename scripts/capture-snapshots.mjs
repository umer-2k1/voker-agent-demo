import { mkdir, rm, stat } from "node:fs/promises";
import { chromium } from "playwright";

const base = process.env.SNAP_BASE ?? "http://localhost:5173";
const api = "http://localhost:8001";
const token = process.env.VOKER_SESSION;
const outDir = "snapshots";

// Fresh set every run.
await rm(outDir, { recursive: true, force: true });
await mkdir(outDir, { recursive: true });

const browser = await chromium.launch();
const saved = [];

async function settle(page, selector, ms = 25000) {
  await page.waitForSelector("h1", { timeout: ms }).catch(() => {});
  if (selector) await page.waitForSelector(selector, { timeout: ms }).catch(() => {});
  await page
    .waitForFunction(() => !document.querySelector('[role="status"]'), { timeout: ms })
    .catch(() => {});
  await page.waitForTimeout(900);
}

async function shot(page, name, { full = false } = {}) {
  const path = `${outDir}/${name}.png`;
  await page.screenshot({ path, fullPage: full });
  const { size } = await stat(path);
  saved.push(name);
  console.log(`  ✓ ${name}.png (${Math.round(size / 1024)} KB)`);
}

async function scrollTo(page, selector) {
  await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (el) el.scrollIntoView({ block: "start" });
    window.scrollBy(0, -8);
  }, selector);
  await page.waitForTimeout(500);
}

async function clickTab(page, name) {
  const tab = page.getByRole("tab", { name });
  if (await tab.count()) {
    await tab.first().click({ timeout: 4000 }).catch(() => {});
    await page.waitForTimeout(900);
  }
}

async function page_(ctx, route, label, selector, body) {
  const page = await ctx.newPage();
  try {
    await page.goto(`${base}${route}`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await settle(page, selector);
    console.log(`\n${label}  ${route}`);
    await body(page);
  } catch (error) {
    console.log(`  ! ${label} failed: ${error.message}`);
  } finally {
    await page.close();
  }
}

/** Capture the full detail flow for one session id. */
async function sessionFlow(ctx, id, prefix) {
  await page_(ctx, `/sessions/${id}`, `${prefix} detail`, "#trace dl", async (page) => {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(400);
    await shot(page, `${prefix}-01-header`);
    await scrollTo(page, '[aria-label="Call state"]');
    await shot(page, `${prefix}-02-call-state`);
    await scrollTo(page, ".conversation-timeline");
    await shot(page, `${prefix}-03-timeline`);

    await clickTab(page, /transcript/i);
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, `${prefix}-04-transcript`);

    await clickTab(page, /analysis/i);
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, `${prefix}-05-analysis-summary`);
    await scrollTo(page, "table.sr-only"); // no-op-ish; fall back below
    await page.getByText(/Tool calls/i).first().scrollIntoViewIfNeeded().catch(() => {});
    await page.waitForTimeout(400);
    await shot(page, `${prefix}-06-tool-calls`);
    await page.getByText(/Analysis history/i).first().scrollIntoViewIfNeeded().catch(() => {});
    await page.waitForTimeout(400);
    await shot(page, `${prefix}-07-findings-history`);

    await clickTab(page, /trace & events/i);
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, `${prefix}-08-waterfall`);
    await page.getByText(/Normalized events/i).first().scrollIntoViewIfNeeded().catch(() => {});
    await page.waitForTimeout(400);
    await shot(page, `${prefix}-09-events`);
  });
}

// Map external_session_id -> id from the API.
const ids = {};
if (token) {
  const res = await fetch(`${api}/api/projects/voker-voice/sessions?limit=40`, {
    headers: { Cookie: `session=${token}` },
  });
  const data = await res.json();
  for (const item of data.items) ids[item.external_session_id] = item.id;
}
const idOf = (prefix) =>
  Object.entries(ids).find(([k]) => k.startsWith(prefix))?.[1] ?? null;

if (token) {
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  await ctx.addCookies([
    { name: "session", value: token, domain: "localhost", path: "/" },
  ]);

  await page_(ctx, "/", "Overview", ".chart-card", async (page) => {
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, "01-overview", { full: true });
    await page.getByRole("button", { name: /toggle navigation/i }).click().catch(() => {});
    await page.waitForTimeout(700);
    await shot(page, "02-overview-sidebar-collapsed");
    await page.getByRole("button", { name: /toggle navigation/i }).click().catch(() => {});
    await page.waitForTimeout(700);
  });

  await page_(ctx, "/sessions", "Sessions", "table tbody tr", async (page) => {
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, "03-sessions-list", { full: true });
    await page.getByRole("button", { name: /more filters/i }).click().catch(() => {});
    await page.waitForTimeout(700);
    await shot(page, "04-sessions-filters");
  });

  const main = idOf("voker-long-");
  if (main) await sessionFlow(ctx, main, "05-main-session");
  const angry = idOf("voker-angry-");
  if (angry) await sessionFlow(ctx, angry, "06-angry-session");
  const wrongTool = idOf("voker-wrong-tool-");
  if (wrongTool) await sessionFlow(ctx, wrongTool, "07-wrong-tool-session");

  await page_(ctx, "/setup", "Setup", '[aria-label="Integration observation state"]', async (page) => {
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, "08-setup", { full: true });
    await clickTab(page, /^vapi$/i);
    await shot(page, "09-setup-vapi-connector");
    await clickTab(page, /^livekit$/i);
    await shot(page, "10-setup-livekit");
  });

  await page_(ctx, "/agents", "Agents", ".agent-grid, .first-observation-state", async (page) => {
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, "11-agents", { full: true });
  });

  await page_(ctx, "/settings", "Settings", "#profile", async (page) => {
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, "12-settings-profile");
    await scrollTo(page, "#api-keys");
    await shot(page, "13-settings-keys-mcp");
  });

  await ctx.close();
}

const anon = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
await page_(anon, "/login", "Login", "h1", async (page) => {
  await shot(page, "14-login");
});
await anon.close();

await browser.close();
console.log(`\nSaved ${saved.length} snapshots to ./${outDir}/`);
