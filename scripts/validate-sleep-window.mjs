// Run after seeding tests/fixtures/sleep-window.sql in a disposable database.
// Inspect the real Grafana request bounds, rather than reimplementing its date parser.
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.env.GRAFANA_URL || "http://localhost:3000";
const outputRoot = path.join(os.tmpdir(), "sleep-window");
const systemChrome = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || "/opt/google/chrome/chrome";
const cases = [
  ["morning", "2026-11-13T07:30:00-05:00", "2026-11-01", "2026-11-02T00:00:00-05:00"],
  ["evening", "2026-11-13T22:15:00-05:00", "2026-11-01", "2026-11-02T00:00:00-05:00"],
  ["spring", "2026-03-09T07:30:00-04:00", "2026-03-07", "2026-03-08T00:00:00-05:00"],
  ["spring-same-day", "2026-03-08T10:00:00-04:00", "2026-03-07", "2026-03-08T00:00:00-05:00"],
  ["fall", "2026-11-02T07:30:00-05:00", "2026-10-31", "2026-11-01T00:00:00-04:00"],
  ["long-history", "2026-11-13T07:30:00-05:00", "2015-06-16", "2015-06-17T00:00:00-04:00"],
  ["today", "2026-11-13T07:30:00-05:00", "2026-11-13", "2026-11-13T07:30:00-05:00"],
];
const browser = await chromium.launch({
  headless: true,
  ...(existsSync(systemChrome) ? { executablePath: systemChrome } : {}),
});
let failures = 0;
try {
  await fs.mkdir(outputRoot, { recursive: true });
  for (const [name, clock, night, expectedEnd] of cases) {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 700 },
      timezoneId: "America/Toronto",
    });
    try {
      const page = await context.newPage();
      await page.clock.setFixedTime(new Date(clock));
      let lastQuery;
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("request", (request) => {
        if (!request.url().includes("/api/ds/query")) return;
        const body = request.postDataJSON();
        if (body.queries?.some((query) => query.rawSql?.startsWith("WITH sr AS"))) lastQuery = body;
      });
      const params = new URLSearchParams({
        orgId: "1", panelId: "9", from: "now-20y", to: "now",
        timezone: "America/Toronto", "var-night": night,
      });
      await page.goto(`${baseUrl}/d-solo/oura-sleep/sleep?${params}`, { waitUntil: "networkidle" });
      await page.getByRole("heading", { name: `Sleep Phase Timeline (${night})` }).waitFor();
      await page.waitForTimeout(750);
      await page.screenshot({ path: path.join(outputRoot, `${name}.png`) });
      assert.deepEqual(errors, [], "Browser errors");
      assert.ok(lastQuery, "Missing phase timeline request");
      assert.equal(Number(lastQuery.to), Date.parse(expectedEnd), "Incorrect timeline end");
      if (night === "2026-11-01") {
        assert.ok(Number(lastQuery.from) <= Date.parse("2026-10-31T18:00:00-04:00"), "Bedtime is clipped");
        assert.ok(Number(lastQuery.to) >= Date.parse("2026-11-01T12:00:00-05:00"), "Late wake is clipped");
      }
      const body = await page.locator("body").innerText();
      assert.doesNotMatch(body, /No data|Data does not have a time field|Query error|An unexpected error/i);
      console.log(`${name}: ${night}, end=${new Date(Number(lastQuery.to)).toISOString()}`);
    } catch (error) {
      failures += 1;
      console.error(`${name}: ${error.message}`);
    } finally {
      await context.close();
    }
  }
} finally {
  await browser.close();
}
assert.equal(failures, 0, `${failures} sleep window regression(s)`);
console.log(`Sleep window validation passed (${cases.length} cases). Screenshots: ${outputRoot}`);
