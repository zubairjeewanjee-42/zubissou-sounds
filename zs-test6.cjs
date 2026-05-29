const { chromium } = require('playwright');
(async () => {
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const consoleErrors = [], pageErrors = [];
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', e => pageErrors.push(e.message));

await page.goto('http://127.0.0.1:8765/zubissou-sounds.html', { waitUntil: 'load', timeout: 15000 });
await page.waitForTimeout(2500);

const probe = await page.evaluate(() => ({
  scenes: document.querySelectorAll('.window-scene').length,
  activeScene: document.querySelector('.window-scene.active')?.dataset?.scene,
  fronds: document.querySelectorAll('.palm-frond').length,
  clouds: document.querySelectorAll('.cloud').length,
  buildings: document.querySelectorAll('.building').length,
  sceneDots: document.querySelectorAll('.scene-dot').length,
  brandWeight: getComputedStyle(document.querySelector('.brand-mark')).fontWeight,
}));
console.log('PROBE:', JSON.stringify(probe, null, 2));

// Day mode — capture all 3 scenes
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(700);

// Force poolside scene
await page.evaluate(() => setScene('poolside'));
await page.waitForTimeout(900);
await page.locator('.window-frame').first().screenshot({ path: '/tmp/zs6-pool-day.png' });

await page.evaluate(() => setScene('city'));
await page.waitForTimeout(900);
await page.locator('.window-frame').first().screenshot({ path: '/tmp/zs6-city-day.png' });

await page.evaluate(() => setScene('sunset'));
await page.waitForTimeout(900);
await page.locator('.window-frame').first().screenshot({ path: '/tmp/zs6-sunset-day.png' });

// Night versions
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'night'));
await page.waitForTimeout(800);
await page.evaluate(() => setScene('poolside'));
await page.waitForTimeout(900);
await page.locator('.window-frame').first().screenshot({ path: '/tmp/zs6-pool-night.png' });

await page.evaluate(() => setScene('city'));
await page.waitForTimeout(900);
await page.locator('.window-frame').first().screenshot({ path: '/tmp/zs6-city-night.png' });

// Header — font weight 900
await page.locator('.topbar').first().screenshot({ path: '/tmp/zs6-header.png' });

console.log('console errors:', consoleErrors.length); consoleErrors.slice(0,8).forEach(e => console.log('  •', e));
console.log('page errors:', pageErrors.length); pageErrors.slice(0,8).forEach(e => console.log('  •', e));
await browser.close();
})();
