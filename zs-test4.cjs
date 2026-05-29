const { chromium } = require('playwright');
(async () => {
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 1600 } });
const consoleErrors = [], pageErrors = [];
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', e => pageErrors.push(e.message));

await page.goto('http://127.0.0.1:8765/zubissou-sounds.html', { waitUntil: 'load', timeout: 15000 });
await page.waitForTimeout(3000);

// Probe header + play button
const probe = await page.evaluate(() => {
  const toggle = document.querySelector('.toggle');
  const tStyle = toggle && getComputedStyle(toggle);
  const playBtn = document.querySelector('.play-btn');
  const playStyle = playBtn && getComputedStyle(playBtn);
  return {
    mode: document.documentElement.getAttribute('data-mode'),
    toggleWidth: tStyle?.width,
    toggleHeight: tStyle?.height,
    playBg: playStyle?.backgroundColor,
    playIcon: !!document.querySelector('.play-btn-icon'),
    playLabels: document.querySelectorAll('.daynight-label').length,
    brand: document.querySelector('.brand-mark')?.textContent,
  };
});
console.log('PROBE:', JSON.stringify(probe, null, 2));

// Try clicking toggle
await page.click('#daynight-toggle');
await page.waitForTimeout(900);
const afterClick = await page.evaluate(() => document.documentElement.getAttribute('data-mode'));
console.log('after toggle click:', afterClick);

// Screenshots — header focus + console
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(800);
await page.locator('.topbar').first().screenshot({ path: '/tmp/zs4-header-day.png' });
await page.locator('.console').first().screenshot({ path: '/tmp/zs4-console-day.png' });
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'night'));
await page.waitForTimeout(1000);
await page.locator('.topbar').first().screenshot({ path: '/tmp/zs4-header-night.png' });
await page.locator('.console').first().screenshot({ path: '/tmp/zs4-console-night.png' });

// Full-page
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(700);
await page.screenshot({ path: '/tmp/zs4-day.png', fullPage: true });
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'night'));
await page.waitForTimeout(900);
await page.screenshot({ path: '/tmp/zs4-night.png', fullPage: true });

// Mobile
await page.setViewportSize({ width: 390, height: 844 });
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(500);
await page.locator('.topbar').first().screenshot({ path: '/tmp/zs4-mobile-header.png' });
await page.locator('.console').first().screenshot({ path: '/tmp/zs4-mobile-console.png' });

console.log('console errors:', consoleErrors.length); consoleErrors.slice(0,10).forEach(e => console.log('  •', e));
console.log('page errors:', pageErrors.length); pageErrors.slice(0,10).forEach(e => console.log('  •', e));
await browser.close();
})();
