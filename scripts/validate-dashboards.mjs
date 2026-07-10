import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const baseUrl = process.env.GRAFANA_URL || "http://localhost:3000";
const outputRoot = "/tmp/panels";
const requested = process.argv.slice(2);
const defaultUids = [
  "oura-overview",
  "oura-sleep",
  "oura-readiness",
  "oura-activity",
  "oura-body",
  "oura-heart-rate",
  "oura-context",
  "oura-ring",
];
const uids = requested.length ? requested : defaultUids;
const viewports = {
  desktop: { width: 1440, height: 900 },
  mobile: { width: 390, height: 844 },
};
const allowedEmptyPanels = new Set([
  "oura-body:13",
  "oura-body:14",
  "oura-context:4",
  "oura-context:5",
  "oura-context:6",
]);

const systemChrome = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || "/opt/google/chrome/chrome";
let browser;
let failures = 0;

function monitorPage(page) {
  const state = {
    browserErrors: [],
    consoleErrors: [],
    requestFailures: [],
    responseErrors: [],
    datasourceChecks: [],
  };

  page.on("pageerror", (error) => state.browserErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) {
      state.consoleErrors.push(message.text());
    }
  });
  page.on("requestfailed", (request) => {
    const error = request.failure()?.errorText;
    if (error !== "net::ERR_ABORTED") {
      state.requestFailures.push({ url: request.url(), error });
    }
  });
  page.on("response", (response) => {
    const responsePath = new URL(response.url()).pathname;
    const isExpectedAnonymousResponse = response.status() === 401 && responsePath === "/api/user/stars";
    if (response.status() >= 400 && !isExpectedAnonymousResponse) {
      state.responseErrors.push({ status: response.status(), url: response.url() });
    }
    if (response.url().includes("/api/ds/query")) {
      state.datasourceChecks.push(
        (async () => {
          if (!response.ok()) {
            return `HTTP ${response.status()} from ${response.url()}`;
          }
          try {
            const body = await response.json();
            const resultErrors = Object.values(body.results || {})
              .map((result) => result.error)
              .filter(Boolean);
            return resultErrors.length ? resultErrors.join("; ") : null;
          } catch (error) {
            if (error.message.includes("Network.getResponseBody") && error.message.includes("No resource")) {
              return null;
            }
            return `Invalid datasource response: ${error.message}`;
          }
        })(),
      );
    }
  });

  return state;
}

async function consumeIssues(page, state) {
  const issues = {
    browserErrors: state.browserErrors.splice(0),
    consoleErrors: state.consoleErrors.splice(0),
    requestFailures: state.requestFailures.splice(0),
    responseErrors: state.responseErrors.splice(0),
    datasourceErrors: (await Promise.all(state.datasourceChecks.splice(0))).filter(Boolean),
    overflow: await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2),
  };
  return issues;
}

function hasIssues(issues) {
  return (
    issues.browserErrors.length ||
    issues.consoleErrors.length ||
    issues.requestFailures.length ||
    issues.responseErrors.length ||
    issues.datasourceErrors.length ||
    issues.overflow
  );
}

