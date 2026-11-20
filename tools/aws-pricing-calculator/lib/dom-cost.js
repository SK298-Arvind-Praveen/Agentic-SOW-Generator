// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

/**
 * DOM-based cost + config-summary extraction. Replacement for
 * csv-export.js when we need rendered cost numbers and/or the
 * "Configuration summary" column. Skips the Export-button → menu →
 * dialog → download flow entirely — every value the CSV would carry
 * is already in the page DOM (the CSV is generated client-side from
 * the same in-memory state).
 *
 * Strategy:
 *   - Open the saved-estimate URL.
 *   - Wait for the Export button to become enabled (signal that
 *     rehydration finished). Same probe csv-export.js uses.
 *   - Read the "Estimate summary" block at the top: three "X.XX USD"
 *     numbers in order (Upfront, Monthly, 12-month).
 *   - Read the Detailed Estimate table rows. Each row has cells in
 *     order: Service | Upfront | Monthly | Description | Region |
 *     Config Summary. Empty config cells render as "-" and we
 *     normalize those to null.
 *
 * Returns:
 *   {
 *     monthlyCost:     number|null,
 *     monthlyByService: Map<string, number>,
 *     configByService:  Map<string, string|null>,
 *   }
 *
 * The Config Summary mirrors what the rehydrated estimate exposes —
 * which is generally narrower than what was sent (the calculator
 * filters by displayInConfigSummary in the PCT). Pair with
 * lib/handler-helpers.js#predictSummaries for "what should surface"
 * to detect drift.
 *
 * ~5-7s end-to-end, vs ~12s for the CSV download flow. Same
 * Playwright dep — the constraint is "the calculator's pricing math
 * runs in the browser" (the CSV is generated client-side too;
 * there's no server-side CSV endpoint to fetch).
 */

let chromium;
try { chromium = require('playwright').chromium; } catch { chromium = null; }

const NAVIGATION_TIMEOUT_MS = 60_000;
const EXPORT_VISIBLE_TIMEOUT_MS = 30_000;
// Same polling cadence as csv-export.js — empirically settled after
// false-positive Read-only verdicts under concurrency-3 load.
const EXPORT_ENABLED_TIMEOUT_MS = 20_000;
const EXPORT_ENABLED_POLL_MS = 250;

const EXPORT_SELECTORS = [
  'button:has-text("Export")',
  'button:has-text("Export estimate")',
  'a:has-text("Export")',
  '[data-testid*="export"]',
  '[aria-label*="Export"]',
];

async function fetchCostFromDOM(url) {
  if (!chromium) {
    throw new Error('Playwright is not installed. Run: npm install --save-dev playwright && npx playwright install chromium');
  }

  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
    });
    try {
      const page = await context.newPage();
      await page.goto(url, { waitUntil: 'networkidle', timeout: NAVIGATION_TIMEOUT_MS });
      // Saved read-only views can show zero in subservice rows (S3, ALB,
      // SNS) while the summary includes their cost. Rehydrate the editable
      // view locally to read current prices and configuration summaries.
      const update = page.getByRole('button', { name: 'Update estimate button', exact: true });
      // The saved estimate mounts this control after navigation/networkidle.
      // An immediate visibility check intermittently skips recalculation and
      // returns stale zero subservice rows against a nonzero summary.
      const canUpdate = await update.waitFor({state:'visible',timeout:15000}).then(()=>true,()=>false);
      if (canUpdate) {
        await update.click();
        await page.waitForLoadState('networkidle');
      }

      const exportSelector = await firstVisible(page, EXPORT_SELECTORS, EXPORT_VISIBLE_TIMEOUT_MS);
      if (!exportSelector) {
        throw new Error('Export button not found on page');
      }

      // Polling for enabled-state distinguishes "still rehydrating"
      // from "rehydration failed" (the eC2Next read-only trap).
      const enabled = await waitForExportEnabled(page, exportSelector);
      if (!enabled) {
        throw new Error('rehydration failed: calculator disabled the Export button (estimate is in Read-only mode)');
      }

      // Five "<n.nn> USD" matches expected in order:
      //   [0] summary upfront cost
      //   [1] summary monthly cost     ← what we want
      //   [2] summary 12-month total
      //   [3..] per-service row costs (upfront/monthly pairs)
      const usdLocators = await page.locator('text=/USD/').all();
      const usdTexts = await Promise.all(usdLocators.map(l => l.innerText()));

      const monthlyCost = usdTexts.length >= 2
        ? parseUsd(usdTexts[1])
        : null;

      // Per-service: walk the Detailed Estimate rows. Header order is
      // observed empirically as `Service | Upfront | Monthly |
      // Description | Region | Config Summary`. We anchor on the first
      // USD cell rather than column index so an upstream column-order
      // change won't silently drop the wrong values — the row layout
      // hasn't changed since 2026-05 but we don't trust it.
      const detailedRows = [];
      for (let pageNumber = 0; pageNumber < 100; pageNumber++) {
        const rows = await page.locator('tr, [role="row"]').all();
        for (const row of rows) {
          const cells = await row.locator('td, [role="cell"]').all().catch(() => []);
          if (cells.length < 6) continue;
          detailedRows.push(await Promise.all(cells.map(c => c.innerText().catch(() => ''))));
        }
        const next = page.getByRole('button', { name: 'Next page', exact: true });
        if (!await next.isVisible().catch(() => false) || await next.isDisabled()) break;
        const before = await page.locator('table').innerText();
        await next.click();
        await page.waitForFunction(old => document.querySelector('table')?.innerText !== old, before);
      }

      const { monthlyByService, configByService, configurationCount } = summarizeDetailedRows(detailedRows);
      const subtotal = [...monthlyByService.values()].reduce((sum, cost) => sum + cost, 0);
      // Never publish a zero summary while priced service rows show a positive total.
      // Treat disagreement as an extraction failure, rather than guessing which DOM
      // number represents the full estimate.
      if (monthlyCost === null || monthlyCost <= 0 || Math.abs(subtotal - monthlyCost) > Math.max(0.02, configurationCount * 0.005)) {
        return { monthlyCost: null, monthlyByService, configByService,
          error: 'Calculator total was zero, missing, or inconsistent with service rows',
          diagnostics: { summaryMonthlyCost: monthlyCost, serviceSubtotal: subtotal, serviceCount: monthlyByService.size } };
      }
      return { monthlyCost, monthlyByService, configByService };
    } finally {
      await context.close();
    }
  } finally {
    await browser.close();
  }
}

