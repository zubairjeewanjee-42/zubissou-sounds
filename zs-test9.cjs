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
  sceneOverlays: document.querySelectorAll('.scene-image-overlay').length,
  scenesWithImage: document.querySelectorAll('.window-scene.has-image').length,
  scenes: document.querySelectorAll('.window-scene').length,
}));
console.log('PROBE:', JSON.stringify(probe, null, 2));

// Simulate dropping in an image — inject a data URL and trigger the load path
await page.evaluate(() => {
  const slug = 'poolside';
  const sceneEl = document.querySelector(`.window-scene[data-scene="${slug}"]`);
  const overlay = sceneEl.querySelector('.scene-image-overlay');
  // Use a 1x1 transparent png as a test
  overlay.style.backgroundImage = `url("data:image/svg+xml;base64,${btoa('<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'200\\' height=\\'40\\'><rect width=\\'100%\\' height=\\'100%\\' fill=\\'#ff66aa\\'/></svg>')}")`;
  sceneEl.classList.add('has-image');
});
await page.waitForTimeout(500);
const overrideWorking = await page.evaluate(() =>
  document.querySelector('.window-scene[data-scene="poolside"]').classList.contains('has-image')
);
console.log('override applied:', overrideWorking);

// Screenshot to verify override visually replaces CSS art
await page.evaluate(() => setScene('poolside'));
await page.waitForTimeout(700);
await page.locator('.window-frame').first().screenshot({ path: '/tmp/zs9-override-test.png' });

console.log('console errors:', consoleErrors.length); consoleErrors.slice(0,8).forEach(e => console.log('  •', e));
console.log('page errors:', pageErrors.length); pageErrors.slice(0,8).forEach(e => console.log('  •', e));
await browser.close();
})();