async function captureScrollableDashboard(page, screenshotPath) {
  const scroller = page.locator('[data-testid*="DashboardEditPaneSplitter body container"]').first();
  await scroller.waitFor({ state: "visible", timeout: 30000 });

  const containerDimensions = await scroller.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
  }));
  const windowDimensions = await page.evaluate(() => ({
    clientHeight: window.innerHeight,
    scrollHeight: document.documentElement.scrollHeight,
  }));
  const useWindow =
    containerDimensions.scrollHeight <= containerDimensions.clientHeight + 2 &&
    windowDimensions.scrollHeight > windowDimensions.clientHeight + 2;
  const dimensions = useWindow ? windowDimensions : containerDimensions;
  const maxScrollTop = Math.max(0, dimensions.scrollHeight - dimensions.clientHeight);
  const step = Math.max(1, Math.floor(dimensions.clientHeight * 0.8));
  const positions = [];
  for (let scrollTop = 0; scrollTop < maxScrollTop; scrollTop += step) {
    positions.push(scrollTop);
  }
  positions.push(maxScrollTop);

  const parsedPath = path.parse(screenshotPath);
  for (const [index, scrollTop] of [...new Set(positions)].entries()) {
    if (useWindow) {
      await page.evaluate((top) => window.scrollTo({ top, behavior: "instant" }), scrollTop);
    } else {
      await scroller.evaluate((element, top) => element.scrollTo({ top, behavior: "instant" }), scrollTop);
    }
    await page.waitForTimeout(750);
    await page.screenshot({
      path: path.join(parsedPath.dir, `${parsedPath.name}-scroll-${String(index + 1).padStart(2, "0")}${parsedPath.ext}`),
    });
  }

  if (useWindow) {
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  } else {
    await scroller.evaluate((element) => element.scrollTo({ top: 0, behavior: "instant" }));
  }
  await page.waitForTimeout(250);
  await page.screenshot({ path: screenshotPath });
}

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
    const dashboardFrom = payload.dashboard.time?.from || "now-30d";
    const dashboardTo = payload.dashboard.time?.to || "now";
    const outputDir = path.join(outputRoot, uid);
    await fs.mkdir(outputDir, { recursive: true });
    browser = await chromium.launch({
      headless: true,
      ...(existsSync(systemChrome) ? { executablePath: systemChrome } : {}),
    });

    for (const [viewportName, viewport] of Object.entries(viewports)) {
      const context = await browser.newContext({ viewport });
      const page = await context.newPage();
      const state = monitorPage(page);
      const range = `from=${encodeURIComponent(dashboardFrom)}&to=${encodeURIComponent(dashboardTo)}`;

      const dashboardUrl = `${baseUrl}/d/${uid}/${slug}?orgId=1&${range}`;
      await page.goto(dashboardUrl, { waitUntil: "networkidle", timeout: 30000 });
      await page.waitForTimeout(1000);
      await captureScrollableDashboard(page, path.join(outputDir, `dashboard-${viewportName}.png`));
      const dashboardText = await page.locator("body").innerText();
      const dashboardIssues = await consumeIssues(page, state);
      const dashboardHasError = /Query error|Panel plugin not found|An unexpected error/i.test(dashboardText);
      if (dashboardHasError || hasIssues(dashboardIssues)) {
        failures += 1;
        console.error(
          `${uid} dashboard (${viewportName}) failed: ` +
            JSON.stringify({ dashboardHasError, ...dashboardIssues }),
        );
      }

      for (const panel of panels) {
        const url = `${baseUrl}/d-solo/${uid}/${slug}?orgId=1&panelId=${panel.id}&${range}`;
        await page.goto(url, { waitUntil: "networkidle", timeout: 30000 });
        await page.waitForTimeout(750);
        const bodyText = await page.locator("body").innerText();
        const key = `${uid}:${panel.id}`;
        const hasNoData = bodyText.includes("No data");
        const hasError = /Query error|Panel plugin not found|An unexpected error/i.test(bodyText);
        const issues = await consumeIssues(page, state);

        if (hasError || hasIssues(issues) || (hasNoData && !allowedEmptyPanels.has(key))) {
          failures += 1;
          console.error(
            `${uid} panel ${panel.id} (${viewportName}) failed: ` +
              JSON.stringify({ hasError, hasNoData, ...issues }),
          );
        }

        const filename = `panel-${String(panel.id).padStart(2, "0")}-${viewportName}.png`;
        await page.screenshot({ path: path.join(outputDir, filename), fullPage: true });
      }
      await context.close();
    }
    console.log(`${uid}: captured ${panels.length} panels and full dashboards at desktop and mobile sizes`);
    await browser.close();
    browser = undefined;
  }
} finally {
  if (browser) {
    await browser.close();
  }
}

if (failures) {
  console.error(`Dashboard validation failed with ${failures} issue(s).`);
  process.exit(1);
}

console.log(`Dashboard validation passed. Screenshots: ${outputRoot}`);
