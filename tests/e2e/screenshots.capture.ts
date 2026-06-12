/**
 * One-off screenshot capture for PR documentation — not part of the e2e suite
 * (filename does not match *.spec.ts). Run with:
 *   npx playwright test screenshots.capture.ts --config=playwright.config.ts
 */
import { test, expect } from '@playwright/test';
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
