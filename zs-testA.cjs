const { chromium } = require('playwright');
(async () => {
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errs = [];
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
page.on('pageerror', e => errs.push(e.message));

await page.goto('http://127.0.0.1:8765/zubissou-sounds.html', { waitUntil: 'load', timeout: 15000 });
await page.waitForTimeout(2800);

const probe = await page.evaluate(() => ({
  scenes: Array.from(document.querySelectorAll('.window-scene')).map(s => s.dataset.scene),
  dots: Array.from(document.querySelectorAll('.scene-dot')).map(d => d.dataset.scene),
  pines: document.querySelectorAll('.pine').length,
  mountains: document.querySelectorAll('.scene-garden .mountain').length,
  island: !!document.querySelector('.scene-beach .island'),
  surfLine: !!document.querySelector('.scene-beach .surf-line'),
  sandSpec: !!document.querySelector('.scene-beach .sand-spec'),
}));
console.log('PROBE:', JSON.stringify(probe, null, 2));

// Day mode — capture all 5 new scenes
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(800);
for (const sc of ['beach', 'forest', 'rain', 'garden', 'city']) {
  await page.evaluate(s => setScene(s), sc);
  await page.waitForTimeout(1500); // let animations settle + weather effects apply
  await page.locator('.window-frame').first().screenshot({ path: `/tmp/zsA-${sc}.png` });
  console.log(`captured ${sc}`);
}

// Confirm rain particles appeared on RAIN scene
await page.evaluate(() => setScene('rain'));
await page.waitForTimeout(900);
const rainDrops = await page.evaluate(() => document.querySelectorAll('.rain-drop').length);
console.log('rain drops on RAIN scene:', rainDrops);

// Confirm rain clears when switching away
await page.evaluate(() => setScene('beach'));
await page.waitForTimeout(900);
const rainAfter = await page.evaluate(() => document.querySelectorAll('.rain-drop').length);
console.log('rain drops after switching to beach:', rainAfter);

console.log('errors:', errs.length); errs.slice(0,5).forEach(e => console.log('  •', e));
await browser.close();
})();
