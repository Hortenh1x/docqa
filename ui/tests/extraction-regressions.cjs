/* Real UI with synthetic API fixtures only; never contacts model providers. */
const assert = require('node:assert/strict');
const { chromium } = require(process.env.DOCQA_PLAYWRIGHT || 'playwright');
const { fixture } = require('./account-regressions.cjs');
const base = process.env.DOCQA_UI_URL || 'http://127.0.0.1:18126';
const own = '22222222-2222-4222-8222-222222222222';
const did = '33333333-3333-4333-8333-333333333333';
const sid = '44444444-4444-4444-8444-444444444444';
const eid = '55555555-5555-4555-8555-555555555555';
const stamp = '2026-09-29T00:00:00Z';
const tests = [];
const test = (name, run) => tests.push({ name, run });
async function setup(browser, width) {
  const f = await fixture(browser, { width, path: '/library', user: { id: 'user', email: 'a@example.test', email_verified: true, tenant_id: own } });
  f.state.failed = false;
  const state = { schemas: [], extractions: [], requests: [], failRun: false, failPatch: false };
  await f.context.route('**/v1/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname;
    if (!path.includes('/schemas') && !path.includes('/extractions')) return route.fallback();
    const headers = { 'access-control-allow-origin': new URL(base).origin, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'Content-Type, X-CSRF-Token', 'access-control-allow-methods': 'GET,POST,PATCH,DELETE,OPTIONS' };
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
    const body = req.postData() ? req.postDataJSON() : null;
    state.requests.push({ path, method: req.method(), body });
    if (req.method() !== 'GET') assert.equal(req.headers()['x-csrf-token'], 'csrf-user');
    const respond = (value, status = 200) => route.fulfill({ status, headers, contentType: 'application/json', body: JSON.stringify(value) });
    if (path.endsWith('/schemas/templates')) return respond([]);
    if (path === '/v1/schemas') {
      if (req.method() === 'POST') { state.schemas = [{ ...body, id: sid, extraction_count: 0, created_at: stamp, updated_at: stamp }]; return respond(state.schemas[0]); }
      return respond(state.schemas);
    }
    if (path === `/v1/schemas/${sid}`) { Object.assign(state.schemas[0], body); return respond(state.schemas[0]); }
    if (path === `/v1/documents/${did}/extractions`) {
      if (req.method() === 'POST') {
        if (state.failRun) return respond({ code: 'quota_exceeded', detail: 'Daily budget exhausted.' }, 429);
        state.extractions = [{ id: eid, schema_id: sid, document_id: did, status: 'ready', model: 'stub', fields: { total: { value: 450, confidence: .95, edited: false, evidence: { chunk_id: 5, chunk_index: 0, page: 1, start: 0, end: 22, quote: 'Private salary excerpt', bbox: null, page_size: null } } }, issues: [], prompt_tokens: 1, completion_tokens: 1, cost_usd: 0, error: null, created_at: stamp, updated_at: stamp }];
        return respond(state.extractions[0]);
      }
      return respond(state.extractions);
    }
    if (path === `/v1/extractions/${eid}` && req.method() === 'PATCH') {
      if (state.failPatch) return respond({ code: 'invalid_field_value', detail: 'Value correction was rejected.' }, 422);
      for (const [name, value] of Object.entries(body.values || {})) state.extractions[0].fields[name] = { value, edited: true, confidence: null, evidence: null };
      for (const name of body.clear || []) state.extractions[0].fields[name] = { value: null, edited: true, confidence: null, evidence: null };
      return respond(state.extractions[0]);
    }
    throw new Error(`Unexpected extraction request ${req.method()} ${path}`);
  });
  return { ...f, extractionState: state };
}
async function noOverflow(page, label) {
  const bounds = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
  assert(bounds.document <= bounds.viewport + 1, `${label}: horizontal overflow ${JSON.stringify(bounds)}`);
}
async function createSchema(f) {
  const page = f.page;
  await page.goto(base + '/schemas');
  await page.getByRole('button', { name: 'New schema', exact: true }).click();
  await page.getByLabel('Name', { exact: true }).fill('Invoice');
  await page.getByLabel('Field name', { exact: true }).fill('total');
  await page.getByLabel('Field type', { exact: true }).selectOption('number');
  await page.getByLabel('Field description', { exact: true }).fill('Invoice total as printed');
  await page.getByLabel('required', { exact: true }).check();
  await noOverflow(page, 'Schema editor');
  await page.getByRole('button', { name: 'Create schema', exact: true }).click();
  await page.getByRole('heading', { name: 'Invoice', exact: true }).waitFor();
  assert.equal(f.extractionState.schemas[0].fields[0].type, 'number');
  assert.equal(f.extractionState.schemas[0].fields[0].required, true);
}
for (const width of [320, 390, 1440]) test(`schemas and Fields create, edit, evidence and clear at ${width}px`, async browser => {
  const f = await setup(browser, width);
  try {
    await createSchema(f);
    await f.page.getByRole('button', { name: 'Edit', exact: true }).click();
    await f.page.getByLabel('Name', { exact: true }).fill('Invoice totals');
    await f.page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await f.page.getByRole('heading', { name: 'Invoice totals', exact: true }).waitFor();
    assert.equal(f.extractionState.schemas[0].name, 'Invoice totals');
    await noOverflow(f.page, 'Schema list');
    await f.page.goto(base + '/library');
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
    await f.page.getByRole('button', { name: 'Extract fields from Private salary.md', exact: true }).click();
    const dialog = f.page.getByRole('dialog');
    await dialog.getByRole('button', { name: 'Extract', exact: true }).click();
    await dialog.getByText('450', { exact: true }).waitFor();
    assert.deepEqual(f.extractionState.requests.find(r => r.path.endsWith('/extractions') && r.method === 'POST').body, { schema_id: sid, force: false });
    await noOverflow(f.page, 'Fields results');
    await dialog.getByRole('button', { name: 'Show in document (p. 1)', exact: true }).click();
    await dialog.locator('mark').filter({ hasText: 'Private salary excerpt' }).waitFor();
    await dialog.getByRole('button', { name: 'Fields', exact: true }).click();
    await dialog.getByRole('button', { name: 'Edit', exact: true }).click();
    await dialog.getByLabel('total value').fill('475.25');
    await dialog.getByRole('button', { name: 'Save', exact: true }).click();
    await dialog.getByText('475.25', { exact: true }).waitFor();
    assert.equal(f.extractionState.extractions[0].fields.total.value, 475.25);
    await dialog.getByText('Re-run keeps your edits.', { exact: false }).waitFor();
    await dialog.getByRole('button', { name: 'Clear', exact: true }).click();
    await dialog.getByText('—', { exact: true }).waitFor();
    assert.equal(f.extractionState.extractions[0].fields.total.value, null);
    await noOverflow(f.page, 'Fields edits');
  } finally { await f.close(); }
});

