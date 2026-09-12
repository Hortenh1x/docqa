/* Run against a local UI build. All API traffic is intercepted; no providers run.
 * DOCQA_PLAYWRIGHT=/path/to/playwright DOCQA_UI_URL=http://127.0.0.1:18124 \
 *   node ui/tests/browser-regressions.cjs
 * Set DOCQA_DEMO=true for a build with NEXT_PUBLIC_DEMO_MODE=true and a demo key.
 */
const assert = require('node:assert/strict');
const { chromium } = require(process.env.DOCQA_PLAYWRIGHT || process.env.PLAYWRIGHT_MODULE || 'playwright');

const base = process.env.DOCQA_UI_URL || 'http://127.0.0.1:18124';
assert(['localhost', '127.0.0.1'].includes(new URL(base).hostname), 'Use a local UI only');
const demo = process.env.DOCQA_DEMO === 'true';
const cid = '11111111-1111-4111-8111-111111111111';
const otherCid = '33333333-3333-4333-8333-333333333333';
const did = '22222222-2222-4222-8222-222222222222';
const keyA = 'synthetic-tenant-a';
const keyB = 'synthetic-tenant-b';
const collection = (tenant) => ({
  id: tenant === 'B' ? otherCid : cid, name: `Tenant ${tenant}`, slug: 'sandbox',
  embedding_model: 'stub@1024', read_only: false, access_labels: [],
  document_count: 1, suggested_questions: [], created_at: '2026-09-10T00:00:00Z',
});
const document = (tenant) => ({
  id: did, collection_id: collection(tenant).id, filename: `tenant-${tenant}.md`,
  mime_type: 'text/markdown', size_bytes: 100, sha256: '0'.repeat(64),
  status: 'ready', error: null, page_count: null, access_labels: [],
  created_at: '2026-09-10T00:00:00Z', processed_at: '2026-09-10T00:00:01Z',
});
const source = {
  n: 1, document_id: did, filename: 'tenant-A.md', pages: [1, 1], section: 'Policy',
  snippet: 'Tenant A private passage', score: 0.9, access_label: 'all',
};
const access = {
  role: 'employee', hidden_passages: 0, hidden_labels: [], hidden_documents: 0,
  hidden_outranking: 0, hidden_truncated: false,
};
const done = {
  answer: 'Tenant A private answer [1]', refused: false, reason: null, confidence: 0.9,
  usage: { prompt_tokens: 12, completion_tokens: 7, cost_usd: 0 },
  latency_ms: 1, model: 'stub',
};
const sse = [
  ['meta', { query_id: did, access }], ['sources', { sources: [source] }],
  ['delta', { text: done.answer }], ['done', done],
].map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('');

