#!/usr/bin/env node
/**
 * Validate all Grafana dashboards by rendering each panel individually.
 * Screenshots saved to /tmp/panels/ for visual inspection.
 *
 * Usage: node scripts/validate-dashboards.mjs [dashboard-uid]
 * Example: node scripts/validate-dashboards.mjs oura-sleep
 * No args = validate all dashboards
 */

import puppeteer from '/tmp/node_modules/puppeteer/lib/esm/puppeteer/puppeteer.js';
import { mkdir } from 'fs/promises';

const GRAFANA_URL = 'http://localhost:3000';
const OUTPUT_DIR = '/tmp/panels';
const DASHBOARDS = ['oura-overview', 'oura-sleep', 'oura-readiness', 'oura-activity', 'oura-body'];

const DASHBOARD_PARAMS = {
  'oura-overview': 'from=now-30d&to=now',
  'oura-sleep': 'from=now-6M&to=now&var-night=2026-02-17',
  'oura-readiness': 'from=now-6M&to=now',
  'oura-activity': 'from=now-6M&to=now',
  'oura-body': 'from=now-6M&to=now',
};

async function getDashboard(uid) {
  const res = await fetch(`${GRAFANA_URL}/api/dashboards/uid/${uid}`, {
    headers: { Authorization: 'Basic ' + btoa('admin:admin') },
  });
  return (await res.json()).dashboard;
}

async function loginToGrafana(browser) {
  const page = await browser.newPage();
  await page.goto(`${GRAFANA_URL}/login`, { waitUntil: 'networkidle0', timeout: 15000 }).catch(() => {});
  // Set auth cookie via API
  await page.evaluate(async () => {
    await fetch('/api/auth/test', {
      headers: { 'Authorization': 'Basic ' + btoa('admin:admin') }
    });
  });
  // Login via the API to get session cookie
  await page.evaluate(async () => {
    await fetch('/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user: 'admin', password: 'admin' })
    });
  });
  await page.close();
}

async function validateDashboard(browser, uid) {
  const dash = await getDashboard(uid);
  const panels = dash.panels || [];
  const dir = `${OUTPUT_DIR}/${uid}`;
  await mkdir(dir, { recursive: true });

  console.log(`\n${'='.repeat(60)}`);
  console.log(`Dashboard: ${dash.title} (${uid}) - ${panels.length} panels`);
  console.log('='.repeat(60));

  const issues = [];

  for (const panel of panels) {
    const page = await browser.newPage();
    // Set basic auth header for all requests
    await page.setExtraHTTPHeaders({
      'Authorization': 'Basic ' + Buffer.from('admin:admin').toString('base64')
    });
    const width = Math.max(panel.gridPos.w * 80, 600);
    const height = Math.max(panel.gridPos.h * 50, 300);
    await page.setViewport({ width, height });

    const params = DASHBOARD_PARAMS[uid] || 'from=now-30d&to=now';
    const url = `${GRAFANA_URL}/d-solo/${uid}/${uid}?orgId=1&${params}&panelId=${panel.id}&theme=light`;

    await page.goto(url, { waitUntil: 'networkidle0', timeout: 30000 }).catch(() => {});
    // Wait for panel to render - Grafana 12 may need more time
    await new Promise(r => setTimeout(r, 5000));
    // Additional wait for any lazy-loaded content
    await page.waitForFunction(() => {
      const body = document.body.innerText;
      return !body.includes('Loading') || body.includes('No data');
    }, { timeout: 10000 }).catch(() => {});

    // Check for issues
    const check = await page.evaluate(() => {
      const body = document.body.innerText;
      const noData = body.includes('No data');
      const error = body.includes('error') || body.includes('Error');
      // Check for truncated text (ellipsis)
      const ellipsis = Array.from(document.querySelectorAll('*')).some(
        el => getComputedStyle(el).textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth
      );
      return { noData, error, ellipsis, text: body.substring(0, 500) };
    });

    const filename = `panel-${String(panel.id).padStart(2, '0')}-${panel.type}.png`;
    await page.screenshot({ path: `${dir}/${filename}` });

    let status = 'OK';
    const panelIssues = [];
    if (check.noData) { status = 'NO DATA'; panelIssues.push('No data'); }
    if (check.error) { status = 'ERROR'; panelIssues.push('Error detected'); }
    if (check.ellipsis) { panelIssues.push('Truncated text'); }

    const icon = status === 'OK' ? (panelIssues.length ? '~' : '+') : '-';
    const extra = panelIssues.length ? ` [${panelIssues.join(', ')}]` : '';
    console.log(`  [${icon}] Panel ${String(panel.id).padStart(2, '0')} | ${panel.type.padEnd(15)} | ${panel.title}${extra}`);

    if (status !== 'OK' || panelIssues.length) {
      issues.push({ uid, panel: panel.id, title: panel.title, issues: panelIssues });
    }

    await page.close();
  }

  return issues;
}

async function main() {
  const filter = process.argv[2];
  const uids = filter ? [filter] : DASHBOARDS;

  await mkdir(OUTPUT_DIR, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome-stable',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
  });

  // Login first to establish session
  await loginToGrafana(browser);

  let allIssues = [];
  for (const uid of uids) {
    const issues = await validateDashboard(browser, uid);
    allIssues = allIssues.concat(issues);
  }

  await browser.close();

  console.log(`\n${'='.repeat(60)}`);
  if (allIssues.length === 0) {
    console.log('All panels OK. Screenshots in /tmp/panels/');
  } else {
    console.log(`${allIssues.length} panel(s) with issues:`);
    for (const i of allIssues) {
      console.log(`  - ${i.uid} panel ${i.panel} (${i.title}): ${i.issues.join(', ')}`);
    }
  }
  console.log('Screenshots saved to /tmp/panels/<dashboard-uid>/');
}

main().catch(err => { console.error(err); process.exit(1); });