test('extraction and correction errors remain visible and permit retry', async browser => {
  const f = await setup(browser, 390);
  try {
    await createSchema(f);
    await f.page.goto(base + '/library');
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
    await f.page.getByRole('button', { name: 'Extract fields from Private salary.md', exact: true }).click();
    const dialog = f.page.getByRole('dialog');
    f.extractionState.failRun = true;
    await dialog.getByRole('button', { name: 'Extract', exact: true }).click();
    await dialog.getByRole('alert').filter({ hasText: 'Daily budget used.' }).waitFor();
    assert.equal(f.extractionState.extractions.length, 0);
    f.extractionState.failRun = false;
    await dialog.getByRole('button', { name: 'Extract', exact: true }).click();
    await dialog.getByText('450', { exact: true }).waitFor();
    await dialog.getByRole('button', { name: 'Edit', exact: true }).click();
    await dialog.getByLabel('total value').fill('475.25');
    f.extractionState.failPatch = true;
    await dialog.getByRole('button', { name: 'Save', exact: true }).click();
    await dialog.getByRole('alert').filter({ hasText: 'Value correction was rejected.' }).waitFor();
    assert.equal(await dialog.getByLabel('total value').inputValue(), '475.25');
    assert.equal(f.extractionState.extractions[0].fields.total.value, 450);
    f.extractionState.failPatch = false;
    await dialog.getByRole('button', { name: 'Save', exact: true }).click();
    await dialog.getByText('475.25', { exact: true }).waitFor();
    await noOverflow(f.page, 'Fields correction after retry');
  } finally { await f.close(); }
});


for (const [filename, mime, searchable, expected] of [
  ['scan.png', 'image/png', true, 'scan.pdf'],
  ['scan.jpeg', 'image/jpeg', true, 'scan.pdf'],
  ['scan.pdf', 'application/pdf', true, 'scan.pdf'],
]) test(`download filename matches PDF bytes for ${filename}`, async browser => {
  const f = await setup(browser, 390);
  try {
    const fileRequests = [];
    await f.context.route('**/v1/**', async route => {
      const req = route.request(), url = new URL(req.url());
      const headers = { 'access-control-allow-origin': new URL(base).origin, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'Content-Type, X-CSRF-Token', 'access-control-allow-methods': 'GET,OPTIONS', 'access-control-expose-headers': 'X-Total-Count', 'X-Total-Count': '1' };
      if (req.method() === 'OPTIONS') return route.fallback();
      if (url.pathname === `/v1/collections/${own}/documents`) return route.fulfill({ status: 200, headers, contentType: 'application/json', body: JSON.stringify([{ id: did, collection_id: own, filename, mime_type: mime, searchable_pdf: searchable, size_bytes: 100, sha256: '0'.repeat(64), status: 'ready', error: null, page_count: 1, access_labels: [], created_at: stamp, processed_at: stamp }]) });
      if (url.pathname === `/v1/documents/${did}/file`) {
        fileRequests.push(url.searchParams.get('variant'));
        return route.fulfill({ status: 200, headers, contentType: 'application/pdf', body: '%PDF-1.4\n% synthetic download fixture\n%%EOF' });
      }
      return route.fallback();
    });
    await f.page.goto(base + '/library');
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
    await f.page.getByRole('button', { name: filename, exact: true }).click();
    const link = f.page.getByRole('dialog').getByRole('link', { name: 'Download', exact: true });
    await link.waitFor();
    const declaredFilename = await link.getAttribute('download');
    assert.equal(declaredFilename, expected);
    // Headless shell downloads the PDF iframe as UUID.pdf before this click.
    // Correlate the event with this link, not that unrelated automatic download.
    const [download] = await Promise.all([
      f.page.waitForEvent('download', { predicate: item => item.suggestedFilename() === declaredFilename }),
      link.click(),
    ]);
    assert.equal(download.suggestedFilename(), expected);
    assert.deepEqual(fileRequests, [mime === 'application/pdf' ? null : 'searchable']);
  } finally { await f.close(); }
});

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.DOCQA_CHROMIUM || process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH, headless: true });
  let failed = 0;
  try { for (const t of tests) { try { await t.run(browser); console.log(`PASS ${t.name}`); } catch (e) { failed++; console.error(`FAIL ${t.name}\n${e.stack}`); } } }
  finally { await browser.close(); }
  console.log(JSON.stringify({ suite: 'extraction', failed, total: tests.length })); process.exitCode = failed ? 1 : 0;
})();
