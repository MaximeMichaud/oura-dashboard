import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const baseUrl = process.env.STREAMLIT_URL || "http://localhost:8501";
const outputRoot = "/tmp/streamlit";
const pages = [
  { route: "Overview", title: "Overview", icon: "dashboard", expectPlot: true },
  { route: "Sleep", title: "Sleep", icon: "bedtime", expectPlot: true, requiredText: "Sleep Contributors" },
  { route: "Readiness", title: "Readiness", icon: "bolt", expectPlot: true },
  { route: "Activity", title: "Activity", icon: "directions_run", expectPlot: true },
  { route: "Body", title: "Body", icon: "monitor_heart", expectPlot: true },
  { route: "Heart_Rate", title: "Heart Rate", icon: "favorite", expectPlot: true },
  { route: "Context", title: "Context", icon: "event_note", expectPlot: false },
  { route: "Ring", title: "Ring", icon: "circle", expectPlot: true },
];
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
  for (const endpoint of ["_stcore/health", "_stcore/host-config"]) {
    const response = await fetch(`${baseUrl}/${endpoint}`);
    if (!response.ok) {
      failures += 1;
      console.error(`${endpoint} failed with HTTP ${response.status}`);
    }
  }

  for (const [viewportName, viewport] of Object.entries(viewports)) {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    const browserErrors = [];
    const responseErrors = [];
    const requestFailures = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));
    page.on("response", (response) => {
      if (response.status() >= 400) {
        responseErrors.push({ status: response.status(), url: response.url() });
      }
    });
    page.on("requestfailed", (request) => {
      requestFailures.push({ url: request.url(), error: request.failure()?.errorText });
    });

    for (const pageSpec of pages) {
      const { route, title, icon, expectPlot, requiredText } = pageSpec;
      await page.goto(`${baseUrl}/${route}`, { waitUntil: "domcontentloaded", timeout: 30000 });
      await page.locator("h1").filter({ hasText: title }).first().waitFor({ timeout: 30000 });
      if (expectPlot) {
        await page.locator(".js-plotly-plot").first().waitFor({ timeout: 30000 });
      }
      if (requiredText) {
        await page.getByText(requiredText, { exact: true }).waitFor({ timeout: 30000 });
      }
      await page.waitForTimeout(1500);
      const bodyText = await page.locator("body").innerText();
      const appError = /Traceback|Uncaught app exception|Connection error/i.test(bodyText);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
      const favicon = await page.locator("link[rel~=icon]").first().getAttribute("href");
      const faviconMatches = favicon?.includes(`/materialsymbolsrounded/${icon}/`) ?? false;
      const unexpectedResponses = responseErrors.filter(({ url }) => {
        const pathname = new URL(url).pathname;
        return ![`/${route}/_stcore/health`, `/${route}/_stcore/host-config`].includes(pathname);
      });
      if (
        appError ||
        overflow ||
        !faviconMatches ||
        browserErrors.length ||
        unexpectedResponses.length ||
        requestFailures.length
      ) {
        failures += 1;
        console.error(
          `${route} (${viewportName}) failed: ` +
            JSON.stringify({
              appError,
              overflow,
              faviconMatches,
              browserErrors,
              unexpectedResponses,
              requestFailures,
            }),
        );
      }
      await page.screenshot({
        path: path.join(outputRoot, `${route.toLowerCase()}-${viewportName}.png`),
        fullPage: true,
      });
      browserErrors.length = 0;
      responseErrors.length = 0;
      requestFailures.length = 0;
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
