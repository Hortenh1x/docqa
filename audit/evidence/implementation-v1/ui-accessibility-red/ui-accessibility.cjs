/* Local, synthetic accessibility/reflow diagnostics. No UI files/builds are changed.
 * DOCQA_UI_URL=http://127.0.0.1:18127 DOCQA_PLAYWRIGHT=/path/to/playwright \
 *   DOCQA_CHROMIUM=/usr/bin/chromium node audit/ui-accessibility.cjs
 * The fixture is reused from ui/tests/browser-regressions.cjs. This measures a
 * stated subset of behavior; it is not a WCAG certification or screen-reader test.
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
process.env.DOCQA_UI_URL ||= 'http://127.0.0.1:18127';
const { chromium } = require(process.env.DOCQA_PLAYWRIGHT || process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const out = path.resolve(process.env.DOCQA_A11Y_OUT || path.join(root, 'audit/evidence/implementation-v1'));
fs.mkdirSync(out, { recursive: true });
const fixtureSource = fs.readFileSync(path.join(root, 'ui/tests/browser-regressions.cjs'), 'utf8');
const fixturePrefix = fixtureSource.slice(0, fixtureSource.indexOf('const tests = [];'));
assert(fixturePrefix.length > 1000, 'Expected reusable browser fixture prefix');
const { fixture, ask, useKey, collection, document: documentFixture, source, access, done } =
  new Function('require', 'process', `${fixturePrefix}\nreturn { fixture, ask, useKey, collection, document, source, access, done };`)(require, process);

const report = {
  timestamp: new Date().toISOString(), url: process.env.DOCQA_UI_URL,
  mode: 'Local final Docker UI; synthetic API fixture; Chromium',
  methodology: {
    reflow: 'Measure document scrollWidth versus layout viewport at 1280, 640, and 320 CSS pixels. Locally scrollable document tables/source rails are recorded separately.',
    zoom: '640 CSS-pixel viewport models the layout reflow of a 1280-pixel viewport at 200% page zoom. Text-only resize separately doubles each rendered HTML element’s computed font size and line height without increasing the viewport or layout spacing. This is an injected resize stress test, not a claim of native browser text-zoom equivalence.',
    contrast: 'Read computed foreground/background colors, resolve CSS colors via canvas, alpha-composite ancestor backgrounds, apply sRGB relative-luminance contrast formula. Compare small non-bold text with a 4.5:1 benchmark; exclude disabled controls. No OCR or anti-aliased edge pixels are used.',
    names: 'Capture browser accessibility snapshots and inspect DOM-provided labels/live text. No assistive technology was run.',
  },
  checks: [], contrast: [], keyboard: [], errors: [], failures: [],
};

async function measure(page, name) {
  const result = await page.evaluate(() => {
    const visible = el => {
      const s = getComputedStyle(el), r = el.getBoundingClientRect();
      return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0;
    };
    const elements = [...document.querySelectorAll('body *')].filter(visible);
    const scrolling = elements.filter(el => el.scrollWidth > el.clientWidth + 2 && ['auto', 'scroll'].includes(getComputedStyle(el).overflowX)).map(el => ({ tag: el.tagName, role: el.getAttribute('role'), class: el.className, width: el.clientWidth, scrollWidth: el.scrollWidth }));
    const outside = elements.filter(el => {
      const r = el.getBoundingClientRect();
      if (r.width <= 1 || getComputedStyle(el).position === 'absolute') return false;
      for (let p = el.parentElement; p; p = p.parentElement) {
        if (['auto', 'scroll', 'hidden'].includes(getComputedStyle(p).overflowX)) return false;
      }
      return r.left < -2 || r.right > innerWidth + 2;
    }).slice(0, 15).map(el => ({ tag: el.tagName, text: (el.innerText || el.getAttribute('aria-label') || '').slice(0, 100), class: el.className, rect: { x: el.getBoundingClientRect().x, width: el.getBoundingClientRect().width } }));
    return { viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight, scrolling, outside };
  });
  result.name = name;
  result.pass = result.scrollWidth <= result.viewport + 2;
  report.checks.push(result);
  if (!result.pass) report.failures.push({ kind: 'reflow', name, viewport: result.viewport, scrollWidth: result.scrollWidth });
  return result;
}

async function scaleText(page) {
  await page.evaluate(() => {
    const values = [...document.querySelectorAll('body *')]
      .filter(el => el instanceof HTMLElement && !['SCRIPT', 'STYLE'].includes(el.tagName))
      .map(el => ({ el, font: parseFloat(getComputedStyle(el).fontSize), line: parseFloat(getComputedStyle(el).lineHeight) }));
    for (const { el, font, line } of values) {
      el.style.setProperty('font-size', `${font * 2}px`, 'important');
      if (Number.isFinite(line)) el.style.setProperty('line-height', `${line * 2}px`, 'important');
    }
  });
}

async function contrast(page, name, locator, pseudo = null) {
  const reading = await locator.evaluate((el, pseudo) => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    const rgba = css => { ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = css; ctx.fillRect(0, 0, 1, 1); return [...ctx.getImageData(0, 0, 1, 1).data].map((v, i) => i === 3 ? v / 255 : v); };
    const over = (top, bottom) => [...top.slice(0, 3).map((v, i) => v * top[3] + bottom[i] * (1 - top[3])), 1];
    let background = [255, 255, 255, 1];
    const ancestors = []; for (let p = el; p; p = p.parentElement) ancestors.unshift(p);
    for (const p of ancestors) background = over(rgba(getComputedStyle(p).backgroundColor), background);
    const style = getComputedStyle(el, pseudo);
    const foreground = over(rgba(style.color), background);
    const luminance = rgb => rgb.slice(0, 3).map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
    const a = luminance(foreground), b = luminance(background);
    return { text: (pseudo ? el.getAttribute('placeholder') : el.textContent).trim().slice(0, 120), foreground: foreground.slice(0, 3).map(v => +v.toFixed(2)), background: background.slice(0, 3).map(v => +v.toFixed(2)), rawColor: style.color, fontSize: style.fontSize, fontWeight: style.fontWeight, ratio: +((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)).toFixed(3) };
  }, pseudo);
  reading.name = name; reading.pass = reading.ratio >= 4.5;
  report.contrast.push(reading);
  if (!reading.pass) report.failures.push({ kind: 'contrast', name, ratio: reading.ratio, benchmark: 4.5 });
}

async function tabInventory(page, name, required) {
  // Starting at document body permits a deterministic full keyboard traversal.
  await page.evaluate(() => { document.body.tabIndex = -1; document.body.focus(); });
  const seen = [];
  for (let i = 0; i < 36; i++) {
    await page.keyboard.press('Tab');
    const active = await page.evaluate(() => {
      const el = document.activeElement;
      const style = getComputedStyle(el);
      return { tag: el.tagName, role: el.getAttribute('role'), name: el.getAttribute('aria-label') || el.innerText || el.getAttribute('placeholder') || '', outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, x: +el.getBoundingClientRect().x.toFixed(1), width: +el.getBoundingClientRect().width.toFixed(1) };
    });
    if (i && active.tag === 'BODY') break;
    seen.push(active);
  }
  const missing = required.filter(label => !seen.some(item => item.name.trim() === label));
  report.keyboard.push({ name, pass: !missing.length, missing, seen });
  if (missing.length) report.failures.push({ kind: 'keyboard', name, missing });
}

const reply = (answer, overrides = {}) => [
  ['meta', { query_id: source.document_id, access }],
  ['sources', { sources: [source] }],
  ['delta', { text: answer }],
  ['done', { ...done, answer, ...overrides }],
].map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('');
const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'GET,POST,DELETE,OPTIONS', 'access-control-expose-headers': 'X-Total-Count', 'X-Total-Count': '4' };
const shot = (page, name) => page.screenshot({ path: path.join(out, `ui-accessibility-${name}.png`), fullPage: true });
async function submitQuestion(page) {
  await page.getByLabel('Your question').fill('Synthetic accessibility question');
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await page.getByRole('button', { name: 'Source 1: tenant-A.md, pages 1–1', exact: true }).first().waitFor();
}

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.DOCQA_CHROMIUM || process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
  try {
    // Real Tab and Enter events traverse and activate the shipped app's controls.
    const keyboardFixture = await fixture(browser);
    try {
      const { page } = keyboardFixture;
      await page.evaluate(() => document.fonts.ready);
      await page.getByLabel('Your question').fill('Keyboard question');
      await tabInventory(page, 'Ask', ['DocQA', 'Ask', 'Library', 'Usage', 'Collection', 'Access role', 'set API key', 'Your question']);
      await page.getByRole('link', { name: 'Library', exact: true }).focus();
      await page.keyboard.press('Enter');
      await page.getByRole('button', { name: 'tenant-A.md', exact: true }).waitFor();
      await tabInventory(page, 'Library', ['DocQA', 'Ask', 'Library', 'Usage', 'Collection', 'Access role', 'Choose a file', 'tenant-A.md', 'Delete tenant-A.md']);
      await page.getByRole('link', { name: 'Usage', exact: true }).focus();
      await page.keyboard.press('Enter');
      await page.getByRole('heading', { name: 'Usage', exact: true }).waitFor();
      await tabInventory(page, 'Usage', ['DocQA', 'Ask', 'Library', 'Usage', 'Collection', 'Access role']);
      await page.getByRole('link', { name: 'Ask', exact: true }).focus();
      await page.keyboard.press('Enter');
      await page.getByLabel('Your question').waitFor();
      await page.keyboard.press('/');
      assert(await page.getByLabel('Your question').evaluate(el => el === document.activeElement));
      report.checks.push({ name: 'keyboard route activation and slash shortcut', pass: true });
      await contrast(page, 'API key secondary link on paper', page.getByRole('button', { name: 'set API key', exact: true }));
      await contrast(page, 'composer placeholder', page.getByLabel('Your question'), '::placeholder');
      await page.getByLabel('Your question').fill('Test live response');
      await contrast(page, 'enabled Ask button', page.getByRole('button', { name: 'Ask', exact: true }));
      await page.keyboard.press('Enter');
      await page.getByRole('button', { name: 'Source 1: tenant-A.md, pages 1–1', exact: true }).waitFor();
      const live = await page.locator('[aria-live="polite"]').first().textContent();
      report.checks.push({ name: 'settled answer polite live message', pass: live.startsWith('Answer ready:'), text: live });
      await contrast(page, 'grounded status on paper', page.getByText('● grounded', { exact: true }));
      await contrast(page, 'answer metadata on paper', page.locator('p').filter({ hasText: 'confidence 0.90' }));
      await contrast(page, 'citation link', page.getByRole('button', { name: 'Source 1: tenant-A.md, pages 1–1', exact: true }));
      fs.writeFileSync(path.join(out, 'ui-accessibility-ask-aria.txt'), await page.locator('body').ariaSnapshot());
    } finally { await keyboardFixture.close(); }

    // Baseline layout, 200% page-zoom reflow equivalent, and separate 200% text resize.
    for (const width of [1280, 640, 320]) {
      for (const route of ['/', '/library', '/usage']) {
        const f = await fixture(browser, { width, path: route });
        try {
          await f.page.evaluate(() => document.fonts.ready);
          if (route === '/library') await f.page.getByRole('button', { name: 'tenant-A.md', exact: true }).waitFor();
          if (route === '/usage') await f.page.getByText('91', { exact: true }).waitFor();
          const label = route === '/' ? 'ask' : route.slice(1);
          await measure(f.page, `${label} ${width}px 100% text`);
          await scaleText(f.page);
          await measure(f.page, `${label} ${width}px 200% text`);
          await shot(f.page, `${label}-${width}-text200`);
        } finally { await f.close(); }
      }
    }

    // Long prose, an unbroken identifier, and long filename display data.
    for (const width of [1280, 320]) {
      const f = await fixture(browser, { width });
      try {
        const { page, context } = f;
        let answer = Array(18).fill('Employees submit their reimbursement request with supporting receipts and manager approval. The policy applies to eligible business travel. [1]').join('\n\n');
        await context.route('**/v1/query', route => route.request().method() === 'OPTIONS'
          ? route.fulfill({ status: 200, headers })
          : route.fulfill({ status: 200, headers, contentType: 'text/event-stream', body: reply(answer, { confidence: 0.51 }) }));
        await submitQuestion(page);
        await measure(page, `long prose answer ${width}px`);
        await contrast(page, `partial status on paper ${width}px`, page.getByText('● partial', { exact: true }));
        answer = `The reference identifier is ${'A'.repeat(160)}. [1]`;
        await submitQuestion(page);
        await page.locator('p').filter({ hasText: `The reference identifier is ${'A'.repeat(160)}.` }).first().waitFor();
        await measure(page, `unbroken answer identifier ${width}px`);
        await shot(page, `long-answer-${width}`);
        const longFilename = 'Handbuch_Reisekosten_und_Abrechnungsrichtlinien_fuer_internationale_Geschaeftsreisen_'.repeat(3) + '2026.md';
        await context.route('**/v1/collections/*/documents*', route => route.request().method() === 'OPTIONS'
          ? route.fulfill({ status: 200, headers })
          : route.fulfill({ status: 200, headers, contentType: 'application/json', body: JSON.stringify([{ ...documentFixture('A'), filename: longFilename }]) }));
        await page.getByRole('link', { name: 'Library', exact: true }).click();
        const trigger = page.getByRole('button', { name: longFilename, exact: true });
        await trigger.waitFor();
        await measure(page, `long filename Library ${width}px`);
        assert.equal(await trigger.getAttribute('title'), `Read ${longFilename}`);
        report.checks.push({ name: `long filename accessible name/title ${width}px`, pass: true, filenameLength: longFilename.length });
        await trigger.click();
        await page.locator('pre').waitFor();
        await measure(page, `long filename reader ${width}px`);
        await shot(page, `long-filename-reader-${width}`);
      } finally { await f.close(); }
    }

    // Every shipped document status, plus error detail and retry, on actual colors.
    const f = await fixture(browser, { path: '/library' });
    try {
      const { page, context } = f;
      await context.route('**/v1/collections/*/documents*', route => route.request().method() === 'OPTIONS'
        ? route.fulfill({ status: 200, headers })
        : route.fulfill({ status: 200, headers, contentType: 'application/json', body: JSON.stringify(['pending', 'processing', 'ready', 'failed'].map((status, i) => ({ ...documentFixture('A'), id: `22222222-2222-4222-8222-${String(i + 1).padStart(12, '0')}`, filename: `${status}.md`, status, error: status === 'failed' ? 'Synthetic parser error' : null }))) }));
      await page.reload();
      for (const status of ['pending', 'processing', 'ready', 'failed']) {
        const badge = page.getByText(status, { exact: true });
        await badge.waitFor();
        await contrast(page, `${status} document status on white`, badge);
      }
      await contrast(page, 'upload hint on white', page.getByText('Drop PDF, DOCX, MD or TXT · up to 25 MB', { exact: true }));
      await contrast(page, 'document table heading on white', page.getByRole('columnheader', { name: 'Document', exact: true }));
      page.once('dialog', dialog => dialog.accept());
      await page.getByRole('button', { name: 'Delete ready.md', exact: true }).click();
      const alert = page.getByRole('main').getByRole('alert');
      await alert.waitFor();
      await contrast(page, 'delete error on white', alert.locator('p'));
      report.checks.push({ name: 'delete error alert and named retry', pass: (await alert.innerText()).includes('Storage is temporarily unavailable') && await page.getByRole('button', { name: 'Retry delete ready.md', exact: true }).count() === 1 });
      await shot(page, 'status-contrast');
      fs.writeFileSync(path.join(out, 'ui-accessibility-library-aria.txt'), await page.locator('body').ariaSnapshot());
    } finally { await f.close(); }
  } catch (error) {
    report.errors.push(error.stack);
  } finally {
    await browser.close();
    for (const check of report.checks.filter(check => !check.pass && !('viewport' in check))) {
      report.failures.push({ kind: 'semantic', name: check.name });
    }
    report.summary = { checks: report.checks.length, contrastPairs: report.contrast.length, keyboardRoutes: report.keyboard.length, failures: report.failures.length, executionErrors: report.errors.length };
    fs.writeFileSync(path.join(out, 'ui-accessibility-results.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report, null, 2));
    if (report.errors.length || report.failures.length) process.exitCode = 1;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
