import { test, expect } from '@playwright/test';
import { openDashboard, trackCardErrors } from './helpers';

/** Format a Date as a local datetime-local value (YYYY-MM-DDTHH:mm). */
function localInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

test.describe('Pawsistant card — arbitrary backdating', () => {
  test('the log form offers a quick slider plus a date picker', async ({ page }) => {
    await openDashboard(page);
    const card = page.locator('pawsistant-card').first();

    await card.locator('.log-btn[data-type="poop"]').click();

    // Default: quick slider mode.
    await expect(card.locator('#bd-minutes-slider')).toBeVisible();
    await expect(card.locator('#bd-datetime')).toBeHidden();
    const toggle = card.locator('#bd-toggle');
    await expect(toggle).toBeVisible();

    // Switching reveals the native date+time picker (bounded at now).
    await toggle.click();
    await expect(card.locator('#bd-datetime')).toBeVisible();
    await expect(card.locator('#bd-minutes-slider')).toBeHidden();
    const max = await card.locator('#bd-datetime').getAttribute('max');
    expect(max).toBeTruthy();
  });

  test('an event can be backdated days into the past', async ({ page }) => {
    const errors = trackCardErrors(page);
    await openDashboard(page);
    const card = page.locator('pawsistant-card').first();

    await card.locator('.log-btn[data-type="poop"]').click();
    await card.locator('#bd-toggle').click();

    const target = new Date(Date.now() - 10 * 24 * 60 * 60000); // 10 days ago
    await card.locator('#bd-datetime').fill(localInput(target));
    await card.locator('#form-submit').click();

    // The form closes on success.
    await expect(card.locator('#bd-datetime')).toHaveCount(0);

    // Verify via the backend that an event landed ~10 days ago — well beyond
    // the old 8-hour ceiling.
    const ages = await page.evaluate(async () => {
      const hass = (document.querySelector('home-assistant') as unknown as { hass: any }).hass;
      const res = await hass.callService(
        'pawsistant',
        'list_events',
        { dog: 'Testdog', event_type: 'poop', days: 60 },
        undefined,
        false,
        true,
      );
      const events = (res.response?.events ?? []) as Array<{ timestamp: string }>;
      const now = Date.now();
      return events.map((e) => (now - new Date(e.timestamp).getTime()) / (24 * 60 * 60000));
    });

    expect(ages.some((d) => d > 9 && d < 11)).toBe(true);
    expect(errors, `card errors:\n${errors.join('\n')}`).toHaveLength(0);
  });
});
