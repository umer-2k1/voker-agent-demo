import { mkdir, stat } from "node:fs/promises";
import { chromium } from "playwright";

const base = process.env.SNAP_BASE ?? "http://localhost:5173";
const token = process.env.VOKER_SESSION;
const sessionId =
  process.env.SNAP_SESSION_ID ?? "e4a8f87e-888b-4f63-9d59-ac9dfc54c373";
const outDir = "snapshots";

await mkdir(outDir, { recursive: true });

const browser = await chromium.launch();
const saved = [];

async function settle(page, contentSelector) {
  await page.waitForSelector("h1", { timeout: 25000 }).catch(() => {});
  if (contentSelector) {
    await page.waitForSelector(contentSelector, { timeout: 30000 }).catch(() => {});
  }
  // Wait until every loading indicator (skeletons/spinners) is gone.
  await page
    .waitForFunction(() => !document.querySelector('[role="status"]'), {
      timeout: 30000,
    })
    .catch(() => {});
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(1200);
}

async function shot(page, name, { full = true } = {}) {
  const path = `${outDir}/${name}.png`;
  await page.screenshot({ path, fullPage: full });
  const { size } = await stat(path);
  saved.push({ name, kb: Math.round(size / 1024) });
  console.log(`  ✓ ${name}.png (${Math.round(size / 1024)} KB)`);
}

async function tap(page, role, name) {
  const target = page.getByRole(role, { name });
  if (await target.count()) {
    await target.first().click({ timeout: 3000 }).catch(() => {});
    await page.waitForTimeout(700);
    return true;
  }
  return false;
}

async function capture(context, route, label, shots, contentSelector) {
  const page = await context.newPage();
  try {
    await page.goto(`${base}${route}`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await settle(page, contentSelector);
    console.log(`\n${label} ${route}`);
    await shots(page);
  } catch (error) {
    console.log(`  ! ${label} failed: ${error.message}`);
  } finally {
    await page.close();
  }
}

if (token) {
  const authed = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
  });
  await authed.addCookies([
    { name: "session", value: token, domain: "localhost", path: "/" },
  ]);

  await capture(authed, "/", "Overview", async (page) => {
    await shot(page, "01-overview");
    // Covers the icon-collapsed sidebar state.
    await tap(page, "button", /toggle navigation/i);
    await shot(page, "02-overview-sidebar-collapsed");
  }, ".chart-card");

  await capture(authed, "/sessions", "Sessions", async (page) => {
    await shot(page, "03-sessions");
    await tap(page, "button", /more filters/i);
    await shot(page, "04-sessions-filters-expanded");
  }, "table tbody tr");

  await capture(authed, `/sessions/${sessionId}`, "Session trace", async (page) => {
    await shot(page, "05-session-trace-playback");
    await tap(page, "tab", /transcript/i);
    await shot(page, "06-session-trace-transcript");
    await tap(page, "tab", /analysis/i);
    await shot(page, "07-session-trace-analysis");
    await tap(page, "tab", /trace & events/i);
    await shot(page, "08-session-events-waterfall");
  }, '[aria-label="Conversation timeline"], .conversation-timeline');

  await capture(authed, "/setup", "Setup", async (page) => {
    await shot(page, "09-setup");
    await tap(page, "tab", /^livekit$/i);
    await shot(page, "10-setup-livekit");
    await tap(page, "tab", /^vapi$/i);
    await shot(page, "11-setup-vapi-connector");
  }, '[aria-label="Integration observation state"]');

  await capture(authed, "/agents", "Agents", async (page) => {
    await shot(page, "12-agents");
  }, ".agent-grid, .first-observation-state");

  await capture(authed, "/settings", "Settings", async (page) => {
    await shot(page, "13-settings");
  }, "#profile");

  await authed.close();
}

const anon = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
await capture(anon, "/login", "Login", async (page) => {
  await shot(page, "14-login");
});
await anon.close();

await browser.close();
console.log(`\nSaved ${saved.length} snapshots to ./${outDir}/`);
