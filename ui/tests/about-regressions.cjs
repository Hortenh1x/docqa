/* Public publication navigation, with the API deliberately unavailable. */
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { chromium } = require(process.env.DOCQA_PLAYWRIGHT || 'playwright');
const base = process.env.DOCQA_UI_URL || 'http://127.0.0.1:18326';
assert(['localhost', '127.0.0.1'].includes(new URL(base).hostname));

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.DOCQA_CHROMIUM, headless: true });
  try {
    for (const width of [320, 1280]) {
      const context = await browser.newContext({ viewport: { width, height: 900 } });
      const apiRequests = [];
      await context.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.pathname.startsWith('/v1/')) {
          apiRequests.push(url.pathname);
          return route.abort();
        }
        return url.origin === new URL(base).origin ? route.continue() : route.abort();
      });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`${base}/about`);
      await page.getByRole('heading', { name: 'About DocQA', exact: true }).waitFor();
      assert.equal(apiRequests.length, 0, 'About must not bootstrap an API session');
      assert(await page.getByRole('link', { name: 'dmytro.bolibok@gmail.com', exact: true }).isVisible());
      const download = page.getByRole('link', { name: 'Download the corresponding source for this build' });
      await download.waitFor();
      const archive = await page.request.get(new URL(await download.getAttribute('href'), base).href);
      assert.equal(archive.status(), 200);
      const offer = await (await page.request.get(`${base}/source/manifest.json`)).json();
      assert.equal(createHash('sha256').update(await archive.body()).digest('hex'), offer.sha256);
      assert.equal((await page.request.get(`${base}/source/LICENSE.txt`)).status(), 200);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);

      await page.getByRole('link', { name: 'Back to Ask', exact: true }).click();
      await page.waitForURL(`${base}/`);
      assert.equal(await page.locator('a[href*="github.com"], a[href^="/source/"]').count(), 0);
      const about = page.getByRole('contentinfo').getByRole('link', { name: 'About', exact: true });
      await about.focus();
      assert(await about.evaluate(element => element === document.activeElement));
      await page.keyboard.press('Enter');
      await page.waitForURL(`${base}/about`);
      await page.getByRole('heading', { name: 'License & source code' }).waitFor();
      assert.deepEqual(errors, []);
      console.log(`PASS: About public access, source download and footer navigation at ${width}px`);
      await context.close();
    }
    const noScript = await browser.newContext({ javaScriptEnabled: false });
    const page = await noScript.newPage();
    await page.goto(`${base}/about`);
    assert(await page.getByRole('heading', { name: 'About DocQA', exact: true }).isVisible());
    assert(await page.getByRole('link', { name: 'Download the corresponding source for this build' }).isVisible());
    await noScript.close();
    console.log('PASS: About and source offer readable without JavaScript');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