async function fixture(browser, options = {}) {
  const context = await browser.newContext({ viewport: { width: options.width || 1280, height: 900 } });
  // Observe actual browser fetch rejections/XHR abort events without recording credentials.
  await context.addInitScript(() => {
    window.abortedRequests = [];
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {
      try { return await originalFetch(...args); }
      catch (error) {
        if (error.name === 'AbortError') window.abortedRequests.push(String(args[0]));
        throw error;
      }
    };
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
      this.addEventListener('abort', () => window.abortedRequests.push(String(url)));
      return originalOpen.call(this, method, url, ...rest);
    };
  });
  const state = { requests: [], errors: [], hold: null, held: [], deleteFails: true, deleted: false, restricted: false, notReady: null };
  await context.route('**/*', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    if (!url.pathname.startsWith('/v1/')) {
      if (url.origin === new URL(base).origin) return route.continue();
      return route.abort(); // No third-party requests, even if the build is misconfigured.
    }
    const headers = {
      'access-control-allow-origin': '*', 'access-control-allow-headers': '*',
      'access-control-allow-methods': 'GET, POST, DELETE, OPTIONS',
      'access-control-expose-headers': 'X-Total-Count', 'X-Total-Count': state.deleted ? '0' : '1',
    };
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 200, headers });
    const tenant = req.headers().authorization === `Bearer ${keyB}` ? 'B' : 'A';
    state.requests.push({ path: url.pathname, method: req.method(), tenant, authorization: req.headers().authorization });
    if (state.hold?.(req, url)) {
      await new Promise(resolve => state.held.push(resolve));
    }
    let body = {};
    let status = 200;
    if (url.pathname === '/v1/collections') body = [collection(tenant)];
    else if (url.pathname === '/v1/roles') body = [
      { role: 'employee', labels: ['all'], default: true, description: 'Employee' },
      { role: 'finance', labels: ['all', 'finance'], default: false, description: 'Finance' },
    ];
    else if (url.pathname.endsWith('/ingest-status')) body = {
      pending: 0, processing: 0, ready: 1, failed: 0, embedded_tokens: 20,
      embedding_model: 'stub@1024', price_per_1m_tokens: null, embedding_cost_usd: null,
      eta_seconds: null, suggested_questions: [], access: { chunks_by_label: { all: 1 }, restricted_chunks: 0 },
    };
    else if (url.pathname.endsWith('/documents') && req.method() === 'POST') {
      status = 413;
      body = { code: 'payload_too_large', detail: `File exceeds the ${demo ? '5' : '25'} MB upload limit.` };
    } else if (url.pathname.endsWith('/documents')) body = state.deleted ? [] : [document(tenant)];
    else if (url.pathname.endsWith('/file')) {
      if (state.notReady) {
        status = 409;
        body = { code: 'document_not_ready', document_status: state.notReady,
          detail: 'The original file is available only after successful processing and access classification.' };
      } else if (state.restricted && url.searchParams.get('role') === 'employee') {
        status = 403;
        body = { code: 'document_restricted', detail: 'This document contains restricted sections.' };
      } else {
        return route.fulfill({ status: 200, headers, contentType: 'text/markdown',
          body: `Tenant ${tenant} private file\n<img src=x onerror="window.xss=true">\n<script>window.xss=true</script>` });
      }
    } else if (req.method() === 'DELETE') {
      status = state.deleteFails ? 503 : 204;
      body = { code: 'unavailable', detail: 'Storage is temporarily unavailable. Try again.' };
      if (!state.deleteFails) state.deleted = true;
    } else if (url.pathname === '/v1/query') {
      return route.fulfill({ status: 200, headers, contentType: 'text/event-stream', body: sse });
    } else if (url.pathname === '/v1/usage') body = {
      days: 30, queries: tenant === 'A' ? 91 : 2, refused: 0, prompt_tokens: 0,
      completion_tokens: 0, cost_usd: 0, avg_latency_ms: 0, daily: [],
    };
    await route.fulfill({ status, headers, contentType: 'application/json', body: status === 204 ? '' : JSON.stringify(body) });
  });
  const page = await context.newPage();
  if (options.time) await page.clock.install({ time: new Date(options.time) });
  page.on('pageerror', error => state.errors.push(error.message));
  await page.goto(base + (options.path || '/'));
  await page.getByLabel('Collection', { exact: true }).selectOption(cid);
  return { page, state, context, close: async () => {
    for (const resolve of state.held) resolve();
    await context.close();
    assert.deepEqual(state.errors, [], 'No uncaught page errors');
  } };
}

async function useKey(page, key) {
  await page.getByRole('button', { name: /^(set API key|change key)$/ }).click();
  await page.getByLabel('API key (kept in memory only)').fill(key);
  await page.getByRole('button', { name: 'use', exact: true }).click();
  await page.getByRole('button', { name: 'change key', exact: true }).waitFor({ timeout: 4000 });
}

async function ask(page) {
  await page.getByLabel('Your question').fill('Private tenant question');
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await page.getByRole('button', { name: 'Source 1: tenant-A.md, pages 1–1', exact: true }).waitFor();
}

async function checkFocus(locator) {
  assert.equal(await locator.evaluate(el => el === document.activeElement), true, 'Focus returns to the opener');
}

