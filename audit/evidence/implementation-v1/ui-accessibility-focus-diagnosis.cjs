const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.DOCQA_PLAYWRIGHT || process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../../..');
const fixtureSource = fs.readFileSync(path.join(root, 'ui/tests/browser-regressions.cjs'), 'utf8');
const { fixture } = new Function('require', 'process', fixtureSource.slice(0, fixtureSource.indexOf('const tests = [];')) + '\nreturn { fixture };')(require, process);
async function traverse(page) {
  await page.evaluate(() => { document.body.tabIndex = -1; document.body.focus(); });
  for (let i = 0; i < 36; i++) {
    await page.keyboard.press('Tab');
    if (i && await page.evaluate(() => document.activeElement.tagName === 'BODY')) break;
  }
}
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.DOCQA_CHROMIUM || '/usr/bin/chromium' });
  const results = [];
  try {
    for (let i = 0; i < Number(process.env.DOCQA_FOCUS_RUNS || 12); i++) {
      const f = await fixture(browser);
      try {
        const { page } = f;
        await page.evaluate(() => {
          window.focusTrace = [];
          const snapshot = label => {
            const active = document.activeElement;
            const field = document.querySelector('[aria-label="Your question"]');
            const s = { label, time: performance.now(), path: location.pathname,
              active: { tag: active.tagName, label: active.getAttribute('aria-label'), text: active.textContent.slice(0, 50) },
              field: field ? { disabled: field.disabled, connected: field.isConnected, visible: field.getBoundingClientRect().width > 0, focused: field === active } : null };
            window.focusTrace.push(s);
            return s;
          };
          window.focusSnapshot = snapshot;
          document.addEventListener('focusin', () => snapshot('focusin'));
          document.addEventListener('keydown', e => {
            if (e.key === '/') {
              snapshot('slash capture');
              queueMicrotask(() => snapshot('slash microtask'));
            }
          }, true);
          const originalAdd = document.addEventListener;
          document.addEventListener = function(type, listener, ...args) {
            if (type === 'keydown') snapshot('keydown listener added');
            return originalAdd.call(this, type, listener, ...args);
          };
        });
        await page.getByLabel('Your question').fill('Keyboard question');
        await traverse(page);
        for (const name of ['Library', 'Usage']) {
          await page.getByRole('link', { name, exact: true }).focus();
          await page.keyboard.press('Enter');
          if (name === 'Library') await page.getByRole('button', { name: 'tenant-A.md', exact: true }).waitFor();
          else await page.getByRole('heading', { name: 'Usage', exact: true }).waitFor();
          await traverse(page);
        }
        await page.getByRole('link', { name: 'Ask', exact: true }).focus();
        await page.keyboard.press('Enter');
        await page.getByLabel('Your question').waitFor();
        if (process.env.DOCQA_FOCUS_SYNC === 'true') {
          await page.getByLabel('Your question').fill('Keyboard readiness');
          await page.waitForFunction(() => {
            const field = document.querySelector('[aria-label="Your question"]');
            return location.pathname === '/' && field && !field.disabled &&
              field.value === 'Keyboard readiness' && !field.form.querySelector('button[type="submit"]').disabled;
          });
          await page.getByLabel('Your question').fill('');
          await page.getByRole('link', { name: 'Ask', exact: true }).focus();
        }
        await page.evaluate(() => window.focusSnapshot('before slash'));
        await page.keyboard.press('/');
        const immediate = await page.evaluate(() => window.focusSnapshot('after slash'));
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        const settled = await page.evaluate(() => window.focusSnapshot('two animation frames later'));
        results.push({ run: i + 1, immediate, settled, trace: await page.evaluate(() => window.focusTrace) });
      } finally { await f.close(); }
    }
  } finally { await browser.close(); }
  console.log(JSON.stringify(results, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
