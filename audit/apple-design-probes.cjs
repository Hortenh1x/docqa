/* Read-only Apple-design diagnostics. Production requests are GET/OPTIONS only.
 * Stateful interactions use the existing local synthetic account fixture.
 * DOCQA_UI_URL=http://127.0.0.1:18141 node audit/apple-design-probes.cjs
 */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('../ui/node_modules/playwright');
const { fixture, login, ask } = require('../ui/tests/account-regressions.cjs');
const out = path.join(__dirname, 'evidence/apple-design-2026-09-12');
fs.mkdirSync(out, { recursive: true });
const report = { timestamp: new Date().toISOString(), live: [], interactions: {}, errors: [], attemptedLiveMutations: [] };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function style(locator) {
  return locator.evaluate(el => {
    const c = getComputedStyle(el), r = el.getBoundingClientRect();
    return { text: el.textContent.trim().slice(0, 100), x: r.x, y: r.y, width: r.width, height: r.height, font: c.fontFamily, fontSize: c.fontSize, lineHeight: c.lineHeight, tracking: c.letterSpacing, weight: c.fontWeight, optical: c.fontOpticalSizing, color: c.color, background: c.backgroundColor, border: c.borderColor, outline: c.outline, shadow: c.boxShadow, transform: c.transform, opacity: c.opacity, transition: c.transition, backdropFilter: c.backdropFilter, animation: c.animation };
  });
}
async function press(page, locator) {
  await locator.scrollIntoViewIfNeeded(); const b = await locator.boundingBox();
  await page.mouse.move(b.x + b.width/2, b.y + b.height/2); await sleep(180);
  const before = await style(locator); await page.mouse.down(); await sleep(130);
  const during = await style(locator);
  await page.mouse.move(0, 0); await page.mouse.up();
  const keys = ['color','background','border','outline','shadow','transform','opacity'];
  return { before, during, changed: keys.filter(k => before[k] !== during[k]) };
}
(async () => {
 const browser = await chromium.launch({ executablePath: '/usr/bin/chromium', headless: true });
 report.browser = browser.version();
 try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.route('https://api.docqa.net/**', async route => {
    if (['GET','OPTIONS'].includes(route.request().method())) return route.continue();
    report.attemptedLiveMutations.push({ method: route.request().method(), path: new URL(route.request().url()).pathname });
    return route.abort();
  });
  const page = await context.newPage();
  page.on('pageerror', e => report.errors.push({ source: 'live', message: e.message }));
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: width === 1440 ? 900 : 844 });
    for (const route of ['/', '/library', '/usage', '/account', '/account/register', '/about']) {
      await page.goto('https://docqa.net' + route, { waitUntil: 'networkidle' });
      if (route !== '/about') await page.getByLabel('Collection', { exact: true }).waitFor();
      const name = (route === '/' ? 'ask' : route.slice(1).replaceAll('/', '-')) + '-' + width;
      await page.screenshot({ path: path.join(out, name + '.png'), fullPage: true });
      const measure = await page.evaluate(() => ({
        url: location.pathname, width: innerWidth, height: innerHeight, documentWidth: document.documentElement.scrollWidth,
        headerHeight: document.querySelector('header')?.getBoundingClientRect().height,
        mainTop: document.querySelector('main')?.getBoundingClientRect().top,
        controls: [...document.querySelectorAll('button,a,select,input,textarea')].filter(el => {const r=el.getBoundingClientRect();return r.width>0&&r.height>0;}).map(el => {const r=el.getBoundingClientRect(),s=getComputedStyle(el);return {name:el.getAttribute('aria-label')||el.textContent.trim().slice(0,65)||el.getAttribute('name'),tag:el.tagName,width:r.width,height:r.height,fontSize:s.fontSize,x:r.x,y:r.y};}),
        headings: [...document.querySelectorAll('h1,h2')].map(el=>{const c=getComputedStyle(el);return {text:el.textContent,font:c.fontFamily,size:c.fontSize,weight:c.fontWeight,leading:c.lineHeight,tracking:c.letterSpacing,optical:c.fontOpticalSizing};}),
      }));
      report.live.push(measure);
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('https://docqa.net/account', { waitUntil: 'networkidle' });
  report.interactions.signInPress = await press(page, page.getByRole('button', { name: 'Sign in', exact: true }));
  report.interactions.googlePress = await press(page, page.getByRole('button', { name: 'Continue with Google', exact: true }));
  const cdp = await context.newCDPSession(page);
  const preferenceResults = [];
  for (const features of [[], [{name:'prefers-contrast',value:'more'}], [{name:'prefers-reduced-transparency',value:'reduce'}]]) {
    await cdp.send('Emulation.setEmulatedMedia', { features });
    preferenceResults.push({ features, matches: await page.evaluate(() => ({ contrast: matchMedia('(prefers-contrast: more)').matches, transparency: matchMedia('(prefers-reduced-transparency: reduce)').matches })), header: await style(page.locator('header')), field: await style(page.getByLabel('Email', { exact: true })) });
  }
  report.interactions.preferences = preferenceResults;
  await cdp.send('Emulation.setEmulatedMedia', {features:[]});
  await page.goto('https://docqa.net/account/register', { waitUntil:'networkidle' });
  await page.getByLabel('Email', {exact:true}).fill('audit@example.test');
  await page.getByLabel('Password', {exact:true}).fill('aaaaaaa1');
  await page.getByLabel('Confirm password', {exact:true}).fill('aaaaaaa2');
  await page.getByRole('heading', {name:'Create account',exact:true}).click();
  report.interactions.passwordMismatch = { beforeSubmitAlerts: await page.getByRole('alert').allTextContents(), ariaInvalidBefore: await page.getByLabel('Confirm password',{exact:true}).getAttribute('aria-invalid') };
  await page.getByRole('button',{name:'Create account',exact:true}).click();
  report.interactions.passwordMismatch.afterSubmitAlerts = await page.getByRole('alert').allTextContents();
  await page.screenshot({path:path.join(out,'registration-mismatch.png'),fullPage:true});
  await context.close();

  // Local fixtures: no real identity, private document, provider or email operation.
  const f = await fixture(browser, { width: 1440 });
  await ask(f.page);
  const trigger = f.page.getByRole('button',{name:'Source 1: Private salary.md, pages 1–1',exact:true});
  await trigger.click();
  const dialog = f.page.getByRole('dialog');
  await dialog.waitFor();
  const desktop = { dialog:await style(dialog), ariaModal:await dialog.getAttribute('aria-modal'), backdropVisible:await f.page.getByRole('button',{name:'Close source panel',exact:true}).isVisible() };
  desktop.focusSequence=[];
  for(let i=0;i<4;i++){await f.page.keyboard.press('Tab');desktop.focusSequence.push(await f.page.evaluate(()=>({name:document.activeElement.textContent,insideDialog:!!document.activeElement.closest('[role=dialog]')})));}
  await f.page.getByLabel('Your question').click();
  desktop.backgroundCanReceivePointerFocus=await f.page.getByLabel('Your question').evaluate(el=>document.activeElement===el);
  await f.page.screenshot({path:path.join(out,'source-desktop.png'),fullPage:true});
  report.interactions.sourceDesktop=desktop;
  await f.page.evaluate(()=>{window.auditClipboard=[];Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.auditClipboard.push(text);}}});});
  const copy=f.page.getByRole('button',{name:'Copy citation',exact:true});
  const beforeCopy=await copy.innerText();await copy.click();await sleep(350);
  report.interactions.copySuccess={before:beforeCopy,after:await copy.innerText(),statuses:await f.page.getByRole('status').allTextContents(),writes:await f.page.evaluate(()=>window.auditClipboard.length)};
  await f.page.getByRole('button',{name:'Close',exact:true}).click();
  for(const reduce of ['no-preference','reduce']) {
    await f.page.emulateMedia({reducedMotion:reduce});
    await trigger.click();await dialog.waitFor();
    report.interactions['sourceMotion-'+reduce]={readingColumn:await style(f.page.locator('main [class*="transition-[margin]"]')),dialog:await style(dialog),animations:await f.page.evaluate(()=>document.getAnimations().map(a=>({property:a.transitionProperty||null,playState:a.playState,duration:a.effect?.getTiming().duration}))) };
    await f.page.getByRole('button',{name:'Close',exact:true}).click();
  }
  await f.page.setViewportSize({width:390,height:844});await trigger.click();await dialog.waitFor();
  report.interactions.sourceMobile={dialog:await style(dialog),close:await style(f.page.getByRole('button',{name:'Close',exact:true})),backdropVisible:await f.page.getByRole('button',{name:'Close source panel',exact:true}).isVisible()};
  await f.page.screenshot({path:path.join(out,'source-mobile.png'),fullPage:true});
  await f.page.keyboard.press('Escape');
  report.interactions.sourceFocusRestored=await trigger.evaluate(el=>document.activeElement===el);
  await f.close();

  const broken=await fixture(browser);
  await ask(broken.page);await broken.page.getByRole('button',{name:'Source 1: Private salary.md, pages 1–1',exact:true}).click();
  await broken.page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw new DOMException('Synthetic clipboard permission denied','NotAllowedError');}}}));
  await broken.page.getByRole('button',{name:'Copy citation',exact:true}).click();await sleep(250);
  report.interactions.copyFailure={alerts:await broken.page.getByRole('alert').allTextContents(),errors:broken.state.errors,buttonText:await broken.page.getByRole('button',{name:'Copy citation',exact:true}).innerText()};
  await broken.context.close();

  const owner=await fixture(browser,{width:390,storageBytes:1048576});
  await login(owner.page);await owner.page.getByRole('link',{name:'Library',exact:true}).click();
  await owner.page.getByLabel('Collection',{exact:true}).selectOption('22222222-2222-4222-8222-222222222222');
  await owner.page.getByRole('region',{name:'Document storage'}).waitFor();
  await owner.page.screenshot({path:path.join(out,'private-library-mobile.png'),fullPage:true});
  report.interactions.ownerLibrary={upload:await style(owner.page.getByRole('button',{name:'Choose a file'})),delete:await style(owner.page.getByRole('button',{name:'Delete Private salary.md',exact:true})),horizontalTableScroll:await owner.page.locator('table').evaluate(el=>({table:el.scrollWidth,container:el.parentElement.clientWidth,scroll:el.parentElement.scrollWidth})),storage:await owner.page.getByRole('region',{name:'Document storage'}).innerText()};
  await owner.close();
  report.status='COMPLETED';
 }catch(e){report.status='INCOMPLETE';report.failure=e.stack;process.exitCode=1;}
 finally {await browser.close();fs.writeFileSync(path.join(out,'observations.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({status:report.status,pages:report.live.length,interactions:Object.keys(report.interactions),mutations:report.attemptedLiveMutations,failure:report.failure}));}
})();