const tests = [];
function test(name, run) { tests.push({ name, run }); }

if (!demo) {
  test('keyless reload never restores a previous tenant answer', async (browser) => {
    const f = await fixture(browser);
    try {
      await ask(f.page);
      await f.page.waitForFunction(() => sessionStorage.getItem('docqa.ask')?.includes('Tenant A private answer'));
      await f.page.reload();
      await f.page.getByRole('heading', { name: 'Ask the documents.' }).waitFor({ timeout: 4000 });
      assert.equal(await f.page.getByText('Tenant A private answer', { exact: false }).count(), 0);
      assert.equal(await f.page.evaluate(() => sessionStorage.getItem('docqa.ask')), null);
      assert.equal(await f.page.evaluate(() => document.body.textContent.includes('Tenant A private answer')), false);
    } finally { await f.close(); }
  });

  test('API key survives submit, resets tenant state/cache, stays out of storage and is lost on reload', async (browser) => {
    const f = await fixture(browser);
    try {
      const { page, state } = f;
      let navigations = 0;
      page.on('framenavigated', frame => { if (frame === page.mainFrame()) navigations++; });
      await useKey(page, keyA);
      await page.waitForFunction(() => document.querySelector('select[aria-label="Collection"]')?.textContent.includes('Tenant A'));
      assert(state.requests.some(r => r.path === '/v1/collections' && r.authorization === `Bearer ${keyA}`));
      assert.equal(navigations, 0, 'Submitting the key must not reload the page');
      await ask(page);
      await page.waitForFunction(() => sessionStorage.getItem('docqa.ask')?.includes('Tenant A private answer'));
      await page.getByLabel('Access role').selectOption('finance');
      await page.getByRole('link', { name: 'Library', exact: true }).click();
      await page.getByRole('button', { name: 'tenant-A.md', exact: true }).click();
      await page.locator('pre').waitFor();
      await page.keyboard.press('Escape');
      await page.getByRole('link', { name: 'Usage', exact: true }).click();
      await page.getByText('91', { exact: true }).waitFor();
      await useKey(page, keyB);
      await page.getByText('2', { exact: true }).waitFor();
      assert.equal(await page.getByText('91', { exact: true }).count(), 0, 'Old usage cache is gone');
      assert.equal(await page.getByLabel('Access role').inputValue(), 'employee');
      assert.equal(await page.getByLabel('Collection', { exact: true }).inputValue(), otherCid);
      const storage = await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }));
      assert(!JSON.stringify(storage).includes(keyA) && !JSON.stringify(storage).includes(keyB), 'Keys never persist');
      assert.equal(storage.session['docqa.ask'], undefined);
      assert.equal(storage.session['docqa.collection'], undefined);
      assert.equal(storage.session['docqa.role'], undefined);
      await page.getByRole('link', { name: 'Ask', exact: true }).click();
      await page.getByRole('heading', { name: 'Ask the documents.' }).waitFor();
      assert.equal(await page.getByText('Private tenant question', { exact: true }).count(), 0);
      await page.getByRole('link', { name: 'Library', exact: true }).click();
      await page.getByRole('button', { name: 'tenant-B.md', exact: true }).click();
      await page.getByText('Tenant B private file', { exact: false }).waitFor();
      assert.equal(await page.getByText('Tenant A private file', { exact: false }).count(), 0);
      await page.reload();
      await page.getByRole('button', { name: 'set API key', exact: true }).waitFor();
    } finally { await f.close(); }
  });

  for (const kind of ['file', 'query', 'upload']) {
    test(`changing API key aborts a pending ${kind} request and discards its result`, async (browser) => {
      const f = await fixture(browser);
      try {
        const { page, state } = f;
        await useKey(page, keyA);
        state.hold = (req, url) => kind === 'file' ? url.pathname.endsWith('/file')
          : kind === 'query' ? url.pathname === '/v1/query'
          : req.method() === 'POST' && url.pathname.endsWith('/documents');
        if (kind === 'query') {
          await page.getByLabel('Your question').fill('Private pending question');
          await page.getByRole('button', { name: 'Ask', exact: true }).click();
        } else {
          await page.getByRole('link', { name: 'Library', exact: true }).click();
          if (kind === 'file') await page.getByRole('button', { name: 'tenant-A.md', exact: true }).click();
          else await page.locator('input[type=file]').setInputFiles({ name: 'pending.md', mimeType: 'text/markdown', buffer: Buffer.from('test') });
        }
        await page.waitForTimeout(100);
        assert.equal(state.held.length, 1, 'The old request is still pending');
        // The reader is modal. Dismiss it before reaching the key field; its pending
        // request is still cached unless cancellation is implemented.
        if (kind === 'file') await page.keyboard.press('Escape');
        await useKey(page, keyB);
        await page.waitForFunction(() => window.abortedRequests.length > 0);
        const aborted = await page.evaluate(() => window.abortedRequests);
        assert(aborted.some(url => kind === 'file' ? url.includes('/file') : kind === 'query' ? url.includes('/query') : url.includes('/documents')));
        state.hold = null;
        state.held.splice(0).forEach(resolve => resolve());
        await page.waitForTimeout(100);
        assert.equal(await page.getByText('Private pending question', { exact: true }).count(), 0);
        assert.equal(await page.getByText('Tenant A private answer', { exact: false }).count(), 0);
        assert.equal(await page.evaluate(() => sessionStorage.getItem('docqa.ask')), null);
      } finally { await f.close(); }
    });
  }
} else {
  test('demo build authenticates with its baked-in key and hides key entry', async (browser) => {
    const f = await fixture(browser);
    try {
      assert.equal(await f.page.getByRole('button', { name: /^(set API key|change key)$/ }).count(), 0);
      assert(f.state.requests.filter(r => r.path === '/v1/collections').every(r => r.authorization && r.authorization !== 'Bearer'));
      await ask(f.page);
      await f.page.reload();
      await f.page.getByRole('button', { name: 'Source 1: tenant-A.md, pages 1–1', exact: true }).waitFor();
    } finally { await f.close(); }
  });

  for (const legacy of [false, true]) {
    test(`demo reload discards ${legacy ? 'legacy undated' : 'previous UTC day'} saved answers`, async (browser) => {
      const f = await fixture(browser, { time: '2026-09-10T23:59:00Z' });
      try {
        await ask(f.page);
        await f.page.waitForFunction(() => sessionStorage.getItem('docqa.ask')?.includes('Tenant A private answer'));
        if (legacy) {
          await f.page.evaluate(() => {
            const saved = JSON.parse(sessionStorage.getItem('docqa.ask'));
            sessionStorage.setItem('docqa.ask', JSON.stringify(saved.state || saved));
          });
        } else await f.page.clock.setSystemTime(new Date('2026-09-11T00:01:00Z'));
        await f.page.reload();
        await f.page.getByRole('heading', { name: 'Ask the documents.' }).waitFor({ timeout: 4000 });
        assert.equal(await f.page.evaluate(() => sessionStorage.getItem('docqa.ask')), null);
      } finally { await f.close(); }
    });
  }
}

