import { test, expect, Page } from '@playwright/test';
import { openDashboard, trackCardErrors } from './helpers';

/**
 * Every delete asks first, in one dialog. Cancel is the default, Escape and a tap
 * outside cancel, and the button names the action. Run at desktop and phone width.
 */
const VIEWPORTS = [
  { name: 'desktop', size: { width: 1280, height: 900 } },
  { name: 'phone', size: { width: 390, height: 844 } },
];

const dialog = (page: Page) => page.locator('.pw-confirm-scrim [role="alertdialog"]');

async function hassCall(page: Page, service: string, data: Record<string, unknown>): Promise<unknown> {
  return page.evaluate(
    async ([svc, payload]) => {
      const hass = (document.querySelector('home-assistant') as unknown as { hass: any }).hass;
      // Only list_events answers with a response.
      return hass.callService('pawsistant', svc as string, payload, undefined, false, svc === 'list_events');
    },
    [service, data] as [string, Record<string, unknown>],
  );
}

async function eventCount(page: Page, note: string): Promise<number> {
  return page.evaluate(async (n) => {
    const hass = (document.querySelector('home-assistant') as unknown as { hass: any }).hass;
    const res = await hass.callService('pawsistant', 'list_events', { dog: 'Testdog', days: 2 }, undefined, false, true);
    return ((res.response?.events ?? []) as Array<{ note?: string }>).filter((e) => e.note === n).length;
  }, note);
}

for (const vp of VIEWPORTS) {
  test.describe(`destructive confirm — ${vp.name}`, () => {
    test.use({ viewport: vp.size });

    test('a log entry is deleted only after the dialog is confirmed', async ({ page }) => {
      const errors = trackCardErrors(page);
      const note = `confirm-${vp.name}-${Date.now()}`;
      await openDashboard(page);
      await hassCall(page, 'log_event', { dog: 'Testdog', event_type: 'pee', note });
      await openDashboard(page);
      const card = page.locator('pawsistant-card').first();
      const row = card.locator(`.event-row[data-note="${note}"]`);
      await expect(row).toBeVisible();

      await row.locator('.delete-btn').click();
      await expect(dialog(page)).toBeVisible();
      await expect(dialog(page).locator('.pw-confirm-title')).toContainText('entry');
      await expect(dialog(page).locator('.pw-confirm-body')).toContainText(note);
      await expect(dialog(page).getByRole('button', { name: 'Cancel' })).toBeFocused();
      await expect(dialog(page).getByRole('button', { name: 'Delete entry' })).toBeVisible();

      // Escape cancels and keeps the entry.
      await page.keyboard.press('Escape');
      await expect(dialog(page)).toHaveCount(0);
      expect(await eventCount(page, note)).toBe(1);

      // A tap outside cancels.
      await row.locator('.delete-btn').click();
      await page.mouse.click(2, 2);
      await expect(dialog(page)).toHaveCount(0);
      expect(await eventCount(page, note)).toBe(1);

      // The confirm button deletes.
      await row.locator('.delete-btn').click();
      await dialog(page).getByRole('button', { name: 'Delete entry' }).click();
      await expect(row).toHaveCount(0);
      expect(await eventCount(page, note)).toBe(0);
      expect(errors, `card errors:\n${errors.join('\n')}`).toHaveLength(0);
    });

    test('an event type is deleted only after the dialog is confirmed', async ({ page }) => {
      const key = `confirm_${vp.name}`;
      await openDashboard(page);
      await hassCall(page, 'add_event_type', { event_type: key, name: `Confirm ${vp.name}`, icon: 'mdi:paw', color: '#4CAF50' });
      await openDashboard(page);
      const card = page.locator('pawsistant-card').first();
      const del = card.locator(`.et-btn.delete[data-et-key="${key}"]`);
      // The card may redraw while Home Assistant settles, which closes the panel: retry.
      await expect(async () => {
        if ((await card.locator('.event-type-row').count()) === 0) await card.locator('#et-gear-btn').click();
        await expect(del).toBeVisible({ timeout: 2000 });
      }).toPass({ timeout: 30_000 });

      await del.click();
      await expect(dialog(page)).toBeVisible();
      await expect(dialog(page).locator('.pw-confirm-title')).toContainText(`Confirm ${vp.name}`);
      await expect(dialog(page).locator('.pw-confirm-body')).toContainText('Entries already logged stay in the log.');
      await dialog(page).getByRole('button', { name: 'Cancel' }).click();
      await expect(dialog(page)).toHaveCount(0);
      await expect(del).toBeVisible();

      await del.click();
      await dialog(page).getByRole('button', { name: 'Delete event type' }).click();
      await expect(del).toHaveCount(0);
    });
  });
}
