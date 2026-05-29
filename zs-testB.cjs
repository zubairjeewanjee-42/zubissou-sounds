const { chromium } = require('playwright');
(async () => {
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 600 } });
await page.goto('http://127.0.0.1:8765/zubissou-sounds.html', { waitUntil: 'load', timeout: 12000 });
await page.waitForTimeout(2500);
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(700);
await page.locator('.window-frame').first().screenshot({ path: '/tmp/zsB-window-day.png' });
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'night'));
await page.waitForTimeout(800);
await page.locator('.window-frame').first().screenshot({ path: '/tmp/zsB-window-night.png' });
await browser.close();
console.log('done');
})();
