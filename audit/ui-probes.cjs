/* UI diagnostics on an isolated production build; API responses are synthetic. */
const { chromium } = require(process.env.DOCQA_PLAYWRIGHT || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const out = path.resolve(process.argv[2] || 'audit/evidence/2026-09-10');
const base = process.env.DOCQA_UI_URL || 'http://127.0.0.1:18124';
const cid = '11111111-1111-4111-8111-111111111111';
const did = '22222222-2222-4222-8222-222222222222';
const results = { mode: 'production UI with synthetic API; not live-provider E2E', checks: [], errors: [] };
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.DOCQA_CHROMIUM || '/usr/bin/chromium' });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const keys = [];
    await context.route('http://127.0.0.1:18123/**', async route => {
      const req = route.request();
      const url = new URL(req.url());
      keys.push(req.headers().authorization === 'Bearer audit-synthetic-key');
      const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-expose-headers': 'X-Total-Count', 'X-Total-Count': '1' };
      if (req.method() === 'OPTIONS') return route.fulfill({ status: 200, headers });
      let body = {};
      if (url.pathname === '/v1/collections') body = [{ id: cid, name: 'Synthetic audit collection', slug: 'sandbox', embedding_model: 'stub@1024', read_only: false, access_labels: [], document_count: 1, suggested_questions: [], created_at: '2026-09-10T00:00:00Z' }];
      else if (url.pathname === '/v1/roles') body = [{ role: 'employee', labels: ['all'], default: true, description: 'Employee' }, { role: 'finance', labels: ['all', 'finance'], default: false, description: 'Finance' }];
      else if (url.pathname.endsWith('/ingest-status')) body = { pending: 0, processing: 0, ready: 1, failed: 0, embedded_tokens: 20, embedding_model: 'stub@1024', price_per_1m_tokens: null, embedding_cost_usd: null, eta_seconds: null, suggested_questions: [], access: { chunks_by_label: {all: 1}, restricted_chunks: 0 } };
      else if (url.pathname.endsWith('/documents')) body = [{ id: did, collection_id: cid, filename: 'audit.md', mime_type: 'text/markdown', size_bytes: 100, sha256: '0'.repeat(64), status: 'ready', error: null, page_count: null, access_labels: [], created_at: '2026-09-10T00:00:00Z', processed_at: '2026-09-10T00:00:01Z' }];
      else if (url.pathname.endsWith('/file')) return route.fulfill({ status: 200, headers, contentType: 'text/markdown', body: '# Synthetic file\n<img src=x onerror="window.auditXss=true">\n<script>window.auditXss=true</script>' });
      else if (url.pathname === '/v1/usage') body = { days: 30, totals: { queries: 0, refused: 0, prompt_tokens: 0, completion_tokens: 0, cost_usd: 0, avg_latency_ms: 0 }, daily: [], by_model: [] };
      await route.fulfill({ status: 200, headers, contentType: 'application/json', body: JSON.stringify(body) });
    });
    const page = await context.newPage();
    page.on('pageerror', err => results.errors.push(err.message));
    await page.goto(base);
    await page.getByLabel('Collection', {exact: true}).selectOption(cid);
    await page.getByRole('button', { name: 'set API key' }).click();
    await page.getByLabel('API key (kept in memory only)').fill('audit-synthetic-key');
    await Promise.all([page.waitForEvent('load'), page.getByRole('button', { name: 'use', exact: true }).click()]);
    await page.getByRole('button', { name: 'set API key' }).waitFor();
    results.checks.push({ id: 'key-lost-on-submit', expected: 'new key authenticates subsequent requests', actual: 'reload resets module memory and button returns to set API key', newKeyUsedInApiRequest: keys.some(Boolean) });
    assert.equal(keys.some(Boolean), false);
    for (const width of [320, 390, 768, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      for (const route of ['/', '/library']) {
        await page.goto(base + route);
        await page.getByLabel('Collection', {exact: true}).selectOption(cid);
        const dimensions = await page.evaluate(() => ({ viewport: innerWidth, scroll: document.documentElement.scrollWidth }));
        results.checks.push({ id: 'reflow', width, route, ...dimensions });
      }
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(base + '/library');
    await page.getByRole('button', { name: 'audit.md', exact: true }).click();
    await page.locator('pre').waitFor();
    results.checks.push({ id: 'text-xss', scriptExecuted: await page.evaluate(() => !!window.auditXss), literalMarkupShown: await page.locator('pre').textContent() });
    assert.equal(await page.evaluate(() => !!window.auditXss), false);
    await page.keyboard.press('Escape');
    await page.getByRole('dialog').waitFor({ state: 'detached' });
    results.checks.push({ id: 'reader-focus-return', expected: 'audit.md trigger', actual: await page.evaluate(() => ({ tag: document.activeElement.tagName, text: document.activeElement === document.body ? '(body)' : document.activeElement.textContent })) });
    await page.screenshot({ path: path.join(out, 'ui-library-mobile.png'), fullPage: true });
    const missing = await page.goto(base + '/audit-route-that-does-not-exist');
    results.checks.push({ id: 'unknown-route', status: missing.status(), text: await page.locator('body').innerText() });
    await page.goto(base);
    results.checks.push({ id: 'metadata', title: await page.title(), ogImage: await page.locator('meta[property="og:image"]').getAttribute('content') });
    results.checks.push({ id: 'storage', keys: await page.evaluate(() => ({ local: Object.keys(localStorage), session: Object.keys(sessionStorage) })) });
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(out, 'ui-probes.json'), JSON.stringify(results, null, 2) + '\n');
  }
  console.log(JSON.stringify(results, null, 2));
})().catch(e => { console.error(e); process.exitCode = 1; });
