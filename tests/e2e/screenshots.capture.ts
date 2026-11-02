/**
 * One-off screenshot capture for PR documentation — not part of the e2e suite
 * (filename does not match *.spec.ts). Run with:
 *   npx playwright test screenshots.capture.ts --config=playwright.config.ts
 */
import { test, expect, Page, Browser, BrowserContext } from '@playwright/test';
import { openDashboard } from './tests/helpers';

const OUT = process.env.SHOT_DIR || '/tmp/pawsistant-shots';

test('capture button card event log popup screenshots', async ({ page }) => {
  await openDashboard(page);

  // Seed a varied timeline via the hass websocket connection
  await page.evaluate(async () => {
    const hass = (document.querySelector('home-assistant') as unknown as { hass: any }).hass;
    const now = Date.now();
    const evs = [
      { event_type: 'walk', mins: 35, note: 'around the block' },
      { event_type: 'pee', mins: 90 },
      { event_type: 'poop', mins: 95, note: 'good boy!' },
      { event_type: 'food', mins: 60 * 9 },
      { event_type: 'weight', mins: 60 * 10, value: 42.5 },
      { event_type: 'pee', mins: 60 * 26 },
      { event_type: 'medicine', mins: 60 * 27, note: 'heartworm pill' },
      { event_type: 'walk', mins: 60 * 30 },
    ];
    for (const e of evs) {
      await hass.callService('pawsistant', 'log_event', {
        dog: 'Testdog',
        event_type: e.event_type,
        timestamp: new Date(now - e.mins * 60000).toISOString(),
        ...(e.note ? { note: e.note } : {}),
        ...(e.value ? { value: e.value } : {}),
      });
    }
  });
  // Reload so card metrics reflect the seeded events
  await openDashboard(page);

  const bcard = page.locator('pawsistant-button-card').first();
  await bcard.scrollIntoViewIfNeeded();
  await expect(bcard.locator('#pbc-log-btn')).toBeVisible();
  await bcard.screenshot({ path: `${OUT}/1-button-card-with-log-button.png` });

  // Open the popup and wait for rows
  await bcard.locator('#pbc-log-btn').click();
  const dialog = bcard.locator('.pbc-dialog');
  await expect(dialog.locator('.event-row').first()).toBeVisible();
  await page.screenshot({ path: `${OUT}/2-event-log-popup.png` });

  // Edit form open in the popup
  const firstRow = dialog.locator('.event-row').first();
  await firstRow.hover();
  await firstRow.locator('.edit-btn').click();
  await expect(dialog.locator('#pbc-edit-form-submit')).toBeVisible();
  await page.screenshot({ path: `${OUT}/3-popup-edit-form.png` });

  // Two-tap delete confirm state
  await dialog.locator('#pbc-edit-form-cancel').click();
  await firstRow.hover();
  await firstRow.locator('.delete-btn').click();
  await expect(firstRow.locator('.delete-btn')).toHaveClass(/confirm-pending/);
  await page.screenshot({ path: `${OUT}/4-popup-delete-confirm.png` });
});

/* ── Event types panel: delete button for admin users only ─────────────── */

// Viewports for the event types screenshots. The height is large so that the
// full card fits on the screen. If the card scrolls, the HA toolbar covers the
// panel header in the screenshot.
const DESKTOP = { width: 1280, height: 1200 };
const PHONE = { width: 390, height: 1200 };
const VIEWER = { name: 'Viewer', username: 'viewer', password: 'viewerpass1' };

/**
 * Create the non-admin VIEWER user through the HA auth websocket API, if it is
 * not there. The page must be logged in as an admin. The step is idempotent.
 */
async function ensureViewerUser(page: Page): Promise<void> {
  await page.evaluate(async (v) => {
    const hass = (document.querySelector('home-assistant') as unknown as { hass: any }).hass;
    const users: Array<{ username?: string }> = await hass.callWS({ type: 'config/auth/list' });
    if (users.some((u) => u.username === v.username)) return;
    const created = await hass.callWS({
      type: 'config/auth/create',
      name: v.name,
      group_ids: ['system-users'],
    });
    await hass.callWS({
      type: 'config/auth_provider/homeassistant/create',
      user_id: created.user.id,
      username: v.username,
      password: v.password,
    });
  }, VIEWER);
}

/** Log in as VIEWER in a new browser context with no stored session. */
async function viewerPage(browser: Browser): Promise<{ ctx: BrowserContext; page: Page }> {
  const ctx = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  const page = await ctx.newPage();
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const username = page.locator('input[autocomplete="username"]');
  await username.waitFor({ state: 'visible', timeout: 30_000 });
  await username.fill(VIEWER.username);
  await page.locator('input[autocomplete="current-password"]').fill(VIEWER.password);
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => !!window.localStorage.getItem('hassTokens'), null, { timeout: 30_000 });
  return { ctx, page };
}

/** Open the event types panel of the main card and capture it at desktop and phone width. */
async function captureEventTypesPanel(page: Page, name: string, expectDelete: boolean): Promise<void> {
  await page.setViewportSize(DESKTOP);
  await openDashboard(page);
  const card = page.locator('pawsistant-card').first();
  await card.locator('#et-gear-btn').click();
  await expect(card.locator('.event-type-row').first()).toBeVisible();
  await expect(card.locator('.et-btn.edit').first()).toBeVisible();
  await expect(card.locator('.et-btn.delete')).toHaveCount(expectDelete ? await card.locator('.event-type-row').count() : 0);
  await card.screenshot({ path: `${OUT}/${name}.png` });

  await page.setViewportSize(PHONE);
  await openDashboard(page);
  await card.locator('#et-gear-btn').click();
  await expect(card.locator('.event-type-row').first()).toBeVisible();
  await expect(card.locator('.et-btn.delete')).toHaveCount(expectDelete ? await card.locator('.event-type-row').count() : 0);
  await card.screenshot({ path: `${OUT}/${name}-mobile.png` });
}

test('capture event types panel for admin and non-admin users', async ({ page, browser }) => {
  // The admin session comes from global-setup.
  await openDashboard(page);
  await ensureViewerUser(page);
  await captureEventTypesPanel(page, 'event-types-admin', true);

  const { ctx, page: vpage } = await viewerPage(browser);
  try {
    await captureEventTypesPanel(vpage, 'event-types-non-admin', false);
  } finally {
    await ctx.close();
  }
});
