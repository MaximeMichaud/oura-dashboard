import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const baseUrl = process.env.STREAMLIT_URL || "http://localhost:8501";
const outputRoot = "/tmp/streamlit";
const pages = [
  { route: "", slug: "root", title: "Oura Dashboard", icon: "health_metrics", expectPlot: false },
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
const knownConsoleNoise = [/WebSocket is closed before the connection is established/i];
const browser = await chromium.launch({
  headless: true,
  ...(existsSync(systemChrome) ? { executablePath: systemChrome } : {}),
});
let failures = 0;

function isKnownConsoleNoise(message) {
  if (knownConsoleNoise.some((pattern) => pattern.test(message.text()))) {
    return true;
  }

  try {
    const pathname = new URL(message.location().url).pathname;
    return (
      /Failed to load resource:.*404 \(Not Found\)/i.test(message.text()) &&
      /\/_stcore\/(health|host-config)$/.test(pathname)
    );
  } catch {
    return false;
  }
}

async function captureScrollablePage(page, screenshotPath) {
  const main = page.locator('[data-testid="stMain"]').first();
  await main.waitFor({ state: "visible", timeout: 30000 });

  const dimensions = await main.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
  }));
  const maxScrollTop = Math.max(0, dimensions.scrollHeight - dimensions.clientHeight);
  const step = Math.max(1, Math.floor(dimensions.clientHeight * 0.8));
  const scrollPositions = [];
  for (let scrollTop = 0; scrollTop < maxScrollTop; scrollTop += step) {
    scrollPositions.push(scrollTop);
  }
  scrollPositions.push(maxScrollTop);

  const parsedPath = path.parse(screenshotPath);
  for (const [index, scrollTop] of [...new Set(scrollPositions)].entries()) {
    await main.evaluate((element, top) => element.scrollTo({ top, behavior: "instant" }), scrollTop);
    await page.waitForTimeout(250);
    await page.screenshot({
      path: path.join(parsedPath.dir, `${parsedPath.name}-scroll-${String(index + 1).padStart(2, "0")}${parsedPath.ext}`),
    });
  }

  await main.evaluate((element) => element.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({ path: screenshotPath, fullPage: true });
}

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
    const consoleErrors = [];
    const responseErrors = [];
    const requestFailures = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error" && !isKnownConsoleNoise(message)) {
        consoleErrors.push({ text: message.text(), location: message.location() });
      }
    });
    page.on("response", (response) => {
      if (response.status() >= 400) {
        responseErrors.push({ status: response.status(), url: response.url() });
      }
    });
    page.on("requestfailed", (request) => {
      requestFailures.push({ url: request.url(), error: request.failure()?.errorText });
    });

    for (const pageSpec of pages) {
      const { route, slug = route.toLowerCase(), title, icon, expectPlot, requiredText } = pageSpec;
      const routePath = route ? `/${route}` : "/";
      await page.goto(`${baseUrl}${routePath}`, { waitUntil: "domcontentloaded", timeout: 30000 });
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
        const routePrefix = route ? `/${route}` : "";
        return ![`${routePrefix}/_stcore/health`, `${routePrefix}/_stcore/host-config`].includes(pathname);
      });
      if (
        appError ||
        overflow ||
        !faviconMatches ||
        browserErrors.length ||
        consoleErrors.length ||
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
              consoleErrors,
              unexpectedResponses,
              requestFailures,
            }),
        );
      }
      await captureScrollablePage(page, path.join(outputRoot, `${slug}-${viewportName}.png`));
      browserErrors.length = 0;
      consoleErrors.length = 0;
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
