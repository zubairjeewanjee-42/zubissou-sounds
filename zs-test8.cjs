const { chromium } = require('playwright');
(async () => {
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const consoleErrors = [], pageErrors = [];
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', e => pageErrors.push(e.message));

await page.goto('http://127.0.0.1:8765/zubissou-sounds.html', { waitUntil: 'load', timeout: 15000 });
await page.waitForTimeout(2800);

const probe = await page.evaluate(() => ({
  bird: !!document.querySelector('.scene-store .bird'),
  butterfly: !!document.querySelector('.scene-meadow .butterfly'),
  cityLights: !!document.querySelector('.scene-twilight .city-lights'),
  snowflakes: document.querySelectorAll('.snow-flake').length,
  sunRays: document.querySelectorAll('.sun-ray').length,
  rainDrops: document.querySelectorAll('.rain-drop').length,
}));
console.log('PROBE:', JSON.stringify(probe, null, 2));

// Force cloudy weather to trigger SJ hack
await page.evaluate(() => {
  // Clear existing precipitation/snow particles
  document.querySelectorAll('.snow-flake, .rain-drop, .sun-ray').forEach(e => e.remove());
  // Manually trigger snow render (simulating cloudy code)
  if (typeof renderSnow === 'function') renderSnow();
});
await page.waitForTimeout(800);
const cloudySnow = await page.evaluate(() => document.querySelectorAll('.snow-flake').length);
console.log('snowflakes after forced cloudy:', cloudySnow);

// Manually trigger sun rays
await page.evaluate(() => {
  document.querySelectorAll('.sun-ray').forEach(e => e.remove());
  if (typeof renderSunRays === 'function') renderSunRays();
});
await page.waitForTimeout(400);
const rays = await page.evaluate(() => document.querySelectorAll('.sun-ray').length);
console.log('sun rays after forced clear:', rays);

// Force day mode and capture each scene with animations
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(700);

for (const sc of ['twilight', 'store', 'meadow']) {
  await page.evaluate(s => setScene(s), sc);
  await page.waitForTimeout(2200); // let animations cycle
  await page.locator('.window-frame').first().screenshot({ path: `/tmp/zs8-${sc}-anim.png` });
  console.log(`captured ${sc} with animations`);
}

// SJ cloudy-snow shot on poolside
await page.evaluate(() => setScene('poolside'));
await page.waitForTimeout(700);
await page.evaluate(() => {
  document.querySelectorAll('.snow-flake').forEach(e => e.remove());
  if (typeof renderSnow === 'function') renderSnow();
});
await page.waitForTimeout(1500);
await page.locator('.window-frame').first().screenshot({ path: '/tmp/zs8-snow-cloudy.png' });

// Sun rays shot on poolside
await page.evaluate(() => {
  document.querySelectorAll('.snow-flake').forEach(e => e.remove());
  if (typeof renderSunRays === 'function') renderSunRays();
});
await page.waitForTimeout(1200);
await page.locator('.window-frame').first().screenshot({ path: '/tmp/zs8-sunrays.png' });

console.log('console errors:', consoleErrors.length); consoleErrors.slice(0,8).forEach(e => console.log('  •', e));
console.log('page errors:', pageErrors.length); pageErrors.slice(0,8).forEach(e => console.log('  •', e));
await browser.close();
})();
