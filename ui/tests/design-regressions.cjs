/* Interaction regressions for the Apple-design audit; API data is synthetic. */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { fixture, ask, login } = require('./account-regressions.cjs');
const tests = [];
const test = (name, run) => tests.push({ name, run });
const source = page => page.getByRole('button', { name: 'Source 1: Private salary.md, pages 1–1', exact: true });

test('desktop source allows keyboard access to the background and restores focus', async browser => {
  const f = await fixture(browser, { width: 1440 });
  try {
    await ask(f.page); await source(f.page).click();
    const dialog = f.page.getByRole('dialog');
    assert.notEqual(await dialog.getAttribute('aria-modal'), 'true');
    let reachedBackground = false;
    const maxTabs = await f.page.locator('button,a,input,textarea,select').count() + 1;
    for (let i = 0; i < maxTabs; i++) {
      await f.page.keyboard.press('Tab');
      if (await f.page.evaluate(() => document.activeElement === document.querySelector('textarea[aria-label="Your question"]'))) reachedBackground = true;
    }
    assert(reachedBackground, 'Tab must reach the composer while the source stays open');
    await f.page.keyboard.press('Escape');
    await dialog.waitFor({ state: 'hidden' });
    assert(await source(f.page).evaluate(el => document.activeElement === el));
  } finally { await f.close(); }
});

test('mobile source blocks background focus and adapts modality across breakpoints', async browser => {
  const f = await fixture(browser, { width: 390 });
  try {
    await ask(f.page); await source(f.page).click();
    const dialog = f.page.getByRole('dialog');
    const composerFocused = () => f.page.getByLabel('Your question').evaluate(el => { el.focus(); return document.activeElement === el; });
    await f.page.keyboard.press('Shift+Tab');
    assert(await f.page.getByRole('button', { name: 'Copy citation', exact: true }).evaluate(el => document.activeElement === el));
    await f.page.keyboard.press('Tab');
    assert(await f.page.getByRole('button', { name: 'Close', exact: true }).evaluate(el => document.activeElement === el));
    assert.equal(await composerFocused(), false, 'Background must be inert');
    await f.page.setViewportSize({ width: 1440, height: 900 });
    await f.page.waitForFunction(() => document.querySelector('[role="dialog"],dialog')?.getAttribute('aria-modal') !== 'true');
    assert.equal(await composerFocused(), true);
    await f.page.setViewportSize({ width: 390, height: 844 });
    await f.page.waitForFunction(() => document.querySelector('[role="dialog"],dialog')?.getAttribute('aria-modal') === 'true');
    assert.equal(await composerFocused(), false);
    await f.page.keyboard.press('/');
    assert.equal(await composerFocused(), false);
    await f.page.getByRole('button', { name: 'Close', exact: true }).click();
    await dialog.waitFor({ state: 'hidden' });
    assert(await source(f.page).evaluate(el => document.activeElement === el));
    assert.equal(await f.page.evaluate(() => document.body.style.overflow), '');
    await source(f.page).click();
    await f.page.mouse.click(4, 4);
    await dialog.waitFor({ state: 'hidden' });
  } finally { await f.close(); }
});

test('copy citation reports success and resets when the source is reopened', async browser => {
  const f = await fixture(browser);
  try {
    await ask(f.page); await source(f.page).click();
    await f.page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: text => new Promise(resolve => { window.copiedCitation = text; window.finishCopy = resolve; }) } }));
    await f.page.getByRole('button', { name: 'Copy citation', exact: true }).click();
    await f.page.getByRole('button', { name: 'Copying…', exact: true }).waitFor();
    await f.page.evaluate(() => window.finishCopy());
    await f.page.getByRole('status').filter({ hasText: 'Citation copied.' }).waitFor();
    assert(await f.page.getByRole('button', { name: 'Copied', exact: true }).evaluate(el => document.activeElement === el), 'Clipboard completion must preserve keyboard focus');
    assert.match(await f.page.evaluate(() => window.copiedCitation), /Private salary.md/);
    await f.page.getByRole('button', { name: 'Close', exact: true }).click();
    await source(f.page).click();
    assert(await f.page.getByRole('button', { name: 'Copy citation', exact: true }).isVisible());
  } finally { await f.close(); }
});