for (const wakeup of ['timer', 'visibility', 'interaction']) {
  test(`open Ask expires at UTC midnight on ${wakeup}`, async (browser) => {
    const f = await fixture(browser, { time: '2026-09-10T23:59:00Z' });
    try {
      await ask(f.page);
      await f.page.waitForFunction(() => sessionStorage.getItem('docqa.ask')?.includes('Tenant A private answer'));
      if (wakeup === 'timer') await f.page.clock.fastForward(61000);
      else {
        // A suspended tab can miss timers. The first visibility/interaction event
        // must discard yesterday's answer before the user continues.
        await f.page.clock.setSystemTime(new Date('2026-09-11T00:01:00Z'));
        if (wakeup === 'visibility') await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
        else await f.page.getByLabel('Your question').click();
      }
      await f.page.getByRole('heading', { name: 'Ask the documents.' }).waitFor({ timeout: 4000 });
      assert.equal(await f.page.evaluate(() => sessionStorage.getItem('docqa.ask')), null);
      assert.equal(await f.page.evaluate(() => document.body.textContent.includes('Tenant A private answer')), false);
    } finally { await f.close(); }
  });
}

for (const width of [390, 1280]) {
  test(`reader returns focus for Escape, close and backdrop at ${width}px`, async (browser) => {
    const f = await fixture(browser, { width, path: '/library' });
    try {
      const { page } = f;
      const trigger = page.getByRole('button', { name: 'tenant-A.md', exact: true });
      for (const dismiss of ['Escape', 'close', 'backdrop']) {
        await trigger.focus();
        await page.keyboard.press('Enter');
        await page.locator('pre').waitFor();
        assert.equal(await page.evaluate(() => !!window.xss), false, 'File markup stays literal text');
        const dialog = page.getByRole('dialog');
        await checkFocus(dialog.getByRole('button', { name: 'Close', exact: true }));
        await page.keyboard.press('Tab');
        await checkFocus(dialog.getByRole('link', { name: 'Download', exact: true }));
        await page.keyboard.press('Shift+Tab');
        if (dismiss === 'Escape') await page.keyboard.press('Escape');
        else if (dismiss === 'close') await dialog.getByRole('button', { name: 'Close', exact: true }).click();
        else await page.getByRole('button', { name: 'Close reader', exact: true }).click({ position: { x: 5, y: 5 } });
        await dialog.waitFor({ state: 'detached' });
        await checkFocus(trigger);
      }
    } finally { await f.close(); }
  });

  test(`source drawer returns focus to citation and rail at ${width}px`, async (browser) => {
    const f = await fixture(browser, { width });
    try {
      const { page } = f;
      await ask(page);
      const triggers = [page.getByRole('button', { name: 'Source 1: tenant-A.md, pages 1–1', exact: true }), page.getByRole('listitem', { name: 'Source 1: tenant-A.md, pages 1–1', exact: true })];
      for (const trigger of triggers) {
        for (const dismiss of width < 1100 ? ['Escape', 'close', 'backdrop'] : ['Escape', 'close']) {
          await trigger.focus();
          await page.keyboard.press('Enter');
          const dialog = page.getByRole('dialog');
          await dialog.waitFor();
          await checkFocus(dialog.getByRole('button', { name: 'Close', exact: true }));
          await page.keyboard.press('Shift+Tab');
          await checkFocus(dialog.getByRole('button', { name: 'Copy citation', exact: true }));
          await page.keyboard.press('Tab');
          if (dismiss === 'Escape') await page.keyboard.press('Escape');
          else if (dismiss === 'close') await dialog.getByRole('button', { name: 'Close', exact: true }).click();
          else await page.getByRole('button', { name: 'Close source panel', exact: true }).click({ position: { x: 5, y: 5 } });
          await dialog.waitFor({ state: 'detached' });
          await checkFocus(trigger);
        }
      }
    } finally { await f.close(); }
  });
}

