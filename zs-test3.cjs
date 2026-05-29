const { chromium } = require('playwright');
(async () => {
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 1600 } });
const consoleErrors = [], pageErrors = [], reqFails = [];
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', e => pageErrors.push(e.message));
page.on('requestfailed', r => reqFails.push(`${r.url()} → ${r.failure()?.errorText}`));

await page.goto('http://127.0.0.1:8765/zubissou-sounds.html', { waitUntil: 'load', timeout: 15000 });
await page.waitForTimeout(3500);

// Probe
const probe = await page.evaluate(() => ({
  mode: document.documentElement.getAttribute('data-mode'),
  knobs: document.querySelectorAll('.knob').length,
  knobLEDs: document.querySelectorAll('.knob-auto-led').length,
  knobLEDsLit: document.querySelectorAll('.knob-auto-led.lit').length,
  knobBounds: document.querySelectorAll('.knob-bounds').length,
  tubes: document.querySelectorAll('.tube').length,
  tubePairs: document.querySelectorAll('.tubes-pair').length,
  speakers: document.querySelectorAll('.speaker-cab').length,
  presetsBtn: !!document.getElementById('presets-btn'),
  vinylViewToggle: !!document.querySelector('.view-toggle'),
  windowMeta: document.getElementById('window-meta')?.textContent,
}));
console.log('PROBE:', JSON.stringify(probe, null, 2));

// Test presets modal
await page.click('#presets-btn');
await page.waitForTimeout(500);
const presetsOpen = await page.evaluate(() => document.getElementById('presets-modal').classList.contains('open'));
const presetCards = await page.locator('.preset-card').count();
console.log('presets modal open:', presetsOpen, '· cards:', presetCards);

// Click first preset
if (presetCards > 0) {
  await page.locator('.preset-card').first().click();
  await page.waitForTimeout(500);
  const litLEDs = await page.evaluate(() => document.querySelectorAll('.knob-auto-led.lit').length);
  console.log('after preset → lit AUTO LEDs:', litLEDs, '(expect 0 since preset touches all knobs)');
}

// Test AUTO LED click reset
await page.evaluate(() => {
  const knob = document.querySelector('.knob[data-knob="mood"]');
  const r = knob.getBoundingClientRect();
  knob.dispatchEvent(new PointerEvent('pointerdown', {clientX: r.left+30, clientY: r.top+30, pointerId: 1, bubbles: true}));
  knob.dispatchEvent(new PointerEvent('pointermove', {clientX: r.left+30, clientY: r.top-20, pointerId: 1, bubbles: true}));
  knob.dispatchEvent(new PointerEvent('pointerup', {clientX: r.left+30, clientY: r.top-20, pointerId: 1, bubbles: true}));
});
await page.waitForTimeout(200);
// Click AUTO LED to reset
await page.locator('.knob-auto-led[data-auto-for="mood"]').click();
await page.waitForTimeout(200);
const moodLed = await page.evaluate(() => document.querySelector('.knob-auto-led[data-auto-for="mood"]').classList.contains('lit'));
console.log('AUTO LED reset → lit:', moodLed);

// Toggle to spine view
const toggle = await page.locator('.view-toggle button[data-view="spines"]').count();
console.log('spine toggle available:', toggle > 0);
if (toggle > 0) {
  await page.locator('.view-toggle button[data-view="spines"]').click();
  await page.waitForTimeout(700);
  const spines = await page.locator('.spine').count();
  console.log('spines rendered:', spines);
}

// Screenshots
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(900);
await page.screenshot({ path: '/tmp/zs3-day.png', fullPage: true });

await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'night'));
await page.waitForTimeout(1100);
await page.screenshot({ path: '/tmp/zs3-night.png', fullPage: true });

// Knob detail - zoom on console
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(700);
await page.locator('.console').first().screenshot({ path: '/tmp/zs3-console-day.png' });
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'night'));
await page.waitForTimeout(800);
await page.locator('.console').first().screenshot({ path: '/tmp/zs3-console-night.png' });

// Presets modal screenshot
await page.click('#presets-btn');
await page.waitForTimeout(500);
await page.evaluate(() => document.documentElement.setAttribute('data-mode', 'day'));
await page.waitForTimeout(400);
await page.screenshot({ path: '/tmp/zs3-presets.png', fullPage: true });
await page.keyboard.press('Escape');

// Mobile
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(500);
await page.screenshot({ path: '/tmp/zs3-mobile.png', fullPage: true });

console.log('console errors:', consoleErrors.length); consoleErrors.slice(0,10).forEach(e => console.log('  •', e));
console.log('page errors:', pageErrors.length); pageErrors.slice(0,10).forEach(e => console.log('  •', e));
console.log('network failures:', reqFails.length); reqFails.slice(0,10).forEach(e => console.log('  •', e));
await browser.close();
})();