test('clipboard denial offers a selectable citation without an unhandled error', async browser => {
  const f = await fixture(browser);
  try {
    await ask(f.page); await source(f.page).click();
    await f.page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: () => new Promise((resolve, reject) => { window.failCopy = () => reject(new DOMException('Clipboard denied', 'NotAllowedError')); }) } }));
    await f.page.getByRole('button', { name: 'Copy citation', exact: true }).click();
    await f.page.getByRole('button', { name: 'Copying…', exact: true }).waitFor();
    await f.page.evaluate(() => window.failCopy());
    const citation = f.page.getByRole('textbox', { name: 'Citation', exact: true });
    await citation.waitFor();
    assert(await f.page.getByRole('button', { name: 'Copy citation', exact: true }).evaluate(el => document.activeElement === el), 'Clipboard failure must preserve keyboard focus');
    await citation.focus();
    assert(await citation.evaluate(el => el.readOnly && el.selectionEnd - el.selectionStart === el.value.length));
    assert.match(await f.page.getByRole('dialog').getByRole('alert').innerText(), /copy.*manually/i);
  } finally { await f.close(); }
});

test('password confirmation validates after blur, clears when corrected, and blocks submission', async browser => {
  const f = await fixture(browser, { path: '/account/register' });
  try {
    const password = f.page.getByLabel('Password', { exact: true });
    const confirm = f.page.getByLabel('Confirm password', { exact: true });
    await f.page.getByLabel('Email', { exact: true }).fill('audit@example.test');
    await password.fill('aaaaaaa1'); await confirm.fill('aaaaaaa2');
    assert.notEqual(await confirm.getAttribute('aria-invalid'), 'true');
    await confirm.press('Tab');
    assert.equal(await confirm.getAttribute('aria-invalid'), 'true');
    await confirm.fill('aaaaaaa1');
    assert.notEqual(await confirm.getAttribute('aria-invalid'), 'true');
    await password.fill('bbbbbbb1');
    assert.equal(await confirm.getAttribute('aria-invalid'), 'true');
    await f.page.getByRole('button', { name: 'Create account', exact: true }).click();
    assert.equal(f.state.requests.filter(r => r.path.endsWith('/register')).length, 0);
    await confirm.fill('');
    assert.notEqual(await confirm.getAttribute('aria-invalid'), 'true');
    await confirm.fill('bbbbbbb1');
    assert.notEqual(await confirm.getAttribute('aria-invalid'), 'true');
  } finally { await f.close(); }
});

test('mobile document actions are visible without horizontal scrolling', async browser => {
  const f = await fixture(browser, { width: 320 });
  try {
    await login(f.page); await f.page.getByRole('link', { name: 'Library', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption('22222222-2222-4222-8222-222222222222');
    for (const width of [320, 390]) {
      await f.page.setViewportSize({ width, height: 844 });
      const remove = f.page.getByRole('button', { name: 'Delete Private salary.md', exact: true });
      await remove.waitFor();
      const box = await remove.boundingBox();
      assert(box.x >= 0 && box.x + box.width <= width, 'Delete must be inside the viewport before horizontal scrolling');
    }
    const read = f.page.getByRole('button', { name: 'Private salary.md', exact: true });
    await read.click();
    await f.page.getByRole('dialog').getByText('Private original salary text').waitFor();
    await f.page.getByRole('button', { name: 'Close', exact: true }).click();
    assert(await read.evaluate(el => document.activeElement === el));
    await f.page.getByRole('button', { name: 'Retry processing Private salary.md', exact: true }).click();
    await f.page.getByRole('button', { name: 'Retry processing Private salary.md', exact: true }).waitFor({ state: 'hidden' });
    f.page.once('dialog', d => d.accept());
    await f.page.getByRole('button', { name: 'Delete Private salary.md', exact: true }).click();
    await f.page.getByText('No documents yet.', { exact: true }).waitFor();
  } finally { await f.close(); }
});

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.DOCQA_CHROMIUM || process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH, headless: true });
  let failed = 0;
  try {
    for (const t of tests) {
      try { await t.run(browser); console.log(`PASS ${t.name}`); }
      catch (e) { failed++; console.error(`FAIL ${t.name}\n${e.stack}`); }
    }
  } finally { await browser.close(); }
  console.log(JSON.stringify({ suite: 'design', total: tests.length, failed }));
  process.exitCode = failed ? 1 : 0;
})();
