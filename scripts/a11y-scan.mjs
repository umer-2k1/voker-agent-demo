import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";

const base = process.env.A11Y_BASE ?? "http://localhost:5173";
const token = process.env.VOKER_SESSION;
const sessionId = process.env.A11Y_SESSION_ID;

const authedRoutes = ["/", "/sessions", `/sessions/${sessionId}`, "/setup", "/agents", "/settings"];

const browser = await chromium.launch();
let total = 0;

async function scan(context, route, label) {
  const page = await context.newPage();
  try {
    await page.goto(`${base}${route}`, { waitUntil: "domcontentloaded", timeout: 30000 });
    // Wait for the lazy route to render its heading before auditing.
    await page.waitForSelector("h1", { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(1500);
    const results = await new AxeBuilder({ page }).analyze();
    const violations = results.violations;
    total += violations.length;
    console.log(`\n${label}  (${route})`);
    if (!violations.length) {
      console.log("  ✓ no violations");
    } else {
      for (const v of violations) {
        console.log(`  ✗ ${v.id} [${v.impact}] ×${v.nodes.length} — ${v.help}`);
        for (const node of v.nodes.slice(0, 3)) {
          console.log(`      ${node.target.join(" ")}`);
        }
      }
    }
  } catch (error) {
    console.log(`\n${label}  (${route})\n  ! scan failed: ${error.message}`);
  } finally {
    await page.close();
  }
}

const authed = await browser.newContext();
if (token) {
  await authed.addCookies([
    { name: "session", value: token, domain: "localhost", path: "/" },
  ]);
}
for (const route of authedRoutes) {
  await scan(authed, route, "authed");
}

const anon = await browser.newContext();
await scan(anon, "/login", "anon");

await browser.close();
console.log(`\nTOTAL violation types: ${total}`);
