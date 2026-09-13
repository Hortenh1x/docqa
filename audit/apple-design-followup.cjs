/* Additional read-only measurements; source interactions use synthetic local API fixtures. */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('../ui/node_modules/playwright');
const { fixture, ask } = require('../ui/tests/account-regressions.cjs');
const out = path.join(__dirname, 'evidence/apple-design-2026-09-12');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/chromium', headless: true });
  const result = { timestamp: new Date().toISOString(), motion: [] };
  try {
    const f = await fixture(browser, { width: 1440 });
    await ask(f.page);
    const trigger = f.page.getByRole('button', { name: 'Source 1: Private salary.md, pages 1–1', exact: true });
    for (const preference of ['no-preference', 'reduce']) {
      await f.page.emulateMedia({ reducedMotion: preference });
      await sleep(350);
      await f.page.evaluate(() => {
        window.auditFrames = [];
        const target = document.querySelector('main [class*="transition-[margin]"]');
        const start = performance.now();
        function sample(time) {
          window.auditFrames.push({ time: time - start, marginRight: parseFloat(getComputedStyle(target).marginRight), animations: target.getAnimations().map(a => ({ property: a.transitionProperty, duration: a.effect.getTiming().duration })) });
          if (time - start < 600) requestAnimationFrame(sample);
        }
        requestAnimationFrame(sample);
      });
      await trigger.click();
      await sleep(650);
      result.motion.push(await f.page.evaluate(preference => ({ preference, matches: matchMedia('(prefers-reduced-motion: reduce)').matches, frames: window.auditFrames }), preference));
      await f.page.getByRole('button', { name: 'Close', exact: true }).click();
    }
    await sleep(350);
    await trigger.click();
    await f.page.evaluate(() => scrollTo(0, 0));
    await sleep(350);
    await f.page.screenshot({ path: path.join(out, 'source-desktop-viewport.png') });
    await f.page.getByRole('button', { name: 'Close', exact: true }).click();
    await f.page.setViewportSize({ width: 390, height: 844 });
    await trigger.click();
    await f.page.evaluate(() => scrollTo(0, 0));
    await sleep(350);
    await f.page.screenshot({ path: path.join(out, 'source-mobile-viewport.png') });
    await f.close();

    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await context.route('https://api.docqa.net/**', route => ['GET', 'OPTIONS'].includes(route.request().method()) ? route.continue() : route.abort());
    const page = await context.newPage();
    await page.goto('https://docqa.net/account', { waitUntil: 'networkidle' });
    result.inputContrast = await page.getByLabel('Email', { exact: true }).evaluate(el => {
      const s = getComputedStyle(el), canvas = document.createElement('canvas');
      canvas.width = canvas.height = 1;
      const ctx = canvas.getContext('2d');
      function rgb(color, background = 'white') {
        ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = background; ctx.fillRect(0, 0, 1, 1);
        ctx.fillStyle = color; ctx.fillRect(0, 0, 1, 1);
        return [...ctx.getImageData(0, 0, 1, 1).data].slice(0, 3);
      }
      function luminance(color) {
        return color.map(v => { const x = v / 255; return x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4; }).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
      }
      function contrast(a, b) { const values = [luminance(a), luminance(b)].sort((a, b) => b - a); return (values[0] + .05) / (values[1] + .05); }
      const outsideColor = getComputedStyle(document.documentElement).backgroundColor;
      const outside = rgb(outsideColor), inside = rgb(s.backgroundColor), border = rgb(s.borderTopColor, s.backgroundColor);
      return { field: el.name, borderColor: s.borderTopColor, backgroundColor: s.backgroundColor, backgroundClip: s.backgroundClip, outsideColor, borderWidth: s.borderTopWidth, borderRgb: border, insideRgb: inside, outsideRgb: outside, borderVsOutside: contrast(border, outside), borderVsInside: contrast(border, inside), insideVsOutside: contrast(inside, outside) };
    });
    await context.close();
    result.status = 'COMPLETED';
  } catch (e) { result.status = 'INCOMPLETE'; result.error = e.stack; process.exitCode = 1; }
  finally {
    await browser.close();
    fs.writeFileSync(path.join(out, 'followup.json'), JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify({ status: result.status, inputContrast: result.inputContrast, motion: result.motion.map(m => ({ preference: m.preference, partialFrames: m.frames.filter(f => f.marginRight > 0 && f.marginRight < 400).length, durations: [...new Set(m.frames.flatMap(f => f.animations.map(a => a.duration)))] })), error: result.error }));
  }
})();
