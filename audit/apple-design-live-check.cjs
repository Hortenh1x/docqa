/* Production verification: public GETs and local-only form validation. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { chromium } = require('../ui/node_modules/playwright');
const out = path.join(__dirname, 'evidence/apple-design-fixes-2026-09-12');
const expected = '1d284dac465cc8877aae85f957ba242b4f75c39bf0123244100e7fa693db9636';
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/chromium', headless: true });
  const report = { timestamp: new Date().toISOString(), pages: [], mutations: [], errors: [] };
  try {
    const context = await browser.newContext();
    await context.route('https://api.docqa.net/**', route => {
      if (['GET','OPTIONS'].includes(route.request().method())) return route.continue();
      report.mutations.push({ method: route.request().method(), path: new URL(route.request().url()).pathname });
      return route.abort();
    });
    const page = await context.newPage();
    page.on('pageerror', e => report.errors.push(e.message));
    for (const width of [1440,390,320]) {
      await page.setViewportSize({ width, height: width === 1440 ? 900 : 844 });
      for (const route of ['/', '/library', '/usage', '/account', '/account/register', '/about']) {
        const response = await page.goto('https://docqa.net'+route, { waitUntil: 'networkidle' });
        assert.equal(response.status(),200);
        const item = await page.evaluate(() => ({ path: location.pathname, width: innerWidth, documentWidth: document.documentElement.scrollWidth }));
        assert(item.documentWidth <= width); report.pages.push(item);
        if (route === '/account' && width === 390) {
          const email = page.getByLabel('Email', { exact: true });
          report.inputBorder = await email.evaluate(el => getComputedStyle(el).borderTopColor);
          assert.equal(report.inputBorder,'rgb(133, 129, 116)');
          report.googleVisible = await page.getByRole('button', {name:'Continue with Google',exact:true}).isVisible();
          assert(report.googleVisible);
          await page.screenshot({ path: path.join(out,'live-account-390.png'), fullPage: true });
        }
        if (route === '/library' && width === 320) await page.screenshot({ path: path.join(out,'live-library-320.png'), fullPage: true });
      }
    }
    await page.goto('https://docqa.net/account/register', { waitUntil: 'networkidle' });
    await page.getByLabel('Password', {exact:true}).fill('aaaaaaa1');
    const confirm = page.getByLabel('Confirm password', {exact:true});
    await confirm.fill('aaaaaaa2'); await confirm.press('Tab');
    assert.equal(await confirm.getAttribute('aria-invalid'),'true');
    await page.getByText('Passwords do not match.', {exact:true}).waitFor();
    report.earlyPasswordMismatch = true;
    await confirm.fill('aaaaaaa1');
    assert.notEqual(await confirm.getAttribute('aria-invalid'),'true');
    report.mismatchClears = true;
    await page.goto('https://docqa.net/about', {waitUntil:'networkidle'});
    const archiveLink = page.locator('a[href$=".tar.gz"]');
    const archiveUrl = new URL(await archiveLink.getAttribute('href'),page.url()).href;
    const archive = await context.request.get(archiveUrl);
    assert.equal(archive.status(),200);
    report.source = { url: archiveUrl, sha256: createHash('sha256').update(await archive.body()).digest('hex') };
    assert.equal(report.source.sha256,expected);
    const ready = await context.request.get('https://api.docqa.net/readyz');
    assert.equal(ready.status(),200); report.readiness = 200;
    assert.deepEqual(report.errors,[]); assert.deepEqual(report.mutations,[]);
    await context.close(); report.status='PASS';
  } catch(e) { report.status='FAIL';report.error=e.stack;process.exitCode=1; }
  finally { await browser.close();fs.writeFileSync(path.join(out,'live-verification.json'),JSON.stringify(report,null,2)+'\n'); console.log(JSON.stringify(report)); }
})();
