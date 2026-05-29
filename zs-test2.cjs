const { chromium } = require('playwright');
(async () => {
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 1400 } });
const consoleErrors = [], pageErrors = [], reqFails = [];
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', e => pageErrors.push(e.message));
page.on('requestfailed', r => reqFails.push(`${r.url()} → ${r.failure()?.errorText}`));

await page.goto('http://127.0.0.1:8765/zubissou-sounds.html', { waitUntil: 'load', timeout: 15000 });
await page.waitForTimeout(3500);

const probe = await page.evaluate(() => ({
  mode: document.documentElement.getAttribute('data-mode'),
  canonCount: document.getElementById('canon-count')?.textContent,
  vinylCount: document.getElementById('vinyl-count')?.textContent,
  xrayStats: document.getElementById('xray-stats')?.textContent,
  curatorCount: document.querySelectorAll('.curator-card').length,
  vinylCards: document.querySelectorAll('.vinyl-card').length,
  manageBtn: !!document.getElementById('manage-canon-btn'),
  manualFab: !!document.getElementById('manual-fab'),
  manualModal: !!document.getElementById('manual-modal'),
  canonModal: !!document.getElementById('canon-modal'),
}));
console.log('PROBE:', JSON.stringify(probe, null, 2));

// Click first curator card
const cur = await page.locator('.curator-card').count();
console.log('curator cards:', cur);
if (cur > 0) {
  await page.locator('.curator-card').first().click();
  await page.waitForTimeout(800);
  const codexOpen = await page.evaluate(() => document.getElementById('codex').classList.contains('open'));
  const epCount = await page.locator('.episode-row').count();
  console.log('curator drawer opened:', codexOpen, '· episodes shown:', epCount);
  if (epCount > 0) {
    await page.locator('.episode-row').first().click();
    await page.waitForTimeout(500);
    const tracks = await page.locator('.tracklist-row').count();
    console.log('tracklist rows after episode click:', tracks);
  }
  await page.click('#codex-close');
  await page.waitForTimeout(300);
}

// Test manual modal
await page.click('#manual-fab');
await page.waitForTimeout(400);
const manualOpen = await page.evaluate(() => document.getElementById('manual-modal').classList.contains('open'));
console.log('manual modal open:', manualOpen);
await page.keyboard.press('Escape');
await page.waitForTimeout(300);

// Test canon manager
await page.click('#manage-canon-btn');
await page.waitForTimeout(500);
const canonOpen = await page.evaluate(() => document.getElementById('canon-modal').classList.contains('open'));
const canonRows = await page.locator('.canon-row').count();
console.log('canon manager open:', canonOpen, '· rows:', canonRows);

// Click a "TOP" move button to test reorder
if (canonRows > 5) {
  const moveBtns = await page.locator('.canon-row').nth(3).locator('[data-act="top"]').count();
  if (moveBtns > 0) {
    await page.locator('.canon-row').nth(3).locator('[data-act="top"]').click();
    await page.waitForTimeout(300);
    console.log('reorder click — ok');
  }
}
await page.keyboard.press('Escape');

// Screenshots
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(700);
await page.screenshot({ path: '/tmp/zs2-day.png', fullPage: true });
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'night'));
await page.waitForTimeout(1000);
await page.screenshot({ path: '/tmp/zs2-night.png', fullPage: true });

// Manual screenshot
await page.click('#manual-fab');
await page.waitForTimeout(500);
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(400);
await page.screenshot({ path: '/tmp/zs2-manual.png', fullPage: true });
await page.keyboard.press('Escape');

// Canon mgr screenshot
await page.click('#manage-canon-btn');
await page.waitForTimeout(500);
await page.screenshot({ path: '/tmp/zs2-canon.png', fullPage: true });

await page.setViewportSize({ width: 390, height: 844 });
await page.keyboard.press('Escape');
await page.waitForTimeout(400);
await page.screenshot({ path: '/tmp/zs2-mobile.png', fullPage: true });

console.log('console errors:', consoleErrors.length); consoleErrors.slice(0,10).forEach(e => console.log('  •', e));
console.log('page errors:', pageErrors.length); pageErrors.slice(0,10).forEach(e => console.log('  •', e));
console.log('network failures:', reqFails.length); reqFails.slice(0,10).forEach(e => console.log('  •', e));
await browser.close();
})();