test('role change hides old reader text while pending and after a restricted response', async (browser) => {
  const f = await fixture(browser, { path: '/library' });
  try {
    const { page, state } = f;
    await page.getByLabel('Access role').selectOption('finance');
    await page.getByRole('button', { name: 'tenant-A.md', exact: true }).click();
    await page.locator('pre').waitFor();
    state.restricted = true;
    state.hold = (_, url) => url.pathname.endsWith('/file') && url.searchParams.get('role') === 'employee';
    // Programmatic selection simulates the existing top-bar role-switch behavior
    // while the document remains mounted.
    await page.getByLabel('Access role').selectOption('employee', { force: true });
    await page.getByText('Loading the file…', { exact: true }).waitFor();
    assert.equal(await page.locator('pre').count(), 0, 'No previous-role file text while pending');
    state.hold = null;
    state.held.splice(0).forEach(resolve => resolve());
    await page.getByRole('main').getByRole('alert').waitFor();
    assert.equal(await page.locator('pre').count(), 0, 'No previous-role file text after refusal');
    assert.equal(await page.getByRole('link', { name: 'Download', exact: true }).count(), 0);
  } finally { await f.close(); }
});

for (const status of ['pending', 'processing', 'failed']) {
  test(`reader explains ${status} document response without exposing the file`, async (browser) => {
    const f = await fixture(browser, { path: '/library' });
    try {
      f.state.notReady = status;
      await f.page.getByRole('button', { name: 'tenant-A.md', exact: true }).click();
      const message = status === 'failed'
        ? 'Processing failed. This file is unavailable. Check the document status for details.'
        : 'This document is still being processed. Close the reader and try again when its status is ready.';
      await f.page.getByRole('alert').filter({ hasText: message }).waitFor({ timeout: 4000 });
      assert.equal(await f.page.locator('pre').count(), 0);
      assert.equal(await f.page.getByRole('link', { name: 'Download', exact: true }).count(), 0);
    } finally { await f.close(); }
  });
}

