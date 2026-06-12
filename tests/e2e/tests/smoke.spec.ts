import { test, expect } from '@playwright/test';
import { openDashboard, trackCardErrors } from './helpers';

test.describe('Pawsistant card — smoke', () => {
  test('main card renders for the seeded pet, with no card errors', async ({ page }) => {
    const errors = trackCardErrors(page);
    await openDashboard(page);

    const card = page.locator('pawsistant-card').first();
    await expect(card.locator('.card-title')).toContainText('Testdog');
    await expect(card.locator('.timeline-header')).toContainText('Timeline');
    await expect(card.locator('.log-btn').first()).toBeVisible();

    expect(errors, `card errors:\n${errors.join('\n')}`).toHaveLength(0);
  });

  test('button card renders its configured quick-log buttons', async ({ page }) => {
    await openDashboard(page);
    const bcard = page.locator('pawsistant-button-card').first();
    await expect(bcard).toBeVisible();
    // Dashboard configures three buttons: poop, pee, weight.
    await expect(bcard.locator('.log-btn')).toHaveCount(3);
  });

  test('both cards register in the Lovelace card picker', async ({ page }) => {
    await openDashboard(page);
    const types = await page.evaluate(
      () => (window as unknown as { customCards?: Array<{ type: string }> }).customCards?.map((c) => c.type) ?? [],
    );
    expect(types).toContain('pawsistant-card');
    expect(types).toContain('pawsistant-button-card');
  });

  test('tapping a quick-log button opens the inline log form', async ({ page }) => {
    await openDashboard(page);
    const card = page.locator('pawsistant-card').first();
    await card.locator('.log-btn[data-type="poop"]').click();
    await expect(card.locator('#form-submit')).toBeVisible();
    await expect(card.locator('#form-cancel')).toBeVisible();
  });

  test('timeline renders an events list or a localized empty state (never a raw key)', async ({ page }) => {
    await openDashboard(page);
    const body = page.locator('pawsistant-card').first().locator('#timeline-body');
    await expect(body).toBeVisible();
    // A wiring bug (missing key) would surface the literal key like "timeline.empty_no_events".
    await expect(body).not.toContainText('timeline.');
  });

  test('opening the event-types panel shows the localized title', async ({ page }) => {
    await openDashboard(page);
    const card = page.locator('pawsistant-card').first();
    await card.locator('#et-gear-btn').click();
    await expect(card.locator('.event-types-panel-title')).toContainText('Event Types');
    await expect(card.locator('#et-add-btn')).toContainText('Add Event Type');
  });

  test('button card opens and closes the event log popup', async ({ page }) => {
    const errors = trackCardErrors(page);
    await openDashboard(page);
    const bcard = page.locator('pawsistant-button-card').first();

    await bcard.locator('#pbc-log-btn').click();
    const dialog = bcard.locator('.pbc-dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.locator('.pbc-dialog-title')).toContainText('Testdog');
    // Timeline body shows rows or a localized empty state — never a raw key
    await expect(dialog.locator('.timeline-body')).not.toContainText('timeline.');

    await dialog.locator('#pbc-dialog-close').click();
    await expect(bcard.locator('.pbc-overlay')).toHaveCount(0);

    expect(errors, `card errors:\n${errors.join('\n')}`).toHaveLength(0);
  });
});
