/**
 * Screenshot capture for supplies — not part of the e2e suite (the filename does not
 * match *.spec.ts). It needs Home Keeper 0.27.0b5 or newer in the same Home
 * Assistant, which the standard e2e container does not have, so mount both
 * integrations into /config/custom_components and add a Home Keeper config entry.
 * Without Home Keeper the test skips. Run with:
 *   SHOT_DIR=../../docs/images npx playwright test --config=supplies.config.ts
 */
import { test, expect, Page, Locator } from '@playwright/test';
import { openDashboard } from './tests/helpers';

const OUT = process.env.SHOT_DIR || '/tmp/pawsistant-shots';
const PHONE = { width: 390, height: 844 };

/* eslint-disable @typescript-eslint/no-explicit-any */
async function call(page: Page, domain: string, service: string, data: Record<string, unknown>) {
  await page.evaluate(
    async ([d, s, body]) => {
      const hass = (document.querySelector('home-assistant') as any).hass;
      await hass.callService(d, s, body);
    },
    [domain, service, data] as const,
  );
}

async function hasHomeKeeper(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const hass = (document.querySelector('home-assistant') as any).hass;
    return Boolean(hass?.services?.home_keeper?.adjust_part_stock);
  });
}

async function saveDashboard(page: Page) {
  await page.evaluate(async () => {
    const hass = (document.querySelector('home-assistant') as any).hass;
    await hass.connection.sendMessagePromise({
      type: 'lovelace/config/save',
      url_path: 'pawsistant-e2e',
      config: {
        views: [
          {
            title: 'Card',
            path: 'card',
            cards: [
              {
                type: 'custom:pawsistant-button-card',
                dog: 'Testdog',
                show_event_log: true,
                buttons: [{ event_type: 'roll' }, { event_type: 'poop' }, { event_type: 'carprofen' }],
              },
              { type: 'custom:pawsistant-card', dog: 'Testdog' },
            ],
          },
        ],
      },
    });
  });
}

async function waitForBadge(card: Locator, text: string) {
  await expect(card.locator('.stock-badge').first()).toHaveText(text, { timeout: 20_000 });
}

test('capture supplies screenshots', async ({ page }) => {
  test.setTimeout(180_000);
  await openDashboard(page);
  test.skip(!(await hasHomeKeeper(page)), 'Home Keeper is not installed in this Home Assistant');

  // Two supplies: bag rolls on a Roll type, and tablets on a Carprofen type that shows
  // days since, as a medicine with a care schedule would.
  await call(page, 'pawsistant', 'add_event_type', {
    event_type: 'roll', name: 'Roll', icon: 'mdi:paper-roll', color: '#8D6E63',
    metric: 'days_since', supply: { name: 'Poop bag rolls', amount: 1 },
  });
  await call(page, 'pawsistant', 'update_supply', {
    event_type: 'roll', stock: 3, reorder_at: 1, unit: 'roll', pack_size: 8,
  });
  await call(page, 'pawsistant', 'add_event_type', {
    event_type: 'carprofen', name: 'Carprofen', icon: 'mdi:pill', color: '#EF5350',
    metric: 'days_since', supply: { name: 'Carprofen 75 mg', amount: 1 },
  });
  await call(page, 'pawsistant', 'update_supply', {
    event_type: 'carprofen', stock: 9, reorder_at: 7, unit: 'tablet', pack_size: 30,
  });
  const yesterday = new Date(Date.now() - 26 * 3600_000).toISOString();
  await call(page, 'pawsistant', 'log_event', { dog: 'Testdog', event_type: 'carprofen', timestamp: yesterday });
  await saveDashboard(page);
  await openDashboard(page);

  const bcard = page.locator('pawsistant-button-card').first();
  await bcard.scrollIntoViewIfNeeded();
  await waitForBadge(bcard, '3');
  // Carprofen was logged once, so its count is one below the 9 set above.
  await expect(bcard.locator('.log-btn').nth(2).locator('.stock-badge')).toHaveText('8', { timeout: 20_000 });
  await expect(bcard.locator('#pbc-supplies-btn')).toBeVisible();
  await page.waitForTimeout(500);
  await bcard.screenshot({ path: `${OUT}/supplies-1-badges.png` });

  // Tap Roll: the log form says what the log takes.
  await bcard.locator('.log-btn').first().click();
  await expect(bcard.locator('.stock-line')).toHaveText('Takes 1 roll · 3 → 2 left');
  await bcard.screenshot({ path: `${OUT}/supplies-2-log-form.png` });

  // Log it: the badge moves and a toast says what is left.
  await bcard.locator('#pbc-form-submit').click();
  await expect(bcard.locator('.pw-toast')).toContainText('Roll logged · 2 left');
  await waitForBadge(bcard, '2');
  await expect(bcard.locator('.pw-toast')).toContainText('Roll logged · 2 left');
  await bcard.screenshot({ path: `${OUT}/supplies-3-toast.png` });

  // A second roll reaches the reorder point: amber badge and the Buy task note.
  await page.waitForTimeout(6500);
  await bcard.locator('.log-btn').first().click();
  await bcard.locator('#pbc-form-submit').click();
  await expect(bcard.locator('.pw-toast')).toContainText('Low stock');
  await expect(bcard.locator('.stock-badge.low')).toHaveText('1', { timeout: 20_000 });
  await bcard.screenshot({ path: `${OUT}/supplies-4-low.png` });

  // The Supplies popup.
  await page.waitForTimeout(6500);
  await bcard.locator('#pbc-supplies-btn').click();
  const dialog = bcard.locator('.pw-sup-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('.pw-sup-row')).toHaveCount(2);
  await page.screenshot({ path: `${OUT}/supplies-5-popup.png` });
  await dialog.locator('.pw-sup-close').click();

  // The event type editor on the main card, with the supply group.
  const mcard = page.locator('pawsistant-card').first();
  await mcard.locator('#et-gear-btn').click();
  await mcard.locator('button.et-btn.edit[data-et-key="roll"]').click();
  const group = mcard.locator('fieldset.et-supply');
  await expect(group).toBeVisible();
  await expect(group.locator('#et-supply-name')).toHaveValue('Poop bag rolls');
  await group.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await group.screenshot({ path: `${OUT}/supplies-6-editor.png` });

  // Phone.
  await page.setViewportSize(PHONE);
  await openDashboard(page);
  const pcard = page.locator('pawsistant-button-card').first();
  await pcard.scrollIntoViewIfNeeded();
  await waitForBadge(pcard, '1');
  await pcard.locator('.log-btn').first().click();
  await expect(pcard.locator('.stock-line')).toBeVisible();
  await pcard.screenshot({ path: `${OUT}/supplies-7-mobile-log-form.png` });
  await pcard.locator('#pbc-form-cancel').click();
  await pcard.locator('#pbc-supplies-btn').click();
  await expect(pcard.locator('.pw-sup-dialog')).toBeVisible();
  await page.screenshot({ path: `${OUT}/supplies-8-mobile-popup.png` });
});