function summarizeDetailedRows(rows) {
  const monthlyByService = new Map();
  const summaries = new Map();
  let configurationCount = 0;
  for (const cells of rows) {
    // Editable tables can insert an empty support column before Upfront.
    const firstUsdIdx = cells.findIndex(text => /USD/.test(text));
    if (firstUsdIdx < 1 || !/USD/.test(cells[firstUsdIdx + 1] || '')) continue;
    const service = cells.slice(0, firstUsdIdx).map(text => text.trim()).find(text => text && text !== '-');
    const monthly = parseUsd(cells[firstUsdIdx + 1]);
    if (!service || !Number.isFinite(monthly)) continue;
    const description = (cells[firstUsdIdx + 2] || '').trim();
    const rawConfig = (cells[firstUsdIdx + 4] || '').trim();
    const summary = rawConfig && rawConfig !== '-' ? rawConfig : null;
    monthlyByService.set(service, (monthlyByService.get(service) || 0) + monthly);
    if (!summaries.has(service)) summaries.set(service, []);
    summaries.get(service).push({ description, summary });
    configurationCount++;
  }
  // Preserve the original single-row string/null contract. Repeated rows
  // carry the calculator description so identical summaries remain distinct.
  const configByService = new Map();
  for (const [service, configs] of summaries) {
    const summary = configs.length === 1 ? configs[0].summary : configs.map((config, index) => {
      const label = config.description && config.description !== '-' ? config.description : `Configuration ${index + 1}`;
      return `${label}: ${config.summary || '-'}`;
    }).join('\n');
    configByService.set(service, summary);
  }
  return { monthlyByService, configByService, configurationCount };
}

async function firstVisible(page, selectors, timeoutMs) {
  // isVisible() returns immediately; its timeout option does not wait for SPA
  // hydration. Wait for any supported control under one shared deadline.
  try {
    return await Promise.any(selectors.map(async sel => {
      await page.locator(sel).first().waitFor({state:'visible',timeout:timeoutMs || 30000});
      return sel;
    }));
  } catch { return null; }
}

async function waitForExportEnabled(page, exportSelector) {
  const locator = page.locator(exportSelector).first();
  const deadline = Date.now() + EXPORT_ENABLED_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const disabled = await locator.isDisabled().catch(() => true);
    if (!disabled) return true;
    await page.waitForTimeout(EXPORT_ENABLED_POLL_MS);
  }
  return false;
}

function parseUsd(text) {
  if (typeof text !== 'string') return null;
  const m = text.match(/([\d,]+(?:\.\d+)?)/);
  if (!m) return null;
  const n = Number(m[1].replace(/,/g, ''));
  return Number.isFinite(n) ? n : null;
}

module.exports = { fetchCostFromDOM, parseUsd, summarizeDetailedRows };
