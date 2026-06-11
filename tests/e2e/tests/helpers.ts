import { Page, expect } from '@playwright/test';

/** YAML e2e dashboard view that renders both Pawsistant cards. */
export const DASHBOARD = '/pawsistant-e2e/card';

/**
 * Navigate to the e2e dashboard and wait for the main card custom element to
 * upgrade. The HA frontend boots asynchronously, so we wait on the element
 * being attached rather than a fixed delay.
 */
export async function openDashboard(page: Page): Promise<void> {
  await page.goto(DASHBOARD, { waitUntil: 'domcontentloaded' });
  await page.locator('pawsistant-card').first().waitFor({ state: 'attached', timeout: 45_000 });
  await expect(page.locator('pawsistant-card').first()).toBeVisible();
}

/**
 * Start collecting card-relevant errors. Attach BEFORE navigating. Captures
 * uncaught page exceptions and console.error lines that reference the card, so
 * the assertion stays targeted: the wider HA frontend emits unrelated errors
 * (e.g. stackless connection-bootstrap rejections) that aren't our concern.
 */
export function trackCardErrors(page: Page): string[] {
  const errors: string[] = [];
  const isCardRelated = (s: string) => /pawsistant/i.test(s);
  page.on('pageerror', (e) => {
    const text = `${e.message}\n${e.stack || ''}`;
    if (isCardRelated(text)) errors.push(`pageerror: ${text}`);
  });
  page.on('console', (msg) => {
    if (msg.type() === 'error' && isCardRelated(msg.text())) {
      errors.push(`console.error: ${msg.text()}`);
    }
  });
  return errors;
}

/** Force the HA frontend language for the next navigation (drives hass.language). */
export async function setLanguage(page: Page, lang: string): Promise<void> {
  await page.addInitScript((l) => {
    window.localStorage.setItem('selectedLanguage', JSON.stringify(l));
  }, lang);
}
