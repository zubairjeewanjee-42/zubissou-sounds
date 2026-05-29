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
  sceneDots: document.querySelectorAll('.scene-dot').length,
  storefront: !!document.querySelector('.storefront'),
  mountain: !!document.querySelector('.mountain'),
  flowers: !!document.querySelector('.flowers'),
  twilight: !!document.querySelector('.scene-twilight'),
}));
console.log('PROBE:', JSON.stringify(probe, null, 2));

// Day mode — capture all 5
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(700);

for (const sc of ['poolside', 'twilight', 'store', 'meadow', 'city']) {
  await page.evaluate(s => setScene(s), sc);
  await page.waitForTimeout(900);
  await page.locator('.window-frame').first().screenshot({ path: `/tmp/zs7-${sc}-day.png` });
  console.log(`  saved ${sc}-day`);
}

// Night mode — same
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'night'));
await page.waitForTimeout(800);
for (const sc of ['poolside', 'twilight', 'store', 'meadow', 'city']) {
  await page.evaluate(s => setScene(s), sc);
  await page.waitForTimeout(900);
  await page.locator('.window-frame').first().screenshot({ path: `/tmp/zs7-${sc}-night.png` });
}

console.log('console errors:', consoleErrors.length); consoleErrors.slice(0,8).forEach(e => console.log('  •', e));
console.log('page errors:', pageErrors.length); pageErrors.slice(0,8).forEach(e => console.log('  •', e));
await browser.close();
})();
