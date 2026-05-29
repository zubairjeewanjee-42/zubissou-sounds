const { chromium } = require('playwright');
(async () => {
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errs = [];
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
page.on('pageerror', e => errs.push(e.message));

await page.goto('http://127.0.0.1:8765/zubissou-sounds.html', { waitUntil: 'load', timeout: 15000 });
await page.waitForTimeout(3000);

const result = await page.evaluate(() => ({
  poolsideHasImage: document.querySelector('.window-scene[data-scene="poolside"]').classList.contains('has-image'),
  poolsideBg: getComputedStyle(document.querySelector('.window-scene[data-scene="poolside"] .scene-image-overlay')).backgroundImage,
  twilightHasImage: document.querySelector('.window-scene[data-scene="twilight"]').classList.contains('has-image'),
  errs: window.__errors || [],
}));
console.log('OVERRIDE TEST:', JSON.stringify(result, null, 2));
console.log('errors:', errs.length); errs.slice(0,5).forEach(e => console.log('  •', e));

// Force poolside scene + screenshot to confirm image replaced CSS art
await page.evaluate(() => setScene('poolside'));
await page.waitForTimeout(900);
await page.locator('.window-frame').first().screenshot({ path: '/tmp/zs10-override.png' });

// Remove the override and confirm CSS art comes back
await page.evaluate(() => {
  const el = document.querySelector('.window-scene[data-scene="poolside"]');
  el.classList.remove('has-image');
});
await page.waitForTimeout(400);
await page.locator('.window-frame').first().screenshot({ path: '/tmp/zs10-cssart.png' });

await browser.close();
})();
