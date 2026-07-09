import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const baseUrl = process.env.STREAMLIT_URL || "http://localhost:8501";
const outputRoot = "/tmp/streamlit";
const pages = ["Heart_Rate", "Context", "Ring"];
const viewports = {
  desktop: { width: 1440, height: 1000 },
  mobile: { width: 390, height: 844 },
};
const systemChrome = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || "/opt/google/chrome/chrome";
const browser = await chromium.launch({
  headless: true,
  ...(existsSync(systemChrome) ? { executablePath: systemChrome } : {}),
});
let failures = 0;

try {
  await fs.mkdir(outputRoot, { recursive: true });
  for (const [viewportName, viewport] of Object.entries(viewports)) {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    const browserErrors = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));

    for (const pageName of pages) {
      await page.goto(`${baseUrl}/${pageName}`, { waitUntil: "domcontentloaded", timeout: 30000 });
      await page
        .locator("h1")
        .filter({ hasText: pageName.replace("_", " ") })
        .first()
        .waitFor({ timeout: 30000 });
      if (pageName !== "Context") {
        await page.locator(".js-plotly-plot").first().waitFor({ timeout: 30000 });
      }
      await page.waitForTimeout(1500);
      const bodyText = await page.locator("body").innerText();
      const appError = /Traceback|Uncaught app exception|Connection error/i.test(bodyText);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
      if (appError || overflow || browserErrors.length) {
        failures += 1;
        console.error(
          `${pageName} (${viewportName}) failed: ` + JSON.stringify({ appError, overflow, browserErrors }),
        );
      }
      await page.screenshot({
        path: path.join(outputRoot, `${pageName.toLowerCase()}-${viewportName}.png`),
        fullPage: true,
      });
      browserErrors.length = 0;
    }
    await context.close();
  }
} finally {
  await browser.close();
}

if (failures) {
  console.error(`Streamlit validation failed with ${failures} issue(s).`);
  process.exit(1);
}

console.log(`Streamlit validation passed. Screenshots: ${outputRoot}`);
