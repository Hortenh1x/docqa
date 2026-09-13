/* Visual/accessibility measurements after the fixes; synthetic API only. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('../ui/node_modules/playwright');
const { fixture, login, ask } = require('../ui/tests/account-regressions.cjs');
const out = path.join(__dirname, 'evidence/apple-design-fixes-2026-09-12');
const pause = ms => new Promise(r => setTimeout(r, ms));
const result = { pages: [], preferences: [], targets: [], pressed: [] };
async function controlStyle(locator) {
  return locator.evaluate(el => { const s = getComputedStyle(el), r = el.getBoundingClientRect(); return { background: s.backgroundColor, border: s.borderColor, outline: s.outlineWidth, backdrop: s.backdropFilter, width: r.width, height: r.height }; });
}
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/chromium', headless: true });
  try {
    const f = await fixture(browser, { width: 390, google: true });
    for (const width of [1440, 390, 320]) {
      await f.page.setViewportSize({ width, height: width === 1440 ? 900 : 844 });
      for (const route of ['/', '/library', '/usage', '/account', '/account/register', '/about']) {
        await f.page.goto(process.env.DOCQA_UI_URL + route, { waitUntil: 'networkidle' });
        const record = await f.page.evaluate(() => ({ path: location.pathname, width: innerWidth, documentWidth: document.documentElement.scrollWidth }));
        result.pages.push(record); assert(record.documentWidth <= width, JSON.stringify(record));
        if (route === '/account' || route === '/') await f.page.screenshot({ path: path.join(out, `${route === '/' ? 'ask' : 'account'}-${width}.png`), fullPage: true });
      }
    }
    await f.page.goto(process.env.DOCQA_UI_URL + '/account', { waitUntil: 'networkidle' });
    const cdp = await f.context.newCDPSession(f.page);
    for (const features of [[], [{ name: 'prefers-contrast', value: 'more' }], [{ name: 'prefers-reduced-transparency', value: 'reduce' }]]) {
      await cdp.send('Emulation.setEmulatedMedia', { features });
      const input = f.page.getByLabel('Email', { exact: true });
      await input.focus();
      const record = { features, field: await controlStyle(input), header: await controlStyle(f.page.locator('header')) };
      record.contrast = await input.evaluate(el => {
        const s = getComputedStyle(el), c = document.createElement('canvas').getContext('2d');
        function lum(color) { c.fillStyle = color; c.fillRect(0, 0, 1, 1); return [...c.getImageData(0, 0, 1, 1).data].slice(0,3).map(v => v/255).map(x => x <= .04045 ? x/12.92 : ((x+.055)/1.055)**2.4).reduce((sum,v,i) => sum+v*[.2126,.7152,.0722][i],0); }
        const values = [lum(s.borderTopColor), lum(getComputedStyle(document.documentElement).backgroundColor)].sort((a,b) => b-a);
        return (values[0]+.05)/(values[1]+.05);
      });
      result.preferences.push(record); assert(record.contrast >= 3);
      if (features.length) assert.equal(record.header.backdrop, 'none');
    }
    assert.notEqual(result.preferences[0].field.border, result.preferences[1].field.border);
    await cdp.send('Emulation.setEmulatedMedia', { features: [] });
    for (const name of ['Sign in', 'Continue with Google']) {
      const button = f.page.getByRole('button', { name, exact: true });
      await button.scrollIntoViewIfNeeded(); const r = await button.boundingBox();
      await f.page.mouse.move(r.x+r.width/2, r.y+r.height/2); await pause(150);
      const before = await controlStyle(button); await f.page.mouse.down();
      const during = await controlStyle(button); await f.page.mouse.move(0,0); await f.page.mouse.up();
      assert.notEqual(before.background, during.background); result.pressed.push({ name, before, during });
    }
    assert.equal(f.state.requests.filter(r => r.path.endsWith('/login') || r.path.endsWith('/google/start')).length, 0);
    await f.page.goto(process.env.DOCQA_UI_URL + '/'); await ask(f.page);
    const trigger = f.page.getByRole('button', { name: 'Source 1: Private salary.md, pages 1–1', exact: true });
    for (const width of [1440, 390]) {
      await f.page.setViewportSize({ width, height: width === 1440 ? 900 : 844 });
      await f.page.emulateMedia({ reducedMotion: 'reduce' }); await trigger.click();
      await f.page.mouse.move(0,0); await f.page.evaluate(() => scrollTo(0,0));
      const transitions = await f.page.locator('main > div').evaluate(el => getComputedStyle(el).transitionDuration);
      assert.equal(transitions, '0s'); result.reducedMotionDuration = transitions;
      await f.page.screenshot({ path: path.join(out, `source-${width}.png`) });
      const close = f.page.getByRole('button', { name: 'Close', exact: true });
      const target = await controlStyle(close); assert(target.height >= 44); result.targets.push({ name: 'Close source', width, ...target });
      await close.click();
    }
    await login(f.page); await f.page.getByRole('link', { name: 'Library', exact: true }).click();
    await f.page.getByLabel('Collection', { exact: true }).selectOption('22222222-2222-4222-8222-222222222222');
    for (const width of [1440, 390, 320]) {
      await f.page.setViewportSize({ width, height: width === 1440 ? 900 : 844 });
      await f.page.getByRole('region', { name: 'Document storage' }).waitFor();
      await f.page.screenshot({ path: path.join(out, `private-library-${width}.png`), fullPage: true });
      for (const name of ['Choose a file', 'Delete Private salary.md']) {
        const target = await controlStyle(f.page.getByRole('button', { name, exact: true }));
        assert(target.height >= 44); result.targets.push({ name, width, ...target });
      }
      assert.equal(await f.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    }
    await f.close(); result.status = 'PASS';
  } catch (e) { result.status = 'FAIL'; result.error = e.stack; process.exitCode = 1; }
  finally { await browser.close(); fs.writeFileSync(path.join(out, 'visual-verification.json'), JSON.stringify(result,null,2)+'\n'); console.log(JSON.stringify({ status: result.status, pages: result.pages.length, contrast: result.preferences.map(p => p.contrast), error: result.error })); }
})();
