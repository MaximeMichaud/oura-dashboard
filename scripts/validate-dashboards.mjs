import fs from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const baseUrl = process.env.GRAFANA_URL || "http://localhost:3000";
const outputRoot = "/tmp/panels";
const requested = process.argv.slice(2);
const defaultUids = ["oura-heart-rate", "oura-context", "oura-ring"];
const uids = requested.length ? requested : defaultUids;
const viewports = {
  desktop: { width: 1440, height: 900 },
  mobile: { width: 390, height: 844 },
};
const allowedEmptyPanels = new Set(["oura-context:4", "oura-context:5", "oura-context:6"]);

const systemChrome = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || "/opt/google/chrome/chrome";
const browser = await chromium.launch({
  headless: true,
  ...(existsSync(systemChrome) ? { executablePath: systemChrome } : {}),
});
let failures = 0;

try {
  for (const uid of uids) {
    const response = await fetch(`${baseUrl}/api/dashboards/uid/${uid}`);
    if (!response.ok) {
      console.error(`${uid}: dashboard API returned ${response.status}`);
      failures += 1;
      continue;
    }
    const payload = await response.json();
    const panels = payload.dashboard.panels.filter((panel) => panel.type !== "row");
    const slug = payload.meta.slug || uid;
    const outputDir = path.join(outputRoot, uid);
    await fs.mkdir(outputDir, { recursive: true });

    for (const [viewportName, viewport] of Object.entries(viewports)) {
      const context = await browser.newContext({ viewport });
      const page = await context.newPage();
      const browserErrors = [];
      page.on("pageerror", (error) => browserErrors.push(error.message));

      for (const panel of panels) {
        const url = `${baseUrl}/d-solo/${uid}/${slug}?orgId=1&panelId=${panel.id}&from=now-30d&to=now`;
        await page.goto(url, { waitUntil: "networkidle", timeout: 30000 });
        await page.waitForTimeout(750);
        const bodyText = await page.locator("body").innerText();
        const key = `${uid}:${panel.id}`;
        const hasNoData = bodyText.includes("No data");
        const hasError = /Query error|Panel plugin not found|An unexpected error/i.test(bodyText);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);

        if (hasError || overflow || browserErrors.length || (hasNoData && !allowedEmptyPanels.has(key))) {
          failures += 1;
          console.error(
            `${uid} panel ${panel.id} (${viewportName}) failed: ` +
              JSON.stringify({ hasError, hasNoData, overflow, browserErrors }),
          );
        }

        const filename = `panel-${String(panel.id).padStart(2, "0")}-${viewportName}.png`;
        await page.screenshot({ path: path.join(outputDir, filename), fullPage: true });
        browserErrors.length = 0;
      }
      await context.close();
    }
    console.log(`${uid}: captured ${panels.length} panels at desktop and mobile sizes`);
  }
} finally {
  await browser.close();
}

if (failures) {
  console.error(`Dashboard validation failed with ${failures} issue(s).`);
  process.exit(1);
}

console.log(`Dashboard validation passed. Screenshots: ${outputRoot}`);
