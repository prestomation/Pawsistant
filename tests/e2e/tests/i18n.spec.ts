import { test, expect } from '@playwright/test';
import { openDashboard, setLanguage } from './helpers';

/**
 * Verifies the card render path is actually wired to the i18n module: switching
 * the HA frontend language (selectedLanguage) must change the rendered chrome.
 */
test.describe('Pawsistant card — i18n', () => {
  test('English baseline shows the English timeline title', async ({ page }) => {
    await openDashboard(page);
    await expect(
      page.locator('pawsistant-card').first().locator('.timeline-header'),
    ).toContainText('Timeline');
  });

  test('German locale localizes the card chrome', async ({ page }) => {
    await setLanguage(page, 'de');
    await openDashboard(page);
    const header = page.locator('pawsistant-card').first().locator('.timeline-header');
    await expect(header).toContainText('Zeitleiste'); // timeline.title (de)
    await expect(header).not.toContainText('Timeline');
  });

  test('Spanish locale localizes the card chrome', async ({ page }) => {
    await setLanguage(page, 'es');
    await openDashboard(page);
    await expect(
      page.locator('pawsistant-card').first().locator('.timeline-header'),
    ).toContainText('Cronología'); // timeline.title (es)
  });
});
