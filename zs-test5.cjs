const { chromium } = require('playwright');
(async () => {
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 1600 } });
const consoleErrors = [], pageErrors = [];
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', e => pageErrors.push(e.message));

await page.goto('http://127.0.0.1:8765/zubissou-sounds.html', { waitUntil: 'load', timeout: 15000 });
await page.waitForTimeout(3000);

const probe = await page.evaluate(() => ({
  mode: document.documentElement.getAttribute('data-mode'),
  knobs: document.querySelectorAll('.knob').length,
  tubes: document.querySelectorAll('.tube').length,
  palm: !!document.querySelector('.window-palm'),
  fronds: document.querySelectorAll('.frond').length,
}));
console.log('PROBE:', JSON.stringify(probe, null, 2));

// Day screenshots
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(900);
await page.locator('.window-frame').first().screenshot({ path: '/tmp/zs5-window-day.png' });
await page.locator('.console').first().screenshot({ path: '/tmp/zs5-console-day.png' });
await page.locator('.speakers-row').first().screenshot({ path: '/tmp/zs5-speakers-day.png' });

// Night
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'night'));
await page.waitForTimeout(1100);
await page.locator('.window-frame').first().screenshot({ path: '/tmp/zs5-window-night.png' });
await page.locator('.console').first().screenshot({ path: '/tmp/zs5-console-night.png' });
await page.locator('.speakers-row').first().screenshot({ path: '/tmp/zs5-speakers-night.png' });

// Full
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(700);
await page.screenshot({ path: '/tmp/zs5-day.png', fullPage: true });
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'night'));
await page.waitForTimeout(900);
await page.screenshot({ path: '/tmp/zs5-night.png', fullPage: true });

console.log('console errors:', consoleErrors.length); consoleErrors.slice(0,8).forEach(e => console.log('  •', e));
console.log('page errors:', pageErrors.length); pageErrors.slice(0,8).forEach(e => console.log('  •', e));
await browser.close();
})();
