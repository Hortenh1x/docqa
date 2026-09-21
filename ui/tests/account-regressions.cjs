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
  const state = { user: options.user || null, guestCsrf: 'csrf-guest', requests: [], responses: [], errors: [], registration: options.registration !== false, remaining: '0.30', reserved: '0.00', invalid: false, failGuestSessionOnce: false, storageBytes: options.storageBytes ?? 100, storageError: false, failed: true, deleted: false, quota: false, sseQuota: false, createFailures: 0, queryCounter: 0, queryPlans: {}, historyPageSize: options.historyPageSize ?? 1, conversationPageSize: options.conversationPageSize ?? 20, conversationOwners: {}, hold: null, held: [], history: options.history ?? [], conversations: options.conversations ?? [], claimed: [] };
  const session = () => ({ user: state.user, csrf_token: state.user ? 'csrf-user' : state.guestCsrf, registration_available: state.registration, google_available: !!options.google });
  await context.route('**/*', async route => {
    const req = route.request(), url = new URL(req.url());
    if (!url.pathname.startsWith('/v1/')) return url.origin === new URL(base).origin ? route.continue() : route.abort();
    const transcriptSnapshot = req.method() === 'GET' && /^\/v1\/conversations\/[^/]+\/queries$/.test(url.pathname)
      ? [...state.history]
      : null;
    const headers = { 'access-control-allow-origin': new URL(base).origin, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'Content-Type, X-CSRF-Token', 'access-control-allow-methods': 'GET,POST,DELETE,OPTIONS', 'access-control-expose-headers': 'X-Total-Count,Retry-After', 'X-Total-Count': state.deleted ? '0' : '1' };
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
    state.requests.push({ path: url.pathname, search: url.search, method: req.method(), headers: req.headers(), body: req.postData() });
    const expectedCsrf = state.user ? 'csrf-user' : state.guestCsrf;
    if (state.hold?.(req, url)) await new Promise(resolve => {
      const release = () => resolve();
      release.path = url.pathname;
      release.question = url.pathname === '/v1/query' ? req.postDataJSON().question : null;
      state.held.push(release);
    });
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
    if (url.pathname === '/v1/auth/login') { const body = req.postDataJSON(); const guestOwner = state.guestCsrf; state.user = { id: body.email, email: body.email, email_verified: true, tenant_id: own }; for (const [id, owner] of Object.entries(state.conversationOwners)) if (owner === guestOwner) state.conversationOwners[id] = state.user.id; return respond(session()); }
    if (url.pathname === '/v1/auth/logout') { state.user = null; return respond({}, 204); }
    if (url.pathname.startsWith('/v1/auth/')) {
      // Reset revokes signed-in sessions without clearing their cookie in its response.
      if (url.pathname.endsWith('/reset') && state.user) state.invalid = true;
      else if (url.pathname.endsWith('/verify') || url.pathname.endsWith('/reset')) state.user = null;
      return respond({ message: 'If eligible, an email has been sent.' }, url.pathname.endsWith('/register') || url.pathname.endsWith('/resend') || url.pathname.endsWith('/forgot-password') ? 202 : 200);
    }
    if (/^\/v1\/collections\/[^/]+\/conversations$/.test(url.pathname)) {
      const collectionId = url.pathname.split('/')[3];
      if (req.method() === 'POST') {
        if (state.createFailures > 0) { state.createFailures--; return respond({ code: 'rate_limited', detail: 'Please try again.', retry_after_s: 0 }, 429); }
        const chat = { id: `chat-${state.conversations.length + 1}`, collection_id: collectionId, title: req.postDataJSON().title || 'New chat', archived: false, legacy: false, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), preview: null };
        state.conversations.push(chat); state.conversationOwners[chat.id] = state.user?.id ?? state.guestCsrf; return respond(chat, 201);
      }
      const archived = url.searchParams.get('archived') === 'true';
      const owner = state.user?.id ?? state.guestCsrf;
      const rows = state.conversations.filter(chat => chat.collection_id === collectionId && chat.archived === archived && (!state.conversationOwners[chat.id] || state.conversationOwners[chat.id] === owner)).sort((a, b) => b.updated_at.localeCompare(a.updated_at) || b.id.localeCompare(a.id));
      const before = url.searchParams.get('before');
      const start = before ? rows.findIndex(chat => chat.id === before) + 1 : 0;
      const page = rows.slice(start, start + state.conversationPageSize);
      return respond({ conversations: page, has_more: start + state.conversationPageSize < rows.length, next_cursor: start + state.conversationPageSize < rows.length ? page.at(-1)?.id ?? null : null });
    }
    if (/^\/v1\/conversations\/[^/]+$/.test(url.pathname) && req.method() === 'PATCH') {
      const chat = state.conversations.find(item => item.id === url.pathname.split('/')[3]);
      Object.assign(chat, req.postDataJSON(), { updated_at: new Date().toISOString() }); return respond(chat);
    }
    if (/^\/v1\/conversations\/[^/]+\/queries$/.test(url.pathname)) {
      const chatId = url.pathname.split('/')[3];
      const items = (transcriptSnapshot ?? state.history).filter(item => item.conversation_id === chatId).sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id.localeCompare(a.id));
      const before = url.searchParams.get('before');
      const start = before ? items.findIndex(item => item.id === before) + 1 : 0;
      const page = items.slice(start, start + state.historyPageSize);
      return respond({ queries: page, has_more: start + state.historyPageSize < items.length, next_cursor: start + state.historyPageSize < items.length ? page.at(-1)?.id ?? null : null });
    }
    if (url.pathname.endsWith('/queries')) {
      const before = url.searchParams.get('before');
      const items = state.history.filter(item => item.collection_id === url.pathname.split('/')[3]);
      const start = before ? items.findIndex(item => item.id === before) + 1 : 0;
      const page = items.slice(start, start + 1);
      return respond({ queries: page.map(({ collection_id, ...item }) => item), has_more: start + 1 < items.length });
    }
    if (url.pathname === `/v1/documents/${did}` && req.method() === 'GET') return respond({ id: did, collection_id: own, filename: 'Private salary.md', mime_type: 'text/markdown', size_bytes: 100, sha256: '0'.repeat(64), status: 'ready', error: null, page_count: 1, access_labels: [], created_at: '2026-09-10T00:00:00Z', processed_at: null });
    if (url.pathname.endsWith('/passages')) return respond({ document_id: did, total: 1, offset: 0, passages: [{ chunk_id: 5, chunk_index: 0, section: 'Salary', pages: [1, 1], access_label: 'finance', content: 'Private salary excerpt in full.' }] });
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
      const query = req.postDataJSON();
      const plan = state.queryPlans[query.question] || {};
      if (plan.httpError) return respond({ code: plan.httpError.code, detail: plan.httpError.detail }, plan.httpError.status);
      const queryId = plan.queryId || `query-${++state.queryCounter}`;
      const outcome = plan.outcome || 'answered';
      const answer = plan.answer ?? (state.user ? 'Private salary answer [1]' : 'Public answer [1]');
      const access = plan.access ?? { role: state.user ? 'owner' : 'employee', hidden_passages: 0, hidden_labels: [] };
      const sources = plan.sources ?? [{ n: 1, document_id: did, filename: 'Private salary.md', pages: [1,1], section: 'Salary', snippet: 'Private salary excerpt', score: 0.9, access_label: 'finance', chunk_id: 5, chunk_index: 0 }];
      const citations = sources.map(source => ({ n: source.n, chunk_id: source.chunk_id, content: 'Private salary excerpt in full.', quotes: [{ start: 0, end: 22, text: 'Private salary excerpt' }] }));
      const frames = [['meta', { query_id: queryId, access, context: { reset: !!plan.contextReset, turns_used: plan.turnsUsed ?? 0 } }], ['sources', { sources }]];
      if (plan.delta !== false && answer) frames.push(['delta', { text: answer }]);
      if (plan.sseError) frames.push(['error', { code: plan.sseError.code, message: plan.sseError.message, retry_after_s: plan.sseError.retry_after_s }]);
      else frames.push(['done', { answer, refused: outcome === 'refused', reason: plan.reason ?? (outcome === 'clarification' ? 'context_clarification' : null), confidence: outcome === 'answered' ? 0.9 : null, usage: { prompt_tokens: 1, completion_tokens: 1, cost_usd: 0 }, latency_ms: 1, model: 'stub', citations: outcome === 'answered' ? citations : [], outcome, context: { reset: !!plan.contextReset, turns_used: plan.turnsUsed ?? 0 } }]);
      if (query.conversation_id && plan.persist !== false) state.history.unshift({ id: queryId, conversation_id: query.conversation_id, parent_query_id: query.parent_query_id || null, question: query.question, answer, refused: outcome === 'refused', reason: plan.reason ?? null, outcome: plan.sseError ? 'failed' : outcome, context_reset: !!plan.contextReset, role: state.user ? 'owner' : query.role ?? 'employee', confidence: outcome === 'answered' ? .9 : null, usage: { prompt_tokens: 1, completion_tokens: 1, cost_usd: 0 }, latency_ms: 1, model: 'stub', created_at: plan.createdAt ?? new Date().toISOString(), sources: outcome === 'answered' ? sources.map(source => ({ ...source, content: 'Private salary excerpt in full.', quotes: [{ start: 0, end: 22, text: 'Private salary excerpt' }] })) : [] });
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
const historyRow = ({ id, conversationId, parentId = null, question, outcome = 'answered', answer = `${question} answer [1]`, createdAt = '2026-09-12T10:00:00Z', role = 'employee', contextReset = false, sources = [] }) => ({ id, conversation_id: conversationId, parent_query_id: parentId, question, answer, refused: outcome === 'refused', reason: outcome === 'clarification' ? 'context_clarification' : outcome === 'refused' ? 'retrieval_threshold' : null, outcome, context_reset: contextReset, role, confidence: outcome === 'answered' ? 0.9 : null, usage: { prompt_tokens: 1, completion_tokens: 1, cost_usd: 0 }, latency_ms: 1, model: 'stub', created_at: createdAt, sources });
async function waitForHeld(state, count = 1) {
  for (let i = 0; state.held.length < count && i < 100; i++) await new Promise(resolve => setTimeout(resolve, 10));
  assert(state.held.length >= count, `Expected ${count} held request(s), saw ${state.held.length}`);
}
function releaseHeld(state, predicate) {
  const index = state.held.findIndex(predicate);
  assert(index >= 0, 'Expected a matching held request');
  state.held.splice(index, 1)[0]();
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
test('session refresh on tab return keeps the thread for the same identity and clears it for another', async browser => {
  const f = await fixture(browser); try {
    await login(f.page); await f.page.getByRole('link', { name: 'Ask', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own); await ask(f.page);
    await f.page.getByLabel('Your question').fill('Draft in progress');
    f.state.hold = (_req, url) => url.pathname === '/v1/auth/session';
    const checks = f.state.requests.filter(r => r.path === '/v1/auth/session').length;
    await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await f.page.waitForFunction(n => window.transport.filter(t => t.path.endsWith('/v1/auth/session')).length > n, checks);
    // the check runs in the background: nothing flashes, nothing is hidden
    const exchange = f.page.getByRole('article', { name: 'What is the salary?', exact: true });
    assert.equal(await f.page.getByText('Checking your session…', { exact: true }).count(), 0);
    assert.equal(await exchange.count(), 1);
    f.state.hold = null; f.state.held.splice(0).forEach(resolve => resolve());
    await f.page.waitForTimeout(300);
    assert.equal(await exchange.count(), 1, 'Same identity keeps the conversation');
    assert.equal(await f.page.getByLabel('Your question').inputValue(), 'Draft in progress');
    // another account behind the same cookie: everything private goes at once
    f.state.user = { id: 'b@example.test', email: 'b@example.test', email_verified: true, tenant_id: own };
    await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await f.page.getByText('b@example.test', { exact: true }).first().waitFor();
    await f.page.getByRole('heading', { name: 'Ask the documents.' }).waitFor();
    assert.equal(await f.page.getByText('Private salary answer', { exact: false }).count(), 0);
  } finally { await f.close(); }
});

test('guest conversations transfer at sign-in without a UUID claim request', async browser => {
  const f = await fixture(browser); try {
    await ask(f.page);
    await f.page.getByRole('article', { name: 'What is the salary?', exact: true }).waitFor();
    await login(f.page);
    assert.equal(f.state.requests.some(request => request.path === '/v1/queries/claim'), false);
    await f.page.getByRole('link', { name: 'Ask', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(pub);
    await f.page.getByRole('article', { name: 'What is the salary?', exact: true }).getByText('Public answer', { exact: false }).waitFor();
    assert.equal(await f.page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }).includes('Public answer')), false, 'Accounts keep nothing in browser storage');
  } finally { await f.close(); }
});

test('a signed-in thread is read from the account history and pages backwards', async browser => {
  const f = await fixture(browser); try {
    f.state.conversations = [{ id: 'chat-own', collection_id: own, title: 'New chat', archived: false, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-12T10:00:00Z', preview: null }];
    const item = (id, question, created_at) => ({ id, conversation_id: 'chat-own', parent_query_id: null, question, answer: `${question} answer [1]`, refused: false, reason: null, outcome: 'answered', context_reset: false, role: null, confidence: 0.9, usage: { prompt_tokens: 1, completion_tokens: 1, cost_usd: 0 }, latency_ms: 1, model: 'stub', created_at, sources: [{ n: 1, document_id: did, filename: 'Private salary.md', pages: [1, 1], section: 'Salary', snippet: 'Private salary excerpt', score: 0.9, access_label: 'finance', chunk_id: 5, chunk_index: 0, content: 'Private salary excerpt in full.', quotes: [{ start: 0, end: 22, text: 'Private salary excerpt' }] }] });
    f.state.history = [item('q-3', 'Third', '2026-09-12T10:00:00Z'), item('q-2', 'Second', '2026-09-11T10:00:00Z'), item('q-1', 'First', '2026-09-10T10:00:00Z')];
    await login(f.page); await f.page.getByRole('link', { name: 'Ask', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
    await f.page.getByRole('article', { name: 'Third', exact: true }).waitFor();
    assert.equal(await f.page.getByRole('article', { name: 'Second', exact: true }).count(), 0);
    await f.page.getByRole('button', { name: 'Show earlier questions', exact: true }).click();
    await f.page.getByRole('article', { name: 'Second', exact: true }).waitFor();
    await f.page.getByRole('button', { name: 'Show earlier questions', exact: true }).click();
    await f.page.getByRole('article', { name: 'First', exact: true }).waitFor();
    const order = await f.page.locator('article').evaluateAll(nodes => nodes.map(n => n.getAttribute('aria-label')));
    assert.deepEqual(order, ['First', 'Second', 'Third']);
    assert.equal(await f.page.getByRole('button', { name: 'Clear history' }).count(), 0, 'Account history is not cleared from the browser');
    // a restored citation still opens the reader on its quote
    await f.page.getByRole('button', { name: 'Source 1: Private salary.md, pages 1–1', exact: true }).first().click();
    const dialog = f.page.getByRole('dialog');
    assert.equal(await dialog.locator('blockquote mark').innerText(), 'Private salary excerpt');
    await dialog.getByRole('button', { name: 'Open in document', exact: true }).click();
    const reader = f.page.getByRole('dialog', { name: 'Read Private salary.md' });
    await reader.locator('mark').waitFor();
    assert.equal(await reader.locator('mark').innerText(), 'Private salary excerpt');
    assert(f.state.requests.some(r => r.path === `/v1/documents/${did}/passages` && !r.search.includes('role=')), 'Owners read passages without a role');
    await f.page.keyboard.press('Escape');
    await reader.waitFor({ state: 'detached' });
    await f.page.getByRole('dialog', { name: 'Source 1: Private salary.md' }).waitFor();
  } finally { await f.close(); }
});
test('an incomplete recorded answer is readable and retryable', async browser => {
  const f = await fixture(browser); try {
    f.state.conversations = [{ id: 'chat-incomplete', collection_id: own, title: 'New chat', archived: false, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-12T10:00:00Z', preview: null }];
    f.state.history = [{ id: 'q-incomplete', conversation_id: 'chat-incomplete', parent_query_id: null, question: 'Interrupted answer', answer: null, refused: false, reason: null, outcome: 'failed', context_reset: false, role: null, confidence: 0.9, usage: { prompt_tokens: 10, completion_tokens: null, cost_usd: null }, latency_ms: 1, model: 'stub', created_at: '2026-09-12T10:00:00Z', sources: [] }];
    await login(f.page); await f.page.getByRole('link', { name: 'Ask', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(own);
    const exchange = f.page.getByRole('article', { name: 'Interrupted answer', exact: true });
    await exchange.getByText('Incomplete', { exact: true }).waitFor();
    await exchange.getByRole('button', { name: 'Retry', exact: true }).waitFor();
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

test('named chat can be renamed, archived, and continued with a clean root', async browser => {
  const f = await fixture(browser); try {
    f.state.hold = (req, url) => req.method() === 'GET' && url.pathname === '/v1/conversations/chat-1/queries';
    await f.page.getByLabel('Chats', { exact: true }).getByRole('button', { name: 'New chat', exact: true }).click();
    await waitForHeld(f.state);
    assert.equal(await f.page.getByLabel('Your question').isDisabled(), true);
    assert.equal(await f.page.getByLabel('Your question').evaluate(node => node === document.activeElement), false);
    f.state.hold = null; f.state.held.splice(0).forEach(release => release());
    await f.page.waitForFunction(() => document.activeElement === document.querySelector('[aria-label="Your question"]'));
    await f.page.getByRole('button', { name: 'Rename', exact: true }).click();
    await f.page.getByLabel('Chat title', { exact: true }).fill('Benefits');
    await f.page.getByRole('button', { name: 'Save', exact: true }).click();
    await f.page.getByRole('button', { name: 'Archive', exact: true }).click();
    await f.page.getByText('This chat is archived.', { exact: false }).waitFor();
    assert.equal(await f.page.getByLabel('Your question').isDisabled(), true);
    await f.page.getByRole('button', { name: 'Unarchive', exact: true }).click();
    await f.page.waitForFunction(() => !document.querySelector('[aria-label="Your question"]').disabled);
    assert.equal(await f.page.getByText('This chat is archived.', { exact: false }).count(), 0);
    await f.page.getByRole('button', { name: 'Archive', exact: true }).click();
    await f.page.getByText('This chat is archived.', { exact: false }).waitFor();
    await f.page.getByRole('button', { name: 'Continue in new chat', exact: true }).click();
    await f.page.getByLabel('Your question').fill('A clean question');
    await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    await f.page.getByRole('article', { name: 'A clean question', exact: true }).getByText('Public answer', { exact: false }).waitFor();
    const request = f.state.requests.filter(item => item.path === '/v1/query').at(-1);
    assert.equal(JSON.parse(request.body).parent_query_id, null);
  } finally { await f.close(); }
});

test('changing chat while renaming cannot submit the draft to the newly selected chat', async browser => {
  const conversations = [
    { id: 'chat-a', collection_id: pub, title: 'Chat A', archived: false, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-30T10:00:00Z', preview: null },
    { id: 'chat-b', collection_id: pub, title: 'Chat B', archived: false, legacy: false, created_at: '2026-09-09T00:00:00Z', updated_at: '2026-09-29T10:00:00Z', preview: null },
  ];
  const f = await fixture(browser, { conversations }); try {
    const chats = f.page.getByRole('region', { name: 'Chats', exact: true });
    await chats.getByRole('button', { name: 'Rename', exact: true }).click();
    await chats.getByLabel('Chat title', { exact: true }).fill('Draft for A');
    await chats.getByRole('button', { name: 'Chat B', exact: true }).click();
    assert.equal(await chats.getByRole('button', { name: 'Save', exact: true }).count(), 0, 'Changing selection cancels the old editor');
    assert.equal(f.state.requests.filter(item => item.method === 'PATCH').length, 0);
    await chats.getByRole('button', { name: 'Rename', exact: true }).click();
    assert.equal(await chats.getByLabel('Chat title', { exact: true }).inputValue(), 'Chat B');
  } finally { await f.close(); }
});

test('archived chat keeps incomplete and refused history read-only', async browser => {
  const f = await fixture(browser); try {
    f.state.conversations = [{ id: 'chat-archived', collection_id: pub, title: 'Archived history', archived: true, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-12T10:00:00Z', preview: null }];
    const row = (id, question, outcome, created_at) => ({ id, conversation_id: 'chat-archived', parent_query_id: null, question, answer: outcome === 'refused' ? 'No answer' : 'Partial answer', refused: outcome === 'refused', reason: outcome === 'refused' ? 'retrieval_threshold' : 'provider_error', outcome, context_reset: false, role: 'employee', confidence: null, usage: { prompt_tokens: null, completion_tokens: null, cost_usd: null }, latency_ms: 1, model: 'stub', created_at, sources: [] });
    f.state.history = [row('q-incomplete', 'Interrupted archived answer', 'failed', '2026-09-12T10:00:00Z'), row('q-refused', 'Archived refusal', 'refused', '2026-09-11T10:00:00Z')];
    await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    const chats = f.page.getByRole('region', { name: 'Chats', exact: true });
    await chats.getByRole('button', { name: 'Archived', exact: true }).click();
    await chats.getByRole('button', { name: 'Archived history', exact: true }).click();
    await f.page.getByRole('article', { name: 'Interrupted archived answer', exact: true }).waitFor();
    await f.page.getByRole('button', { name: 'Show earlier questions', exact: true }).click();
    await f.page.getByRole('article', { name: 'Archived refusal', exact: true }).waitFor();
    assert.equal(await f.page.getByRole('button', { name: 'Retry', exact: true }).count(), 0);
    assert.equal(await f.page.getByRole('button', { name: 'What is the policy?', exact: false }).count(), 0);
    assert.equal(await f.page.getByLabel('Your question').isDisabled(), true);
    assert.equal(f.state.requests.filter(item => item.path === '/v1/query').length, 0);
  } finally { await f.close(); }
});

test('initial transcript blocks send until its durable parent is loaded', async browser => {
  const f = await fixture(browser); try {
    f.state.conversations = [{ id: 'chat-head', collection_id: pub, title: 'Head test', archived: false, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-12T10:00:00Z', preview: null }];
    f.state.history = [historyRow({ id: 'q-parent', conversationId: 'chat-head', question: 'Existing parent' })];
    f.state.hold = (_req, url) => url.pathname === '/v1/conversations/chat-head/queries';
    await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await f.page.getByRole('region', { name: 'Chats', exact: true }).getByRole('button', { name: 'Head test', exact: true }).waitFor();
    await waitForHeld(f.state);
    assert.equal(await f.page.getByLabel('Your question').isDisabled(), true);
    f.state.hold = null; f.state.held.splice(0).forEach(resolve => resolve());
    await f.page.getByRole('article', { name: 'Existing parent', exact: true }).waitFor();
    await f.page.getByLabel('Your question').fill('Follow loaded parent');
    await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    await f.page.getByRole('article', { name: 'Follow loaded parent', exact: true }).getByText('Public answer', { exact: false }).waitFor();
    const body = JSON.parse(f.state.requests.filter(item => item.path === '/v1/query').at(-1).body);
    assert.equal(body.parent_query_id, 'q-parent');
  } finally { await f.close(); }
});

test('local completion survives an older transcript snapshot and a refreshed external head wins', async browser => {
  const f = await fixture(browser); try {
    f.state.conversations = [{ id: 'chat-causal', collection_id: pub, title: 'Causal head', archived: false, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-12T10:00:00Z', preview: null }];
    f.state.history = [historyRow({ id: 'q-one', conversationId: 'chat-causal', question: 'Server parent', createdAt: '2026-09-12T10:00:00Z' })];
    await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await f.page.getByRole('article', { name: 'Server parent', exact: true }).waitFor();
    f.state.hold = (_req, url) => url.pathname === '/v1/conversations/chat-causal/queries';
    await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await waitForHeld(f.state);
    await f.page.evaluate(() => {
      const RealDate = Date;
      class SkewedDate extends RealDate {
        constructor(...args) { super(args.length ? args[0] : '2020-01-01T00:00:00Z'); }
        static now() { return new RealDate('2020-01-01T00:00:00Z').getTime(); }
      }
      window.Date = SkewedDate;
    });
    f.state.queryPlans['Local second'] = { queryId: 'q-two' };
    await f.page.getByLabel('Your question').fill('Local second'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    await f.page.getByRole('article', { name: 'Local second', exact: true }).getByText('Public answer', { exact: false }).waitFor();
    f.state.queryPlans['After stale snapshot'] = { queryId: 'q-three' };
    await f.page.getByLabel('Your question').fill('After stale snapshot'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    await f.page.getByRole('article', { name: 'After stale snapshot', exact: true }).getByText('Public answer', { exact: false }).waitFor();
    let body = JSON.parse(f.state.requests.filter(item => item.path === '/v1/query').at(-1).body);
    assert.equal(body.parent_query_id, 'q-two', 'A browser clock skew cannot rewind the local durable head');
    f.state.hold = null; f.state.held.splice(0).forEach(resolve => resolve());
    f.state.history.unshift(historyRow({ id: 'q-external', conversationId: 'chat-causal', parentId: 'q-two', question: 'External newer answer', createdAt: '2026-09-30T10:00:00Z' }));
    await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await f.page.getByRole('article', { name: 'External newer answer', exact: true }).waitFor();
    f.state.queryPlans['After external answer'] = { queryId: 'q-four' };
    await f.page.getByLabel('Your question').fill('After external answer'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    await f.page.getByRole('article', { name: 'After external answer', exact: true }).getByText('Public answer', { exact: false }).waitFor();
    body = JSON.parse(f.state.requests.filter(item => item.path === '/v1/query').at(-1).body);
    assert.equal(body.parent_query_id, 'q-external');
  } finally { await f.close(); }
});

test('failed lazy create stays with its collection and Retry creates the captured root', async browser => {
  const second = '44444444-4444-4444-8444-444444444444';
  const f = await fixture(browser, { publicCollections: [collection(pub), { ...collection(second), name: 'Second policies', slug: 'second-policies' }] }); try {
    f.state.createFailures = 1;
    await f.page.getByLabel('Your question').fill('Keep this failed question'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    const failed = f.page.getByRole('article', { name: 'Keep this failed question', exact: true });
    await failed.getByText('Demo limit reached', { exact: true }).waitFor();
    await f.page.getByLabel('Collection', { exact: true }).selectOption(second);
    assert.equal(await failed.count(), 0, 'A null-conversation row must still be scoped by collection');
    await f.page.getByLabel('Collection', { exact: true }).selectOption(pub);
    await failed.getByRole('button', { name: 'Retry', exact: true }).click();
    await f.page.getByRole('article', { name: 'Keep this failed question', exact: true }).getByText('Public answer', { exact: false }).waitFor();
    const body = JSON.parse(f.state.requests.filter(item => item.path === '/v1/query').at(-1).body);
    assert.equal(body.collection_id, pub); assert.equal(body.parent_query_id, null); assert.match(body.conversation_id, /^chat-/);
  } finally { await f.close(); }
});

test('late lazy creation never steals a newer selected conversation', async browser => {
  const f = await fixture(browser); try {
    f.state.hold = (req, url) => req.method() === 'POST' && url.pathname === `/v1/collections/${pub}/conversations`;
    await f.page.getByLabel('Your question').fill('Lazy A'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    await waitForHeld(f.state);
    f.state.conversations.push({ id: 'chat-b', collection_id: pub, title: 'Selected B', archived: false, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-30T10:00:00Z', preview: null });
    await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await f.page.getByRole('region', { name: 'Chats', exact: true }).getByRole('button', { name: 'Selected B', exact: true }).waitFor();
    f.state.hold = null; f.state.held.splice(0).forEach(resolve => resolve());
    await f.page.waitForFunction(() => window.transport.filter(item => item.path.endsWith('/v1/query')).length > 0);
    const header = f.page.getByRole('region', { name: 'Chats', exact: true });
    assert.equal(await header.getByText('Selected B', { exact: true }).count() > 0, true);
    assert.equal(await header.getByRole('button', { name: 'Selected B', exact: true }).getAttribute('aria-current'), 'page');
  } finally { await f.close(); }
});

test('a late older sibling never replaces the newer completed and echoed head', async browser => {
  const f = await fixture(browser); try {
    f.state.conversations = [{ id: 'chat-siblings', collection_id: pub, title: 'Sibling race', archived: false, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-12T10:00:00Z', preview: null }];
    f.state.history = [historyRow({ id: 'q-root', conversationId: 'chat-siblings', question: 'Root' })];
    f.state.historyPageSize = 30;
    await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await f.page.getByRole('article', { name: 'Root', exact: true }).waitFor();
    f.state.queryPlans['Slow older sibling'] = { queryId: 'q-slow', createdAt: '2026-09-13T10:00:00Z' };
    f.state.queryPlans['Fast newer sibling'] = { queryId: 'q-fast', createdAt: '2026-09-13T10:00:01Z' };
    f.state.hold = (req, url) => url.pathname === '/v1/query' && req.postDataJSON().question === 'Slow older sibling';
    await f.page.getByLabel('Your question').fill('Slow older sibling'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    await waitForHeld(f.state);
    await f.page.getByLabel('Your question').fill('Fast newer sibling'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    await f.page.getByRole('article', { name: 'Fast newer sibling', exact: true }).getByText('Public answer', { exact: false }).waitFor();
    await f.page.waitForFunction(() => window.transport.filter(item => item.path.includes('/v1/conversations/chat-siblings/queries')).length >= 2);
    f.state.hold = (_req, url) => url.pathname === '/v1/conversations/chat-siblings/queries';
    f.state.held.splice(0).forEach(resolve => resolve());
    await f.page.getByRole('article', { name: 'Slow older sibling', exact: true }).getByText('Public answer', { exact: false }).waitFor();
    f.state.queryPlans['After sibling race'] = { queryId: 'q-after-siblings' };
    await f.page.getByLabel('Your question').fill('After sibling race'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    await f.page.waitForFunction(() => window.transport.filter(item => item.path.endsWith('/v1/query')).length >= 3);
    const body = JSON.parse(f.state.requests.filter(item => item.path === '/v1/query').at(-1).body);
    assert.equal(body.parent_query_id, 'q-fast');
  } finally { await f.close(); }
});

test('a newer sibling remains the head when the older sibling completes first', async browser => {
  const conversation = { id: 'chat-siblings-forward', collection_id: pub, title: 'Forward sibling race', archived: false, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-12T10:00:00Z', preview: null };
  const f = await fixture(browser, { conversations: [conversation], history: [historyRow({ id: 'q-root-forward', conversationId: conversation.id, question: 'Forward root' })], historyPageSize: 30 }); try {
    await f.page.getByRole('article', { name: 'Forward root', exact: true }).waitFor();
    f.state.queryPlans['Older finishes first'] = { queryId: 'q-older-first' };
    f.state.queryPlans['Newer finishes second'] = { queryId: 'q-newer-second' };
    f.state.hold = (_req, url) => url.pathname === '/v1/query';
    await f.page.getByLabel('Your question').fill('Older finishes first'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    await f.page.getByLabel('Your question').fill('Newer finishes second'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    await waitForHeld(f.state, 2);
    f.state.hold = (_req, url) => url.pathname === `/v1/conversations/${conversation.id}/queries`;
    releaseHeld(f.state, held => held.question === 'Older finishes first');
    await f.page.getByRole('article', { name: 'Older finishes first', exact: true }).getByText('Public answer', { exact: false }).waitFor();
    releaseHeld(f.state, held => held.question === 'Newer finishes second');
    await f.page.getByRole('article', { name: 'Newer finishes second', exact: true }).getByText('Public answer', { exact: false }).waitFor();
    await waitForHeld(f.state, 1);
    f.state.queryPlans['After forward siblings'] = { queryId: 'q-after-forward' };
    await f.page.getByLabel('Your question').fill('After forward siblings'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    await f.page.waitForFunction(() => window.transport.filter(item => item.path.endsWith('/v1/query')).length >= 3);
    const body = JSON.parse(f.state.requests.filter(item => item.path === '/v1/query').at(-1).body);
    assert.equal(body.parent_query_id, 'q-newer-second');
  } finally { await f.close(); }
});

test('partial SSE failure stays readable and reconciles to durable incomplete history', async browser => {
  const conversation = { id: 'chat-partial', collection_id: pub, title: 'Partial failure', archived: false, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-12T10:00:00Z', preview: null };
  const f = await fixture(browser, { conversations: [conversation], history: [historyRow({ id: 'q-partial-root', conversationId: conversation.id, question: 'Partial root' })], historyPageSize: 30 }); try {
    await f.page.getByRole('article', { name: 'Partial root', exact: true }).waitFor();
    f.state.queryPlans['Interrupted response'] = { queryId: 'q-partial-error', answer: 'Readable partial answer [1]', sseError: { code: 'provider_error', message: 'Provider interrupted.' } };
    f.state.hold = (_req, url) => url.pathname === `/v1/conversations/${conversation.id}/queries`;
    await f.page.getByLabel('Your question').fill('Interrupted response'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    const row = f.page.getByRole('article', { name: 'Interrupted response', exact: true });
    await row.getByText('Readable partial answer [1]', { exact: true }).waitFor();
    await row.getByText('Something went wrong', { exact: true }).waitFor();
    await waitForHeld(f.state, 1);
    await row.getByRole('listitem', { name: 'Source 1: Private salary.md, pages 1–1', exact: true }).click();
    const drawer = f.page.getByRole('dialog', { name: 'Source 1: Private salary.md', exact: true });
    await drawer.waitFor();
    f.state.hold = null; f.state.held.splice(0).forEach(release => release());
    await row.getByText('Incomplete', { exact: true }).waitFor();
    await drawer.getByText('Private salary excerpt', { exact: false }).first().waitFor();
    assert.equal(await f.page.getByRole('article', { name: 'Interrupted response', exact: true }).count(), 1, 'The optimistic row is replaced by one durable row');
  } finally { await f.close(); }
});

test('failed rows do not advance the head and retry preserves the captured scope', async browser => {
  const f = await fixture(browser); try {
    f.state.conversations = [{ id: 'chat-retry', collection_id: pub, title: 'Retry scope', archived: false, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-12T10:00:00Z', preview: null }];
    f.state.history = [historyRow({ id: 'q-failed', conversationId: 'chat-retry', parentId: 'q-parent', question: 'Persisted failure', outcome: 'failed', answer: 'Partial' }), historyRow({ id: 'q-parent', conversationId: 'chat-retry', question: 'Eligible parent', createdAt: '2026-09-11T10:00:00Z' })];
    f.state.historyPageSize = 30;
    await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    const failed = f.page.getByRole('article', { name: 'Persisted failure', exact: true });
    await failed.getByRole('button', { name: 'Retry', exact: true }).click();
    await failed.getByText('Public answer', { exact: false }).waitFor();
    let body = JSON.parse(f.state.requests.filter(item => item.path === '/v1/query').at(-1).body);
    assert.deepEqual({ collection: body.collection_id, conversation: body.conversation_id, parent: body.parent_query_id }, { collection: pub, conversation: 'chat-retry', parent: 'q-parent' });
    f.state.queryPlans['Endpoint failure'] = { queryId: 'q-error', sseError: { code: 'provider_error', message: 'Provider failed.' } };
    await f.page.getByLabel('Your question').fill('Endpoint failure'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    const endpointFailure = f.page.getByRole('article', { name: 'Endpoint failure', exact: true });
    await endpointFailure.getByText(/Something went wrong|Incomplete/).waitFor();
    await f.page.getByLabel('Your question').fill('After endpoint failure'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    body = JSON.parse(f.state.requests.filter(item => item.path === '/v1/query').at(-1).body);
    assert.notEqual(body.parent_query_id, 'q-error');
  } finally { await f.close(); }
});

test('View as reruns the clicked refusal with its captured collection conversation and parent', async browser => {
  const conversation = { id: 'chat-view', collection_id: pub, title: 'View as scope', archived: false, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-12T10:00:00Z', preview: null };
  const f = await fixture(browser, { conversations: [conversation], history: [historyRow({ id: 'q-parent', conversationId: 'chat-view', question: 'Parent' })] }); try {
    f.state.queryPlans['Restricted question'] = { queryId: 'q-refused', outcome: 'refused', answer: 'Restricted question', delta: false, sources: [], access: { role: 'employee', hidden_passages: 2, hidden_labels: ['finance'], hidden_documents: 1, hidden_outranking: true, hidden_truncated: false } };
    await f.page.getByRole('article', { name: 'Parent', exact: true }).waitFor();
    f.state.hold = (_req, url) => url.pathname === '/v1/conversations/chat-view/queries';
    await f.page.getByLabel('Your question').fill('Restricted question'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    const refused = f.page.getByRole('article', { name: 'Restricted question', exact: true });
    await refused.getByRole('button', { name: 'View as Finance', exact: true }).click();
    await f.page.waitForFunction(() => window.transport.filter(item => item.path.endsWith('/v1/query')).length >= 2);
    const body = JSON.parse(f.state.requests.filter(item => item.path === '/v1/query').at(-1).body);
    assert.deepEqual({ collection: body.collection_id, conversation: body.conversation_id, parent: body.parent_query_id, role: body.role }, { collection: pub, conversation: 'chat-view', parent: 'q-parent', role: 'finance' });
  } finally { await f.close(); }
});

test('clarification is neutral and remains an eligible parent while reset copy stays generic', async browser => {
  const f = await fixture(browser); try {
    f.state.conversations = [{ id: 'chat-clarify', collection_id: pub, title: 'Clarify', archived: false, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-12T10:00:00Z', preview: null }];
    f.state.history = [historyRow({ id: 'q-parent', conversationId: 'chat-clarify', question: 'Parent' })];
    f.state.queryPlans['Ambiguous follow-up'] = { queryId: 'q-clarify', outcome: 'clarification', answer: 'Which year do you mean?', delta: false, sources: [] };
    f.state.queryPlans['The latest year'] = { queryId: 'q-reset', contextReset: true };
    await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await f.page.getByRole('article', { name: 'Parent', exact: true }).waitFor();
    await f.page.getByLabel('Your question').fill('Ambiguous follow-up'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    const clarification = f.page.getByRole('article', { name: 'Ambiguous follow-up', exact: true });
    await clarification.getByText('Which year do you mean?', { exact: true }).waitFor();
    assert.equal(await clarification.getByText('grounded', { exact: false }).count(), 0);
    assert.equal(await clarification.getByRole('button', { name: 'Retry', exact: true }).count(), 0);
    await f.page.getByLabel('Your question').fill('The latest year'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    const reset = f.page.getByRole('article', { name: 'The latest year', exact: true });
    await reset.getByText('This answer starts with fresh context.', { exact: true }).waitFor();
    const body = JSON.parse(f.state.requests.filter(item => item.path === '/v1/query').at(-1).body);
    assert.equal(body.parent_query_id, 'q-clarify');
    const text = await reset.innerText();
    assert.equal(/source_generation|fingerprint|effective question|access reset/i.test(text), false);
  } finally { await f.close(); }
});

test('same guest refresh preserves a running stream while guest rotation clears and aborts it', async browser => {
  const f = await fixture(browser); try {
    f.state.hold = (_req, url) => url.pathname === '/v1/query';
    await f.page.getByLabel('Your question').fill('Held guest stream'); await f.page.getByRole('button', { name: 'Ask', exact: true }).click();
    await waitForHeld(f.state);
    const exchange = f.page.getByRole('article', { name: 'Held guest stream', exact: true });
    await exchange.waitFor();
    const input = f.page.getByLabel('Your question'); await input.fill('Guest draft'); await input.focus();
    let checks = f.state.requests.filter(item => item.path === '/v1/auth/session').length;
    await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await f.page.waitForFunction(count => window.transport.filter(item => item.path.endsWith('/v1/auth/session')).length > count, checks);
    await f.page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Your question');
    assert.equal(await exchange.count(), 1); assert.equal(await input.inputValue(), 'Guest draft');
    f.state.guestCsrf = 'csrf-rotated'; checks = f.state.requests.filter(item => item.path === '/v1/auth/session').length;
    await f.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await f.page.waitForFunction(count => window.transport.filter(item => item.path.endsWith('/v1/auth/session')).length > count, checks);
    await f.page.getByRole('heading', { name: 'Ask the documents.', exact: true }).waitFor();
    assert.equal(await exchange.count(), 0); assert.equal(await f.page.getByLabel('Your question').inputValue(), '');
    await f.page.waitForFunction(() => window.abortedRequests.some(item => item.endsWith('/v1/query')));
  } finally { await f.close(); }
});

test('legacy anonymous local history is read-only, hidden after login, and removed only on explicit logout', async browser => {
  const f = await fixture(browser); try {
    await f.page.evaluate((collectionId) => localStorage.setItem('docqa.ask.v2.guest', JSON.stringify([{ id: 'old-local', collectionId, question: 'Old local question', answer: 'Old local answer', createdAt: '2026-09-10T00:00:00Z' }])), pub);
    await f.page.reload();
    const disclosure = f.page.getByText('Earlier local history', { exact: true });
    await disclosure.waitFor(); await disclosure.click();
    await f.page.getByText('Old local question', { exact: true }).waitFor();
    assert.equal(await f.page.getByText('Old local question', { exact: true }).locator('..').getByRole('button').count(), 0);
    await login(f.page);
    assert.equal(await disclosure.count(), 0);
    assert.notEqual(await f.page.evaluate(() => localStorage.getItem('docqa.ask.v2.guest')), null);
    await f.page.getByRole('button', { name: 'Sign out', exact: true }).click();
    await f.page.getByRole('link', { name: 'Sign in', exact: true }).first().waitFor();
    assert.equal(await f.page.evaluate(() => localStorage.getItem('docqa.ask.v2.guest')), null);
  } finally { await f.close(); }
});

test('conversation lists page beyond twenty and default titles show their last-question preview', async browser => {
  const conversations = [false, true].flatMap(archived => Array.from({ length: 21 }, (_, index) => ({ id: `chat-${archived ? 'archived' : 'active'}-${index + 1}`, collection_id: pub, title: 'New chat', archived, legacy: false, created_at: `2026-09-${String(index + 1).padStart(2, '0')}T10:00:00Z`, updated_at: `2026-09-${String(index + 1).padStart(2, '0')}T10:00:00Z`, preview: { query_id: `preview-${archived ? 'archived' : 'active'}-${index + 1}`, question: `${archived ? 'Archived' : 'Active'} preview ${index + 1}`, outcome: 'answered', created_at: `2026-09-${String(index + 1).padStart(2, '0')}T10:00:00Z` } })));
  const f = await fixture(browser, { conversations, conversationPageSize: 20 }); try {
    const chats = f.page.getByRole('region', { name: 'Chats', exact: true });
    await chats.getByText('Active preview 21', { exact: true }).waitFor();
    assert.equal(await chats.getByText('Active preview 1', { exact: true }).count(), 0);
    await chats.getByRole('button', { name: 'Load more chats', exact: true }).click();
    await chats.getByText('Active preview 1', { exact: true }).waitFor();
    assert.equal(await chats.getByRole('button', { name: 'New chat. Last question: Active preview 21', exact: true }).count(), 1);
    await chats.getByRole('button', { name: 'Archived', exact: true }).click();
    await chats.getByText('Archived preview 21', { exact: true }).waitFor();
    assert.equal(await chats.getByText('Archived preview 1', { exact: true }).count(), 0);
    await chats.getByRole('button', { name: 'Load more chats', exact: true }).click();
    await chats.getByText('Archived preview 1', { exact: true }).waitFor();
  } finally { await f.close(); }
});

test('legacy server conversation is readable and exposes no write or reply actions', async browser => {
  const conversation = { id: 'chat-legacy', collection_id: pub, title: 'Previous questions', archived: true, legacy: true, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-12T10:00:00Z', preview: null };
  const history = [historyRow({ id: 'q-legacy', conversationId: 'chat-legacy', question: 'Historical question', outcome: 'legacy_unknown', answer: 'Historical answer' })];
  const f = await fixture(browser, { conversations: [conversation], history }); try {
    const chats = f.page.getByRole('region', { name: 'Chats', exact: true });
    await chats.getByRole('button', { name: 'Archived', exact: true }).click();
    await chats.getByRole('button', { name: 'Previous questions · Previous questions', exact: true }).click();
    await f.page.getByText('Previous questions are read-only.', { exact: true }).waitFor();
    await f.page.getByRole('article', { name: 'Historical question', exact: true }).getByText('Historical answer', { exact: true }).last().waitFor();
    assert.equal(await chats.getByRole('button', { name: 'Rename', exact: true }).count(), 0);
    assert.equal(await chats.getByRole('button', { name: 'Unarchive', exact: true }).count(), 0);
    assert.equal(await f.page.getByLabel('Your question').isDisabled(), true);
  } finally { await f.close(); }
});

test('large variable transcript keeps prepend anchor, bounded DOM, focus and source state', async browser => {
  const conversation = { id: 'chat-large', collection_id: pub, title: 'Large transcript', archived: false, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-30T10:00:00Z', preview: null };
  const source = { n: 1, document_id: did, filename: 'Private salary.md', pages: [1, 1], section: 'Salary', snippet: 'Private salary excerpt', score: .9, access_label: 'finance', chunk_id: 5, chunk_index: 0, content: 'Private salary excerpt in full.', quotes: [{ start: 0, end: 22, text: 'Private salary excerpt' }] };
  const history = Array.from({ length: 120 }, (_, index) => historyRow({ id: `q-large-${index + 1}`, conversationId: 'chat-large', question: `Question ${index + 1}`, answer: `${Array.from({ length: index % 5 + 1 }, () => `Variable paragraph for row ${index + 1}.`).join('\n\n')} [1]`, createdAt: new Date(Date.UTC(2026, 8, 1, 0, index)).toISOString(), sources: [source] }));
  const f = await fixture(browser, { conversations: [conversation], history, historyPageSize: 30 }); try {
    const transcript = f.page.getByLabel('Conversation transcript', { exact: true });
    await f.page.getByRole('article', { name: 'Question 120', exact: true }).waitFor();
    const visibleAnchor = async () => transcript.evaluate((node) => {
      const box = node.getBoundingClientRect();
      const visible = [...node.querySelectorAll('article')].map(article => ({ label: article.getAttribute('aria-label'), top: article.getBoundingClientRect().top - box.top })).filter(item => item.top >= 0).sort((a, b) => a.top - b.top)[0];
      return visible;
    });
    const anchor = await visibleAnchor(); assert(anchor?.label);
    let transcriptRequests = f.state.requests.filter(item => item.path === '/v1/conversations/chat-large/queries').length;
    await transcript.getByRole('button', { name: 'Show earlier questions', exact: true }).click();
    await f.page.waitForFunction(count => window.transport.filter(item => item.path.includes('/v1/conversations/chat-large/queries')).length > count, transcriptRequests);
    await f.page.waitForFunction(label => { const viewport = document.querySelector('[aria-label="Conversation transcript"]'); const article = [...document.querySelectorAll('article')].find(row => row.getAttribute('aria-label') === label); return !!viewport && !!article && article.getBoundingClientRect().top >= viewport.getBoundingClientRect().top; }, anchor.label);
    const after = await visibleAnchor();
    assert.equal(after.label, anchor.label); assert(Math.abs(after.top - anchor.top) < 12, `Anchor shifted ${after.top - anchor.top}px`);
    const pinnedAcrossPrepend = transcript.getByRole('article', { name: anchor.label, exact: true }).getByRole('listitem').first();
    await pinnedAcrossPrepend.focus();
    const pinnedRowKey = await pinnedAcrossPrepend.evaluate(node => node.closest('[data-row-key]')?.getAttribute('data-row-key'));
    assert(pinnedRowKey);
    transcriptRequests = f.state.requests.filter(item => item.path === '/v1/conversations/chat-large/queries').length;
    const secondPage = transcript.getByRole('button', { name: 'Show earlier questions', exact: true });
    await f.page.waitForFunction(() => {
      const button = [...document.querySelectorAll('button')].find(item => item.textContent === 'Show earlier questions');
      return button instanceof HTMLButtonElement && !button.disabled;
    });
    await secondPage.evaluate(button => button.click());
    await f.page.waitForFunction(count => window.transport.filter(item => item.path.includes('/v1/conversations/chat-large/queries')).length > count, transcriptRequests);
    await transcript.getByText('90 questions', { exact: true }).waitFor();
    await transcript.evaluate(node => { node.scrollTop = node.scrollHeight; node.dispatchEvent(new Event('scroll', { bubbles: true })); });
    await f.page.waitForTimeout(100);
    const prependFocus = await f.page.evaluate(key => { const row = document.querySelector(`[data-row-key="${CSS.escape(key)}"]`); const active = document.activeElement; return { retained: !!row && row.contains(active) && active.isConnected, rowConnected: !!row?.isConnected, activeTag: active?.tagName, activeLabel: active?.getAttribute('aria-label'), activeRowKey: active?.closest('[data-row-key]')?.getAttribute('data-row-key') }; }, pinnedRowKey);
    assert.equal(prependFocus.retained, true, `Focused row ${pinnedRowKey} survives a prepended page: ${JSON.stringify(prependFocus)}`);
    await transcript.focus();
    transcriptRequests = f.state.requests.filter(item => item.path === '/v1/conversations/chat-large/queries').length;
    const thirdPage = transcript.getByRole('button', { name: 'Show earlier questions', exact: true });
    await f.page.waitForFunction(() => {
      const button = [...document.querySelectorAll('button')].find(item => item.textContent === 'Show earlier questions');
      return button instanceof HTMLButtonElement && !button.disabled;
    });
    await thirdPage.click();
    await f.page.waitForFunction(count => window.transport.filter(item => item.path.includes('/v1/conversations/chat-large/queries')).length > count, transcriptRequests);
    await f.page.waitForFunction(() => document.querySelectorAll('[aria-label="Conversation transcript"] article').length > 0);
    assert((await transcript.getByRole('article').count()) < 30, 'Virtualizer must keep the mounted article count bounded');
    await transcript.evaluate(node => { node.scrollTop = node.scrollHeight; node.dispatchEvent(new Event('scroll', { bubbles: true })); });
    const focusedSource = transcript.getByRole('listitem').last(); await focusedSource.focus();
    const focusedRowKey = await focusedSource.evaluate(node => node.closest('[data-row-key]')?.getAttribute('data-row-key'));
    assert(focusedRowKey);
    await transcript.evaluate(node => { node.scrollTop = 0; node.dispatchEvent(new Event('scroll', { bubbles: true })); });
    await f.page.waitForTimeout(100);
    const retainedSource = transcript.locator(`[data-row-key="${focusedRowKey}"]`).getByRole('listitem').last();
    assert.equal(await retainedSource.evaluate(node => node === document.activeElement && node.isConnected), true, 'Focused virtual row remains mounted');
    await retainedSource.click();
    const drawer = f.page.getByRole('dialog', { name: 'Source 1: Private salary.md', exact: true }); await drawer.waitFor();
    await transcript.evaluate(node => { node.scrollTop = 0; node.dispatchEvent(new Event('scroll', { bubbles: true })); });
    await drawer.getByRole('button', { name: 'Close', exact: true }).click();
    const jump = f.page.getByRole('button', { name: 'Jump to latest', exact: true }); await jump.waitFor();
    assert.equal(await jump.evaluate(node => node === document.activeElement), true);
    await jump.click();
    const readerSource = transcript.getByRole('listitem').last(); await readerSource.click(); await drawer.waitFor();
    await drawer.getByRole('button', { name: 'Open in document', exact: true }).click();
    const reader = f.page.getByRole('dialog', { name: 'Read Private salary.md', exact: true }); await reader.waitFor();
    await transcript.evaluate(node => { node.scrollTop = 0; node.dispatchEvent(new Event('scroll', { bubbles: true })); });
    await f.page.keyboard.press('Escape'); await reader.waitFor({ state: 'detached' }); await drawer.waitFor();
    await drawer.getByRole('button', { name: 'Close', exact: true }).click();
    assert.equal(await jump.evaluate(node => node === document.activeElement), true, 'Reader and source close restore a mounted focus target');
  } finally { await f.close(); }
});

test('switching conversations resets a scrolled transcript to the latest row', async browser => {
  const conversations = [
    { id: 'chat-a', collection_id: pub, title: 'Long A', archived: false, legacy: false, created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-30T10:00:00Z', preview: null },
    { id: 'chat-b', collection_id: pub, title: 'Short B', archived: false, legacy: false, created_at: '2026-09-09T00:00:00Z', updated_at: '2026-09-29T10:00:00Z', preview: null },
  ];
  const history = [
    ...Array.from({ length: 40 }, (_, index) => historyRow({ id: `q-a-${index + 1}`, conversationId: 'chat-a', question: `A ${index + 1}`, createdAt: new Date(Date.UTC(2026, 8, 1, 0, index)).toISOString() })),
    ...Array.from({ length: 10 }, (_, index) => historyRow({ id: `q-b-${index + 1}`, conversationId: 'chat-b', question: `B ${index + 1}`, createdAt: new Date(Date.UTC(2026, 8, 2, 0, index)).toISOString() })),
  ];
  const f = await fixture(browser, { conversations, history, historyPageSize: 40 }); try {
    const transcript = f.page.getByLabel('Conversation transcript', { exact: true });
    await f.page.getByRole('article', { name: 'A 40', exact: true }).waitFor();
    await transcript.evaluate(node => { node.scrollTop = 0; node.dispatchEvent(new Event('scroll', { bubbles: true })); });
    await f.page.getByRole('region', { name: 'Chats', exact: true }).getByRole('button', { name: 'Short B', exact: true }).click();
    await f.page.getByRole('article', { name: 'B 10', exact: true }).waitFor();
    const gap = await transcript.evaluate(node => node.scrollHeight - node.scrollTop - node.clientHeight);
    assert(gap < 64, `Expected the selected transcript at its latest row, gap=${gap}`);
  } finally { await f.close(); }
});

module.exports = { fixture, login, ask };
if (require.main === module) (async () => {
  const browser = await chromium.launch({ executablePath: process.env.DOCQA_CHROMIUM || process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH, headless: true });
  let failed = 0;
  try { for (const t of tests.filter(t => !process.env.DOCQA_TEST_FILTER || new RegExp(process.env.DOCQA_TEST_FILTER).test(t.name))) { try { await t.run(browser); console.log(`PASS ${t.name}`); } catch (e) { failed++; console.error(`FAIL ${t.name}\n${e.stack}`); } } }
  finally { await browser.close(); }
  console.log(JSON.stringify({ suite: 'accounts', failed, total: tests.filter(t => !process.env.DOCQA_TEST_FILTER || new RegExp(process.env.DOCQA_TEST_FILTER).test(t.name)).length })); process.exitCode = failed ? 1 : 0;
})();
