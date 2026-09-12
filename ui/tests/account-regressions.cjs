/* Production browser tests; all API responses are local synthetic fixtures. */
const assert = require('node:assert/strict');
const { chromium } = require(process.env.DOCQA_PLAYWRIGHT || 'playwright');
const base = process.env.DOCQA_UI_URL || 'http://127.0.0.1:18126';
assert(['localhost', '127.0.0.1'].includes(new URL(base).hostname));
const pub = '11111111-1111-4111-8111-111111111111';
const own = '22222222-2222-4222-8222-222222222222';
const did = '33333333-3333-4333-8333-333333333333';
const password = 'Correct horse! maple river 7';
const collection = (id, privateData = false) => ({ id, name: privateData ? 'My documents' : 'Public policies', slug: privateData ? 'my-documents' : 'policies-en', embedding_model: 'stub@1024', read_only: !privateData, is_public: !privateData, owned: privateData, writable: privateData, access_labels: ['finance'], document_count: 1, suggested_questions: [{ question: 'What is the policy?', min_role: 'finance' }], created_at: '2026-09-10T00:00:00Z' });
async function fixture(browser, options = {}) {
  const resetAt = new Date();
  resetAt.setUTCHours(24, 0, 0, 0);
  const resetAtIso = resetAt.toISOString();
  const context = await browser.newContext({ viewport: { width: options.width || 1280, height: 900 } });
  context.setDefaultTimeout(7000);
  await context.addInitScript(() => {
    window.transport = []; window.revoked = []; window.abortedRequests = [];
    const f = window.fetch; window.fetch = async (input, init) => {
      window.transport.push({ path: String(input), credentials: init?.credentials });
      try { return await f(input, init); } catch (e) { if (e.name === 'AbortError') window.abortedRequests.push(String(input)); throw e; }
    };
    const send = XMLHttpRequest.prototype.send; XMLHttpRequest.prototype.send = function(body) {
      window.transport.push({ xhr: true, credentials: this.withCredentials });
      this.addEventListener('abort', () => window.abortedRequests.push('xhr'));
      return send.call(this, body);
    };
    const revoke = URL.revokeObjectURL; URL.revokeObjectURL = function(url) { window.revoked.push(url); revoke(url); };
  });
  const state = { user: options.user || null, requests: [], responses: [], errors: [], registration: options.registration !== false, remaining: '0.30', reserved: '0.00', invalid: false, failGuestSessionOnce: false, storageBytes: options.storageBytes ?? 100, storageError: false, failed: true, deleted: false, quota: false, sseQuota: false, hold: null, held: [] };
  const session = () => ({ user: state.user, csrf_token: state.user ? 'csrf-user' : 'csrf-guest', registration_available: state.registration, google_available: !!options.google });
  await context.route('**/*', async route => {
    const req = route.request(), url = new URL(req.url());
    if (!url.pathname.startsWith('/v1/')) return url.origin === new URL(base).origin ? route.continue() : route.abort();
    const headers = { 'access-control-allow-origin': new URL(base).origin, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'Content-Type, X-CSRF-Token', 'access-control-allow-methods': 'GET,POST,DELETE,OPTIONS', 'access-control-expose-headers': 'X-Total-Count,Retry-After', 'X-Total-Count': state.deleted ? '0' : '1' };
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
    state.requests.push({ path: url.pathname, search: url.search, method: req.method(), headers: req.headers(), body: req.postData() });
    const expectedCsrf = state.user ? 'csrf-user' : 'csrf-guest';
    if (state.hold?.(req, url)) await new Promise(resolve => state.held.push(resolve));
    const respond = (body, status = 200) => {
      state.responses.push({ path: url.pathname, status });
      return route.fulfill({ status, headers, contentType: 'application/json', body: status === 204 ? '' : JSON.stringify(body) });
    };
    if (state.invalid) { state.invalid = false; state.user = null; return respond({ code: 'invalid_session', detail: 'Session expired.' }, 401); }
    if (url.pathname === '/v1/auth/session') {
      if (!state.user && state.failGuestSessionOnce) {
        state.failGuestSessionOnce = false; state.responses.push({ path: url.pathname, status: 0 });
        return route.abort('failed');
      }
      return respond(session());
    }
    if (url.pathname === '/v1/site') return respond({ accounts_enabled: true, upload_max_mb: 5, operator_contact: 'operator@example.test', providers: [{ name: 'OpenAI', receives: 'Document text for embeddings.' }, { name: 'DeepSeek', receives: 'Question and retrieved passages.' }], purpose: 'Explore document Q&A.', document_privacy: 'Your documents are private to your account.' });
    if (req.method() !== 'GET') assert.equal(req.headers()['x-csrf-token'], expectedCsrf, 'Every mutation uses the current session CSRF token');
    assert.equal(req.headers().authorization, undefined, 'Account build never sends a bearer key');
    if (url.pathname === '/v1/auth/google/start') return options.googleError ? respond({ code: 'account_service_unavailable', detail: 'Google sign-in is temporarily unavailable.' }, 503) : respond({ authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?state=synthetic-google-state' });
    if (url.pathname === '/v1/auth/login') { const body = req.postDataJSON(); state.user = { id: body.email, email: body.email, email_verified: true, tenant_id: own }; return respond(session()); }
    if (url.pathname === '/v1/auth/logout') { state.user = null; return respond({}, 204); }
    if (url.pathname.startsWith('/v1/auth/')) {
      // Reset revokes signed-in sessions without clearing their cookie in its response.
      if (url.pathname.endsWith('/reset') && state.user) state.invalid = true;
      else if (url.pathname.endsWith('/verify') || url.pathname.endsWith('/reset')) state.user = null;
      return respond({ message: 'If eligible, an email has been sent.' }, url.pathname.endsWith('/register') || url.pathname.endsWith('/resend') || url.pathname.endsWith('/forgot-password') ? 202 : 200);
    }
    if (url.pathname === '/v1/storage') return state.storageError ? respond({ detail: 'Storage temporarily unavailable.' }, 503) : respond({ used_bytes: state.storageBytes, limit_bytes: 52428800, remaining_bytes: Math.max(0, 52428800 - state.storageBytes), document_count: state.deleted ? 0 : 8 });
    if (url.pathname === '/v1/budget') return respond({ enabled: true, limit_usd: '0.50', spent_usd: '0.20', reserved_usd: state.reserved, remaining_usd: state.remaining, limited_by: 'ip', reset_at: resetAtIso });
    if (url.pathname === '/v1/collections') return respond([...(options.publicCollections || [collection(pub)]), ...(state.user ? [{ ...collection(own, true), writable: state.user.email_verified }] : [])]);
    if (url.pathname === '/v1/roles') return respond([{ role: 'employee', labels: ['all'], default: true, description: 'Employee' }, { role: 'finance', labels: ['all', 'finance'], default: false, description: 'Finance' }]);
    if (url.pathname.endsWith('/ingest-status')) return respond({ pending: 0, processing: 0, ready: 1, failed: Number(state.failed), embedded_tokens: 1, embedding_model: 'stub', price_per_1m_tokens: null, embedding_cost_usd: null, eta_seconds: null, suggested_questions: [], access: { chunks_by_label: { finance: 1 }, restricted_chunks: 1 } });
    if (url.pathname.endsWith('/reprocess')) { if (state.quota) return respond({ code: 'quota_exceeded', detail: 'Daily budget exhausted.', reset_at: resetAtIso }, 429); state.failed = false; return respond({ id: did, status: 'pending' }, 202); }
    if (url.pathname.endsWith('/documents') && req.method() === 'POST') { state.storageBytes += 1024; return respond({ id: did, status: 'pending' }, 202); }
    if (url.pathname.endsWith('/documents')) return respond(state.deleted ? [] : [{ id: did, collection_id: own, filename: 'Private salary.md', mime_type: 'text/markdown', size_bytes: 100, sha256: '0'.repeat(64), status: state.failed ? 'failed' : 'ready', error: state.failed ? 'Daily budget exhausted. Retry after reset.' : null, page_count: 1, access_labels: ['historic-confidential'], created_at: '2026-09-10T00:00:00Z', processed_at: null }]);
    if (url.pathname.endsWith('/file')) return route.fulfill({ status: 200, headers, contentType: 'text/markdown', body: 'Private original salary text' });
    if (req.method() === 'DELETE') { state.deleted = true; state.storageBytes = 0; return options.deleteCommittedError ? respond({ code: 'storage_unavailable', detail: 'Original cleanup is temporarily unavailable.' }, 503) : respond({}, 204); }
    if (url.pathname === '/v1/query') {
      if (state.quota) return respond({ code: 'quota_exceeded', detail: 'Daily budget exhausted.', reset_at: resetAtIso }, 429);
      if (state.sseQuota) return route.fulfill({ status: 200, headers, contentType: 'text/event-stream', body: `event: error\ndata: ${JSON.stringify({ code: 'quota_exceeded', message: 'Daily budget exhausted.', reset_at: resetAtIso, retry_after_s: 1000 })}\n\n` });
      const answer = state.user ? 'Private salary answer [1]' : 'Public answer [1]';
      const frames = [['meta', { query_id: did, access: { role: state.user ? 'owner' : 'employee', hidden_passages: 0, hidden_labels: [] } }], ['sources', { sources: [{ n: 1, document_id: did, filename: 'Private salary.md', pages: [1,1], section: 'Salary', snippet: 'Private salary excerpt', score: 0.9, access_label: 'finance' }] }], ['delta', { text: answer }], ['done', { answer, refused: false, reason: null, confidence: 0.9, usage: { prompt_tokens: 1, completion_tokens: 1, cost_usd: 0 }, latency_ms: 1, model: 'stub' }]];
      return route.fulfill({ status: 200, headers, contentType: 'text/event-stream', body: frames.map(([event,data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('') });
    }
    if (url.pathname === '/v1/usage') return respond({ days: 30, queries: 1, refused: 0, prompt_tokens: 1, completion_tokens: 1, cost_usd: 0.2, avg_latency_ms: 1, daily: [] });
    return respond({});
  });
  const page = await context.newPage(); page.on('pageerror', e => state.errors.push(e.message));
  await page.goto(base + (options.path || '/'));
  return { page, context, state, resetAt: resetAtIso, close: async () => { state.held.forEach(r => r()); await context.close(); assert.deepEqual(state.errors, []); } };
}
async function login(page, email = 'a@example.test') {
  await page.getByRole('link', { name: 'Sign in', exact: true }).first().click();
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.getByText(email, { exact: true }).first().waitFor();
}
async function ask(page) {
  await page.getByLabel('Your question').fill('What is the salary?');
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await page.getByRole('button', { name: 'Source 1: Private salary.md, pages 1–1', exact: true }).waitFor();
}
const tests = [];
const test = (name, run) => tests.push({ name, run });
test('guest has public Ask, no upload, and 0.20 spend leaves 0.30 after login', async browser => {
  const f = await fixture(browser); try {
    await f.page.getByText('$0.30 remaining', { exact: false }).first().waitFor({ timeout: 3000 });
    await ask(f.page);
    await f.page.getByRole('link', { name: 'Library', exact: true }).click();
    assert.equal(await f.page.getByRole('button', { name: 'Choose a file' }).count(), 0);
    await login(f.page);
    await f.page.getByText('$0.30 remaining', { exact: false }).first().waitFor();
    await f.page.getByRole('link', { name: 'Library', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
    await f.page.getByRole('button', { name: 'Choose a file' }).waitFor();
    assert.equal(await f.page.getByLabel('Access role').count(), 0);
    await f.page.getByText('OpenAI', { exact: false }).first().waitFor();
    await f.page.getByText('DeepSeek', { exact: false }).first().waitFor();
    assert.equal(await f.page.getByText('wiped nightly', { exact: false }).count(), 0);
  } finally { await f.close(); }
});
test('verification and reset consume fragment, choose final password and require explicit login', async browser => {
  for (const action of ['verify', 'reset']) {
    const f = await fixture(browser, { path: `/account/${action}#token=synthetic-proof-012345678901234567890123456789` }); try {
      await f.page.getByLabel('New password', { exact: true }).fill(password);
      await f.page.getByLabel('Confirm password', { exact: true }).fill(password);
      assert.equal(new URL(f.page.url()).hash, '');
      await f.page.getByRole('button', { name: action === 'verify' ? 'Verify email and set password' : 'Reset password', exact: true }).click();
      await f.page.getByText('Sign in with your new password.', { exact: false }).first().waitFor();
      const req = f.state.requests.find(r => r.path === `/v1/auth/${action}`);
      assert.deepEqual(JSON.parse(req.body), { token: 'synthetic-proof-012345678901234567890123456789', password, password_confirmation: password });
      assert.equal(f.state.requests.some(r => r.search.includes('synthetic-proof-012345678901234567890123456789')), false);
      assert.equal(await f.page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }).includes('synthetic-proof-012345678901234567890123456789')), false);
    } finally { await f.close(); }
  }
});
test('owner can download failed historical-label original, retry, upload and delete with credentials', async browser => {
  const f = await fixture(browser); try {
    await login(f.page); await f.page.getByRole('link', { name: 'Library', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
    await f.page.getByText('Daily budget exhausted. Retry after reset.', { exact: true }).waitFor();
    await f.page.getByRole('button', { name: 'Private salary.md', exact: true }).click();
    await f.page.getByText('Private original salary text', { exact: false }).waitFor();
    await f.page.getByRole('link', { name: 'Download', exact: true }).waitFor();
    await f.page.keyboard.press('Escape');
    f.state.quota = true;
    await f.page.getByRole('button', { name: 'Retry processing Private salary.md', exact: true }).click();
    await f.page.getByRole('alert').filter({ hasText: 'UTC' }).waitFor();
    f.state.quota = false;
    await f.page.getByRole('button', { name: 'Retry processing Private salary.md', exact: true }).click();
    await f.page.locator('input[type=file]').setInputFiles({ name: 'safe.md', mimeType: 'text/markdown', buffer: Buffer.from('Safe example') });
    await f.page.waitForFunction(() => window.transport.some(t => t.xhr));
    assert.equal(await f.page.evaluate(() => window.transport.filter(t => t.xhr).every(t => t.credentials === true)), true);
    assert.equal(await f.page.evaluate(() => window.transport.filter(t => t.path?.includes('/v1/')).every(t => t.credentials === 'include')), true);
    f.page.once('dialog', d => d.accept());
    await f.page.getByRole('button', { name: 'Delete Private salary.md', exact: true }).click();
    await f.page.getByText('No documents yet.', { exact: true }).waitFor();
  } finally { await f.close(); }
});
test('logout clears private answers and readers across tabs, then account B starts fresh', async browser => {
  const f = await fixture(browser); try {
    await login(f.page); await f.page.getByRole('link', { name: 'Ask', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own); await ask(f.page);
    assert.equal(await f.page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }).includes('Private salary')), false);
    const second = await f.context.newPage(); await second.goto(base + '/library');
    await second.getByLabel('Collection', { exact: true }).selectOption(own);
    await second.getByRole('button', { name: 'Private salary.md', exact: true }).click();
    await second.getByText('Private original salary text', { exact: false }).waitFor();
    await f.page.getByRole('button', { name: 'Sign out', exact: true }).click();
    await f.page.getByRole('link', { name: 'Sign in', exact: true }).first().waitFor();
    await second.getByRole('link', { name: 'Sign in', exact: true }).first().waitFor();
    assert.equal(await second.getByRole('dialog').count(), 0);
    assert.equal(await second.evaluate(() => window.revoked.length > 0), true);
    assert.equal(await f.page.getByText('Private salary answer', { exact: false }).count(), 0);
    await login(f.page, 'b@example.test');
    await f.page.getByRole('link', { name: 'Ask', exact: true }).click();
    assert.equal(await f.page.getByText('Private salary answer', { exact: false }).count(), 0);
  } finally { await f.close(); }
});
test('expired session discards private state and explicitly obtains guest session', async browser => {
  const f = await fixture(browser); try {
    await login(f.page); await f.page.getByRole('link', { name: 'Ask', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own); await ask(f.page);
    const start = f.state.requests.length; f.state.invalid = true;
    await f.page.getByRole('link', { name: 'Usage', exact: true }).click();
    await f.page.getByRole('link', { name: 'Sign in', exact: true }).first().waitFor();
    await f.page.getByText('Your session expired', { exact: false }).waitFor();
    assert(f.state.requests.slice(start).some(r => r.path === '/v1/auth/session'));
    await f.page.getByRole('link', { name: 'Ask', exact: true }).click();
    assert.equal(await f.page.getByText('Private salary answer', { exact: false }).count(), 0);
  } finally { await f.close(); }
});
test('missing mail is honest, existing login works and narrow keyboard forms fit', async browser => {
  const f = await fixture(browser, { registration: false, width: 360 }); try {
    await f.page.getByRole('link', { name: 'Sign in', exact: true }).first().click();
    await f.page.getByText('Registration and password recovery are currently unavailable.', { exact: false }).waitFor();
    assert.equal(await f.page.getByRole('link', { name: 'Create account', exact: true }).count(), 0);
    await f.page.getByLabel('Email', { exact: true }).focus(); await f.page.keyboard.press('Tab');
    assert.equal(await f.page.getByLabel('Password', { exact: true }).evaluate(el => el === document.activeElement), true);
    assert.equal(await f.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await f.page.getByLabel('Email', { exact: true }).fill('a@example.test');
    await f.page.getByLabel('Password', { exact: true }).fill(password);
    await f.page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await f.page.getByText('a@example.test', { exact: true }).first().waitFor();
  } finally { await f.close(); }
});
test('registration, resend and recovery use neutral responses and keep passwords out of storage', async browser => {
  const f = await fixture(browser, { path: '/account/register' }); try {
    await f.page.getByLabel('Email', { exact: true }).fill('new@example.test');
    await f.page.getByLabel('Password', { exact: true }).fill(password);
    await f.page.getByLabel('Confirm password', { exact: true }).fill(password);
    await f.page.getByRole('button', { name: 'Create account', exact: true }).click();
    await f.page.getByText('If eligible, an email has been sent.', { exact: true }).waitFor();
    assert.equal(await f.page.getByRole('button', { name: 'Sign out', exact: true }).count(), 0);
    assert.equal(await f.page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }).includes('Correct horse')), false);
    for (const [action, button] of [['resend', 'Send verification email'], ['forgot-password', 'Send recovery email']]) {
      await f.page.goto(base + '/account/' + action);
      await f.page.getByLabel('Email', { exact: true }).fill('new@example.test');
      await f.page.getByRole('button', { name: button, exact: true }).click();
      await f.page.getByText('If eligible, an email has been sent.', { exact: true }).waitFor();
      assert.deepEqual(JSON.parse(f.state.requests.find(r => r.path === '/v1/auth/' + action).body), { email: 'new@example.test' });
    }
  } finally { await f.close(); }
});
test('unverified accounts cannot upload or delete and can request verification', async browser => {
  const f = await fixture(browser, { path: '/library', user: { id: 'unverified', email: 'unverified@example.test', email_verified: false, tenant_id: own } }); try {
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
    await f.page.getByText('Verify your email before uploading', { exact: false }).waitFor();
    assert.equal(await f.page.getByRole('button', { name: 'Choose a file' }).count(), 0);
    assert.equal(await f.page.getByRole('button', { name: 'Delete Private salary.md' }).count(), 0);
    await f.page.getByRole('link', { name: 'Resend verification email', exact: true }).click();
    assert.equal(await f.page.getByLabel('Email', { exact: true }).inputValue(), 'unverified@example.test');
  } finally { await f.close(); }
});
test('HTTP and SSE budget exhaustion show the UTC reset and preserve guest spending at login', async browser => {
  for (const streaming of [false, true]) {
    const f = await fixture(browser); try {
      f.state.quota = !streaming; f.state.sseQuota = streaming; f.state.remaining = '0.00';
      await f.page.getByLabel('Your question').fill('Another question');
      await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
      await f.page.getByText('Daily budget used', { exact: true }).waitFor();
      await f.page.getByText('Your allowance resets', { exact: false }).waitFor();
      assert.equal(await f.page.getByRole('button', { name: 'Retry', exact: true }).isDisabled(), true);
      await login(f.page);
      await f.page.getByText('$0.00 remaining', { exact: false }).first().waitFor();
    } finally { await f.close(); }
  }
});
test('cross-tab logout aborts pending original fetch, upload XHR and query SSE requests', async browser => {
  for (const kind of ['file', 'upload', 'query']) {
    const f = await fixture(browser); try {
      await login(f.page);
      const other = await f.context.newPage(); await other.goto(base);
      await other.getByRole('button', { name: 'Sign out', exact: true }).waitFor();
      if (kind !== 'query') await f.page.getByRole('link', { name: 'Library', exact: true }).click();
      else await f.page.getByRole('link', { name: 'Ask', exact: true }).click();
      await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
      f.state.hold = (req, url) => kind === 'file' ? url.pathname.endsWith('/file') : kind === 'upload' ? url.pathname.endsWith('/documents') && req.method() === 'POST' : url.pathname === '/v1/query';
      if (kind === 'file') await f.page.getByRole('button', { name: 'Private salary.md', exact: true }).click();
      else if (kind === 'upload') await f.page.locator('input[type=file]').setInputFiles({ name: 'secret.md', mimeType: 'text/markdown', buffer: Buffer.from('Private draft') });
      else { await f.page.getByLabel('Your question').fill('Private draft question'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click(); }
      await f.page.waitForTimeout(200);
      assert(f.state.held.length > 0, 'The private request is in flight');
      await other.getByRole('button', { name: 'Sign out', exact: true }).click();
      await f.page.getByRole('link', { name: 'Sign in', exact: true }).first().waitFor();
      await f.page.waitForFunction(() => window.abortedRequests.length > 0);
      assert.equal(await f.page.getByRole('dialog').count(), 0);
      assert.equal(await f.page.getByText('Private draft question', { exact: true }).count(), 0);
      f.state.hold = null; f.state.held.forEach(resolve => resolve());
      await f.page.waitForTimeout(100);
      assert.equal(await f.page.getByText('Private salary answer', { exact: false }).count(), 0);
    } finally { await f.close(); }
  }
});
test('session refresh hides old private answer before a delayed session response', async browser => {
  const f = await fixture(browser); try {
    await login(f.page); await f.page.getByRole('link', { name: 'Ask', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own); await ask(f.page);
    f.state.hold = (_req, url) => url.pathname === '/v1/auth/session';
    await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await f.page.getByText('Checking your session…', { exact: true }).waitFor();
    assert.equal(await f.page.getByText('Private salary answer', { exact: false }).count(), 0);
    f.state.hold = null; f.state.held.forEach(resolve => resolve());
    await f.page.getByRole('heading', { name: 'Ask the documents.' }).waitFor();
    assert.equal(await f.page.getByLabel('Your question').inputValue(), '');
  } finally { await f.close(); }
});
test('mutation preflight detects another account and never sends the old upload', async browser => {
  const f = await fixture(browser); try {
    await login(f.page); await f.page.getByRole('link', { name: 'Library', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
    const count = f.state.requests.filter(r => r.path.endsWith('/documents') && r.method === 'POST').length;
    f.state.user = { id: 'b@example.test', email: 'b@example.test', email_verified: true, tenant_id: own };
    await f.page.locator('input[type=file]').setInputFiles({ name: 'a-private.md', mimeType: 'text/markdown', buffer: Buffer.from('Account A private file') });
    await f.page.getByText('b@example.test', { exact: true }).first().waitFor();
    assert.equal(f.state.requests.filter(r => r.path.endsWith('/documents') && r.method === 'POST').length, count);
    assert.equal(await f.page.getByText('a-private.md', { exact: true }).count(), 0);
  } finally { await f.close(); }
});
test('mobile private source keeps keyboard focus and fits the viewport', async browser => {
  const f = await fixture(browser, { width: 360 }); try {
    await login(f.page); await f.page.getByRole('link', { name: 'Ask', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own); await ask(f.page);
    await f.page.getByText('Private source', { exact: true }).waitFor();
    const source = f.page.getByRole('button', { name: 'Source 1: Private salary.md, pages 1–1', exact: true });
    await source.click(); await f.page.getByRole('dialog').waitFor();
    await f.page.getByText('Private · only your account', { exact: true }).waitFor();
    await f.page.keyboard.press('Escape');
    assert.equal(await source.evaluate(el => el === document.activeElement), true);
    assert.equal(await f.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await f.page.screenshot({ path: '/tmp/docqa-account-mobile.png' });
  } finally { await f.close(); }
});

test('verification and reset keep their in-memory proof and password after same-session tab return', async browser => {
  for (const action of ['verify', 'reset']) {
    const proof = 'synthetic-proof-012345678901234567890123456789';
    const f = await fixture(browser, { path: `/account/${action}#token=${proof}` }); try {
      await f.page.getByLabel('New password', { exact: true }).fill(password);
      await f.page.getByLabel('Confirm password', { exact: true }).fill(password);
      assert.equal(new URL(f.page.url()).hash, '');
      f.state.hold = (_req, url) => url.pathname === '/v1/auth/session';
      await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
      await f.page.getByText('Checking your session…', { exact: true }).waitFor();
      assert.equal(await f.page.getByLabel('New password', { exact: true }).isVisible(), false);
      f.state.hold = null; f.state.held.forEach(resolve => resolve());
      await f.page.getByLabel('New password', { exact: true }).waitFor();
      assert.equal(await f.page.getByLabel('New password', { exact: true }).inputValue(), password);
      await f.page.getByRole('button', { name: action === 'verify' ? 'Verify email and set password' : 'Reset password', exact: true }).click();
      await f.page.getByText('Sign in with your new password.', { exact: false }).first().waitFor();
      assert.deepEqual(JSON.parse(f.state.requests.find(r => r.path === `/v1/auth/${action}`).body), { token: proof, password, password_confirmation: password });
      assert.equal(await f.page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }).includes('synthetic-proof')), false);
    } finally { await f.close(); }
  }
});
test('proof forms are discarded when tab return finds an expired or different session', async browser => {
  for (const changed of ['expired', 'account']) {
    const f = await fixture(browser, { path: '/account/verify#token=synthetic-proof-012345678901234567890123456789' }); try {
      await f.page.getByLabel('New password', { exact: true }).fill(password);
      await f.page.getByLabel('Confirm password', { exact: true }).fill(password);
      if (changed === 'expired') f.state.invalid = true;
      else f.state.user = { id: 'new@example.test', email: 'new@example.test', email_verified: true, tenant_id: own };
      await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
      await f.page.getByText('This link is missing its token.', { exact: false }).waitFor();
      assert.equal(await f.page.getByLabel('New password', { exact: true }).count(), 0);
      assert.equal(f.state.requests.some(r => r.path === '/v1/auth/verify'), false);
    } finally { await f.close(); }
  }
});
test('Usage distinguishes settled daily spend and pending reservations from remaining allowance', async browser => {
  const f = await fixture(browser, { path: '/usage' }); try {
    f.state.reserved = '0.07'; f.state.remaining = '0.23';
    // Reload establishes one coherent daily fixture before any cached budget response.
    await f.page.reload();
    const daily = f.page.getByRole('region', { name: 'Daily budget', exact: true });
    await daily.waitFor();
    for (const [label, value] of [['Settled spend', '$0.20'], ['Pending reservations', '$0.07'], ['Remaining', '$0.23'], ['Daily limit', '$0.50']]) {
      await daily.getByText(label, { exact: true }).locator('..').getByText(value, { exact: true }).waitFor();
    }
    assert.equal(await daily.locator('time').getAttribute('datetime'), f.resetAt);
    assert.match(await daily.locator('time').innerText(), /UTC/);
    await login(f.page); await f.page.getByRole('link', { name: 'Usage', exact: true }).click();
    await f.page.getByRole('region', { name: 'Daily budget', exact: true }).getByText('Pending reservations', { exact: true }).locator('..').getByText('$0.07', { exact: true }).waitFor();
  } finally { await f.close(); }
});
test('signed-in password reset preserves confirmed success through revoked-cookie recovery', async browser => {
  const f = await fixture(browser, {
    path: '/account/reset#token=synthetic-proof-012345678901234567890123456789',
    user: { id: 'a@example.test', email: 'a@example.test', email_verified: true, tenant_id: own },
  }); try {
    await f.page.getByRole('button', { name: 'Sign out', exact: true }).waitFor();
    await f.page.getByLabel('New password', { exact: true }).fill(password);
    await f.page.getByLabel('Confirm password', { exact: true }).fill(password);
    await f.page.evaluate(() => {
      window.proofWarnings = [];
      new MutationObserver(() => {
        const text = document.body.innerText;
        if (text.includes('Your session expired') || text.includes('This link is missing its token.')) window.proofWarnings.push(text);
      }).observe(document.body, { childList: true, subtree: true, characterData: true });
    });
    await f.page.getByRole('button', { name: 'Reset password', exact: true }).click();
    await f.page.getByText('Password saved. Sign in with your new password.', { exact: true }).waitFor();
    await f.page.getByRole('link', { name: 'Sign in', exact: true }).first().waitFor();
    assert.deepEqual(f.state.responses.filter(r => r.path === '/v1/auth/session').slice(-2).map(r => r.status), [401, 200]);
    assert.equal(await f.page.getByText('Your session expired', { exact: false }).count(), 0);
    assert.equal(await f.page.getByText('This link is missing its token.', { exact: false }).count(), 0);
    assert.equal(await f.page.getByRole('link', { name: 'Request a new link', exact: true }).count(), 0);
    assert.deepEqual(await f.page.evaluate(() => window.proofWarnings), [], 'Successful reset must not flash an expired/missing-link state');
  } finally { await f.close(); }
});
test('confirmed password reset survives a failed guest-session bootstrap and retry', async browser => {
  const f = await fixture(browser, {
    path: '/account/reset#token=synthetic-proof-012345678901234567890123456789',
    user: { id: 'a@example.test', email: 'a@example.test', email_verified: true, tenant_id: own },
  }); try {
    await f.page.getByLabel('New password', { exact: true }).fill(password);
    await f.page.getByLabel('Confirm password', { exact: true }).fill(password);
    f.state.failGuestSessionOnce = true;
    await f.page.getByRole('button', { name: 'Reset password', exact: true }).click();
    await f.page.getByRole('button', { name: 'Retry session check', exact: true }).waitFor();
    assert.equal(await f.page.getByLabel('New password', { exact: true }).count(), 0);
    await f.page.getByRole('button', { name: 'Retry session check', exact: true }).click();
    await f.page.getByText('Password saved. Sign in with your new password.', { exact: true }).waitFor();
    assert.deepEqual(f.state.responses.filter(r => r.path === '/v1/auth/session').slice(-3).map(r => r.status), [401, 0, 200]);
    assert.equal(await f.page.getByText('Your session expired', { exact: false }).count(), 0);
    assert.equal(await f.page.getByText('This link is missing its token.', { exact: false }).count(), 0);
    assert.equal(await f.page.getByRole('link', { name: 'Request a new link', exact: true }).count(), 0);
    assert.equal(await f.page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }).includes('synthetic-proof')), false);
  } finally { await f.close(); }
});
test('a fresh proof fragment starts a new form after an earlier proof completed', async browser => {
  for (const action of ['verify', 'reset']) {
    const freshProof = 'synthetic-new-proof-012345678901234567890123456789';
    const f = await fixture(browser, { path: `/account/${action}#token=synthetic-proof-012345678901234567890123456789` }); try {
      await f.page.getByLabel('New password', { exact: true }).fill(password);
      await f.page.getByLabel('Confirm password', { exact: true }).fill(password);
      const submit = action === 'verify' ? 'Verify email and set password' : 'Reset password';
      await f.page.getByRole('button', { name: submit, exact: true }).click();
      await f.page.getByText('Password saved. Sign in with your new password.', { exact: true }).waitFor();
      await f.page.evaluate(proof => { window.location.hash = `token=${proof}`; }, freshProof);
      await f.page.getByLabel('New password', { exact: true }).waitFor();
      assert.equal(await f.page.getByLabel('New password', { exact: true }).inputValue(), '');
      assert.equal(await f.page.getByText('Password saved. Sign in with your new password.', { exact: true }).count(), 0);
      assert.equal(new URL(f.page.url()).hash, '');
      await f.page.getByLabel('New password', { exact: true }).fill(password);
      await f.page.getByLabel('Confirm password', { exact: true }).fill(password);
      await f.page.getByRole('button', { name: submit, exact: true }).click();
      await f.page.getByText('Password saved. Sign in with your new password.', { exact: true }).waitFor();
      assert.equal(JSON.parse(f.state.requests.filter(r => r.path === `/v1/auth/${action}`).at(-1).body).token, freshProof);
    } finally { await f.close(); }
  }
});
test('password confirmation blocks mismatches and accepts exactly eight characters', async browser => {
  for (const action of ['register', 'verify', 'reset']) {
    const proof = action !== 'register';
    const f = await fixture(browser, { width: 375, path: `/account/${action}${proof ? '#token=synthetic-proof-012345678901234567890123456789' : ''}` }); try {
      if (!proof) await f.page.getByLabel('Email', { exact: true }).fill('new@example.test');
      await f.page.getByLabel(proof ? 'New password' : 'Password', { exact: true }).fill('aaaaaaa1');
      await f.page.getByLabel('Confirm password', { exact: true }).fill('aaaaaaa2');
      const submit = action === 'register' ? 'Create account' : action === 'verify' ? 'Verify email and set password' : 'Reset password';
      await f.page.getByRole('button', { name: submit, exact: true }).click();
      await f.page.getByRole('alert').filter({ hasText: 'Passwords do not match' }).waitFor();
      assert.equal(f.state.requests.filter(r => r.path === `/v1/auth/${action}`).length, 0);
      await f.page.getByLabel('Confirm password', { exact: true }).fill('aaaaaaa1');
      await f.page.getByRole('button', { name: submit, exact: true }).click();
      await f.page.getByRole('status').filter({ hasText: proof ? 'Password saved' : 'If eligible' }).waitFor();
      const body = JSON.parse(f.state.requests.find(r => r.path === `/v1/auth/${action}`).body);
      assert.equal(body.password, 'aaaaaaa1'); assert.equal(body.password_confirmation, 'aaaaaaa1');
      assert.equal(await f.page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    } finally { await f.close(); }
  }
});
test('Google is hidden without credentials and enabled independently of SMTP', async browser => {
  const disabled = await fixture(browser, { path: '/account' }); try {
    await disabled.page.getByRole('heading', { name: 'Sign in', exact: true }).waitFor();
    assert.equal(await disabled.page.getByRole('button', { name: 'Continue with Google', exact: true }).count(), 0);
  } finally { await disabled.close(); }
  const f = await fixture(browser, { path: '/account/register', google: true, registration: false }); try {
    await f.context.route('https://accounts.google.com/**', route => route.fulfill({ contentType: 'text/html', body: '<h1>Local Google fixture</h1>' }));
    await f.page.getByRole('button', { name: 'Continue with Google', exact: true }).click();
    await f.page.getByRole('heading', { name: 'Local Google fixture' }).waitFor();
    const request = f.state.requests.find(r => r.path === '/v1/auth/google/start');
    assert.deepEqual(JSON.parse(request.body), { intent: 'login' });
    assert.equal(request.headers['x-csrf-token'], 'csrf-guest');
  } finally { await f.close(); }
});
test('signed-in accounts explicitly connect Google and start failures remain actionable', async browser => {
  const f = await fixture(browser, { path: '/account', google: true, googleError: true,
    user: { id: 'owner', email: 'owner@example.test', email_verified: true, tenant_id: own } }); try {
    const button = f.page.getByRole('button', { name: 'Connect Google', exact: true });
    await button.click();
    await f.page.getByRole('alert').filter({ hasText: 'Google sign-in is temporarily unavailable.' }).waitFor();
    assert.equal(await button.isEnabled(), true);
    const request = f.state.requests.find(r => r.path === '/v1/auth/google/start');
    assert.deepEqual(JSON.parse(request.body), { intent: 'link' });
    assert.equal(request.headers['x-csrf-token'], 'csrf-user');
  } finally { await f.close(); }
});
test('Google callback errors explain email collision without merging accounts', async browser => {
  const f = await fixture(browser, { path: '/account?google_error=email_exists', google: true }); try {
    await f.page.getByRole('alert').filter({ hasText: 'Sign in with your email and password' }).waitFor();
    assert.equal(f.state.user, null);
    assert.equal(f.state.requests.some(r => r.path === '/v1/auth/google/start'), false);
  } finally { await f.close(); }
});
test('a newer proof remains usable when an earlier proof request finishes', async browser => {
  const oldProof = 'synthetic-old-proof-012345678901234567890123456789';
  const newProof = 'synthetic-new-proof-012345678901234567890123456789';
  const f = await fixture(browser, { path: `/account/verify#token=${oldProof}` }); try {
    await f.page.getByLabel('New password', { exact: true }).fill(password);
    await f.page.getByLabel('Confirm password', { exact: true }).fill(password);
    f.state.hold = (_req, url) => url.pathname === '/v1/auth/verify';
    await f.page.getByRole('button', { name: 'Verify email and set password', exact: true }).click();
    for (let i = 0; !f.state.held.length && i < 100; i++) await new Promise(resolve => setTimeout(resolve, 10));
    assert.equal(f.state.held.length, 1);
    await f.page.evaluate(token => { window.location.hash = `token=${token}`; }, newProof);
    await f.page.waitForFunction(() => location.hash === '');
    f.state.hold = null; f.state.held.splice(0).forEach(resolve => resolve());
    await f.page.waitForFunction(() => !document.querySelector('button[type="submit"]').disabled);
    assert.equal(await f.page.getByLabel('New password', { exact: true }).inputValue(), '');
    assert.equal(await f.page.getByLabel('Confirm password', { exact: true }).inputValue(), '');
    await f.page.getByLabel('New password', { exact: true }).fill(password);
    await f.page.getByLabel('Confirm password', { exact: true }).fill(password);
    await f.page.getByRole('button', { name: 'Verify email and set password', exact: true }).click();
    await f.page.getByText('Password saved. Sign in with your new password.', { exact: true }).waitFor();
    const payloads = f.state.requests.filter(r => r.path === '/v1/auth/verify').map(r => JSON.parse(r.body));
    assert.deepEqual(payloads.map(body => body.token), [oldProof, newProof]);
  } finally { await f.close(); }
});

test('storage allowance spans the private library and refreshes after upload and deletion', async browser => {
  const f = await fixture(browser, { storageBytes: 1048576 }); try {
    await login(f.page); await f.page.getByRole('link', { name: 'Library', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
    const storage = f.page.getByRole('region', { name: 'Document storage' });
    await storage.getByText('1.0 MB of 50.0 MB used', { exact: false }).waitFor();
    await storage.getByText('49.0 MB remaining', { exact: false }).waitFor();
    await storage.getByText('Any number of files', { exact: false }).waitFor();
    const before = f.state.requests.filter(r => r.path === '/v1/storage').length;
    await f.page.locator('input[type=file]').setInputFiles({ name: 'safe.md', mimeType: 'text/markdown', buffer: Buffer.from('Safe example') });
    for (let i = 0; f.state.requests.filter(r => r.path === '/v1/storage').length === before && i < 100; i++) await new Promise(r => setTimeout(r, 20));
    assert(f.state.requests.filter(r => r.path === '/v1/storage').length > before);
    f.page.once('dialog', d => d.accept());
    await f.page.getByRole('button', { name: 'Delete Private salary.md', exact: true }).click();
    await storage.getByText('0 B of 50.0 MB used', { exact: false }).waitFor();
    await f.page.getByRole('button', { name: 'Sign out', exact: true }).click();
    assert.equal(await f.page.getByRole('region', { name: 'Document storage' }).count(), 0);
  } finally { await f.close(); }
});
test('full storage prevents upload but keeps deletion available', async browser => {
  const f = await fixture(browser, { storageBytes: 52428800 }); try {
    await login(f.page); await f.page.getByRole('link', { name: 'Library', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
    await f.page.getByText('Storage full. Delete a document to make room for another upload.', { exact: true }).waitFor();
    assert.equal(await f.page.getByRole('button', { name: 'Choose a file' }).isEnabled(), false);
    assert.equal(await f.page.getByRole('button', { name: 'Delete Private salary.md', exact: true }).isEnabled(), true);
    f.page.once('dialog', d => d.accept());
    await f.page.getByRole('button', { name: 'Delete Private salary.md', exact: true }).click();
    await f.page.waitForFunction(() => [...document.querySelectorAll('button')].some(b => b.textContent === 'Choose a file' && !b.disabled));
  } finally { await f.close(); }
});
test('storage read failure offers retry without claiming zero usage', async browser => {
  const f = await fixture(browser); try {
    f.state.storageError = true;
    await login(f.page); await f.page.getByRole('link', { name: 'Library', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
    const storage = f.page.getByRole('region', { name: 'Document storage' });
    await storage.getByText('Could not load storage usage.', { exact: false }).waitFor();
    assert.equal(await storage.getByText('0 B of', { exact: false }).count(), 0);
    f.state.storageError = false;
    await storage.getByRole('button', { name: 'Retry' }).click();
    await storage.getByText('100 B of 50.0 MB used', { exact: false }).waitFor();
  } finally { await f.close(); }
});
test('every public set shows an accurate access explanation and three starter questions', async browser => {
  const second = '44444444-4444-4444-8444-444444444444';
  const questions = [{ question: 'Question one?', min_role: 'employee' }, { question: 'Question two?', min_role: 'employee' }, { question: 'Question three?', min_role: 'finance' }];
  const f = await fixture(browser, { publicCollections: [{ ...collection(pub), suggested_questions: questions }, { ...collection(second), name: 'Open handbook', slug: 'handbook', access_labels: [], suggested_questions: questions }] }); try {
    for (const id of [pub, second]) {
      await f.page.getByLabel('Collection', { exact: true }).selectOption(id);
      await f.page.getByRole('note', { name: 'Document access' }).waitFor();
      for (const q of questions) await f.page.getByRole('button', { name: q.question, exact: false }).waitFor();
      const note = await f.page.getByRole('note', { name: 'Document access' }).textContent();
      assert.match(note, /Viewing as Employee/);
      assert.match(note, id === pub ? /restricted to Finance/ : /no restricted sections/);
    }
    await login(f.page); await f.page.getByRole('link', { name: 'Ask', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
    await f.page.getByRole('note', { name: 'Document access' }).getByText('Only your account can access these documents.', { exact: false }).waitFor();
    assert.equal(await f.page.getByLabel('Access role').count(), 0);
  } finally { await f.close(); }
});
test('Google button follows Sign in and displays the multicolor mark on mobile', async browser => {
  const f = await fixture(browser, { width: 375, path: '/account', google: true }); try {
    const google = f.page.getByRole('button', { name: 'Continue with Google', exact: true });
    await google.waitFor();
    const signInBox = await f.page.getByRole('button', { name: 'Sign in', exact: true }).boundingBox();
    const googleBox = await google.boundingBox();
    assert(googleBox.y >= signInBox.y + signInBox.height);
    const mark = google.locator('img');
    await mark.waitFor();
    assert.equal(await mark.evaluate(img => img.complete && img.naturalWidth > 0), true);
    assert.match(await mark.getAttribute('src'), /google-g/);
    assert.equal(await f.page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  } finally { await f.close(); }
});

test('a committed delete with an error response still refreshes the full storage allowance', async browser => {
  const f = await fixture(browser, { storageBytes: 52428800, deleteCommittedError: true }); try {
    await login(f.page); await f.page.getByRole('link', { name: 'Library', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
    await f.page.getByText('Storage full. Delete a document to make room for another upload.', { exact: true }).waitFor();
    f.page.once('dialog', d => d.accept());
    await f.page.getByRole('button', { name: 'Delete Private salary.md', exact: true }).click();
    await f.page.getByRole('region', { name: 'Document storage' }).getByText('0 B of 50.0 MB used', { exact: false }).waitFor();
    await f.page.getByText('No documents yet.', { exact: true }).waitFor();
    assert.equal(await f.page.getByRole('button', { name: 'Choose a file' }).isEnabled(), true);
  } finally { await f.close(); }
});

module.exports = { fixture, login, ask };
if (require.main === module) (async () => {
  const browser = await chromium.launch({ executablePath: process.env.DOCQA_CHROMIUM || '/usr/bin/chromium', headless: true });
  let failed = 0;
  try { for (const t of tests.filter(t => !process.env.DOCQA_TEST_FILTER || new RegExp(process.env.DOCQA_TEST_FILTER).test(t.name))) { try { await t.run(browser); console.log(`PASS ${t.name}`); } catch (e) { failed++; console.error(`FAIL ${t.name}\n${e.stack}`); } } }
  finally { await browser.close(); }
  console.log(JSON.stringify({ suite: 'accounts', failed, total: tests.filter(t => !process.env.DOCQA_TEST_FILTER || new RegExp(process.env.DOCQA_TEST_FILTER).test(t.name)).length })); process.exitCode = failed ? 1 : 0;
})();