test('delete cancellation sends nothing; failure is visible and Retry succeeds', async (browser) => {
  const f = await fixture(browser, { path: '/library' });
  try {
    const { page, state } = f;
    page.once('dialog', dialog => dialog.dismiss());
    await page.getByRole('button', { name: 'Delete tenant-A.md', exact: true }).click();
    assert.equal(state.requests.filter(r => r.method === 'DELETE').length, 0);
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: 'Delete tenant-A.md', exact: true }).click();
    const alert = page.getByRole('main').getByRole('alert');
    await alert.waitFor({ timeout: 4000 });
    assert((await alert.innerText()).includes('Storage is temporarily unavailable'));
    assert.equal(await page.getByRole('button', { name: 'tenant-A.md', exact: true }).count(), 1);
    state.deleteFails = false;
    await page.getByRole('button', { name: 'Retry delete tenant-A.md', exact: true }).click();
    await page.getByText('No documents yet.', { exact: true }).waitFor();
    assert.equal(state.requests.filter(r => r.method === 'DELETE').length, 2);
    assert.equal(await alert.count(), 0);
  } finally { await f.close(); }
});

test(`upload hint matches ${demo ? '5' : '25'} MB limit and server size error is visible`, async (browser) => {
  const f = await fixture(browser, { path: '/library' });
  try {
    const { page } = f;
    await page.getByText(`Drop PDF, DOCX, MD or TXT · up to ${demo ? '5' : '25'} MB`, { exact: true }).waitFor({ timeout: 4000 });
    await page.locator('input[type=file]').setInputFiles({ name: 'oversized.md', mimeType: 'text/markdown', buffer: Buffer.from('synthetic rejection') });
    const alert = page.getByRole('main').getByRole('alert');
    await alert.waitFor();
    assert.equal(await alert.innerText(), `File exceeds the ${demo ? '5' : '25'} MB upload limit.`);
    assert.equal(await page.getByRole('button', { name: 'Choose a file', exact: true }).isEnabled(), true);
  } finally { await f.close(); }
});

(async () => {
  const browser = await chromium.launch({ headless: true,
    executablePath: process.env.DOCQA_CHROMIUM || process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
  const results = [];
  try {
    for (const { name, run } of tests) {
      if (process.env.DOCQA_TEST_FILTER && !new RegExp(process.env.DOCQA_TEST_FILTER).test(name)) continue;
      try { await run(browser); results.push({ name, pass: true }); console.log(`PASS ${name}`); }
      catch (error) { results.push({ name, pass: false, error: error.stack }); console.error(`FAIL ${name}\n${error.stack}`); }
    }
  } finally { await browser.close(); }
  console.log(JSON.stringify({ demo, passed: results.filter(r => r.pass).length, total: results.length, results }, null, 2));
  if (results.some(r => !r.pass)) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
