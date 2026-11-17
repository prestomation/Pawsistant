import { test, expect, Page, Locator } from '@playwright/test';
import { openDashboard, trackCardErrors } from './helpers';

/**
 * What the next pawsistant.log_event call does:
 *  - ok:     goes to Home Assistant at once
 *  - slow:   goes to Home Assistant after `delayMs`
 *  - fail:   Home Assistant never sees it, the page gets an error answer
 *  - lost:   Home Assistant stores it, the answer is lost on the way back
 */
type Mode = 'ok' | 'slow' | 'fail' | 'lost';

interface Net {
  mode: Mode;
  delayMs: number;
  /** log_event calls the page sent, in order. */
  sent: Array<{ event_type: string; timestamp?: string }>;
}

/** Put a proxy between the page and the Home Assistant websocket. Call before the page loads. */
async function proxyWebSocket(page: Page): Promise<Net> {
  const net: Net = { mode: 'ok', delayMs: 4000, sent: [] };
  await page.routeWebSocket(/\/api\/websocket$/, (ws) => {
    const server = ws.connectToServer();
    const lostIds = new Set<number>();
    server.onMessage((message) => {
      // Home Assistant can send several messages in one array.
      let parsed: any;
      try {
        parsed = JSON.parse(String(message));
      } catch {
        ws.send(message);
        return;
      }
      const list: any[] = Array.isArray(parsed) ? parsed : [parsed];
      const keep = list.filter((m) => !(m && lostIds.has(m.id)));
      if (keep.length === list.length) ws.send(message);
      else if (keep.length) ws.send(JSON.stringify(Array.isArray(parsed) ? keep : keep[0]));
    });
    ws.onMessage((message) => {
      let msg: { id?: number; type?: string; domain?: string; service?: string; service_data?: any } | null = null;
      try {
        msg = JSON.parse(String(message));
      } catch {
        /* not JSON: pass it on */
      }
      const isLog = msg?.type === 'call_service' && msg.domain === 'pawsistant' && msg.service === 'log_event';
      if (!isLog) {
        server.send(message);
        return;
      }
      net.sent.push(msg!.service_data);
      if (net.mode === 'fail') {
        ws.send(JSON.stringify({ id: msg!.id, type: 'result', success: false, error: { code: 'unknown_error', message: 'Test failure' } }));
      } else if (net.mode === 'slow') {
        setTimeout(() => server.send(message), net.delayMs);
      } else {
        if (net.mode === 'lost') lostIds.add(msg!.id!);
        server.send(message);
      }
    });
  });
  return net;
}

/** Hold a button long enough for an instant log. */
async function holdToLog(page: Page, btn: Locator): Promise<void> {
  const box = (await btn.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(700);
  await page.mouse.up();
}

const pendingRow = (card: Locator) => card.locator('#timeline-body .event-row[data-pending-id]');

test.describe('Pawsistant card — pending log entries', () => {
  test('a slow save shows a faded row, then a solid row', async ({ page }) => {
    const errors = trackCardErrors(page);
    const net = await proxyWebSocket(page);
    net.mode = 'slow';
    net.delayMs = 4000;
    await openDashboard(page);
    const card = page.locator('pawsistant-card').first();
    await expect(card.locator('#timeline-body .event-row').first()).toBeVisible();
    const before = await card.locator('#timeline-body .event-row').count();

    await holdToLog(page, card.locator('.log-btn[data-type="pee"]'));
    const row = pendingRow(card);
    await expect(row).toHaveCount(1);
    await expect(row).toContainText('Saving…');
    await expect(row.locator('.pending-spin')).toBeVisible();
    await expect(row.locator('.delete-btn')).toHaveCount(0);

    // The save arrives: the faded row goes and the list has one more row.
    await expect(row).toHaveCount(0, { timeout: 12_000 });
    await expect(card.locator('#timeline-body .event-row')).toHaveCount(before + 1);
    await expect(card.locator('#timeline-body .event-row').first().locator('.delete-btn')).toHaveCount(1);
    expect(net.sent).toHaveLength(1);
    expect(net.sent[0].timestamp).toBeTruthy(); // the tap sends the phone time
    expect(errors, `card errors:\n${errors.join('\n')}`).toHaveLength(0);
  });

  test('a failed save shows "Not saved yet"; Retry saves it once', async ({ page }) => {
    const net = await proxyWebSocket(page);
    net.mode = 'fail';
    await openDashboard(page);
    const card = page.locator('pawsistant-card').first();
    await expect(card.locator('#timeline-body .event-row').first()).toBeVisible();
    const before = await card.locator('#timeline-body .event-row').count();

    await holdToLog(page, card.locator('.log-btn[data-type="pee"]'));
    const row = pendingRow(card);
    await expect(row).toContainText('Not saved yet');
    await expect(row.locator('.retry-btn')).toBeVisible();
    await expect(row.locator('.discard-btn')).toBeVisible();

    net.mode = 'ok';
    await row.locator('.retry-btn').click();
    await expect(row).toHaveCount(0);
    await expect(card.locator('#timeline-body .event-row')).toHaveCount(before + 1);
    expect(net.sent).toHaveLength(2);
    expect(net.sent[1].timestamp).toBe(net.sent[0].timestamp);
  });

  test('a lost answer shows "Not saved yet" after 15 s; Retry makes no copy', async ({ page }) => {
    test.setTimeout(90_000);
    const net = await proxyWebSocket(page);
    await openDashboard(page);
    const card = page.locator('pawsistant-card').first();
    await expect(card.locator('#timeline-body .event-row').first()).toBeVisible();
    const before = await card.locator('#timeline-body .event-row').count();

    // Home Assistant stores the event. The answer never comes back to the page.
    net.mode = 'lost';
    await holdToLog(page, card.locator('.log-btn[data-type="pee"]'));
    const row = pendingRow(card);
    await expect(row).toContainText('Saving…');
    await expect(row).toContainText('Not saved yet', { timeout: 20_000 });

    // Retry reads the list, finds the event, and sends nothing.
    net.mode = 'ok';
    await row.locator('.retry-btn').click();
    await expect(row).toHaveCount(0);
    expect(net.sent).toHaveLength(1);
    // The reload makes one row more, not two
    await page.reload();
    await expect(card.locator('#timeline-body .event-row').first()).toBeVisible();
    await expect(card.locator('#timeline-body .event-row')).toHaveCount(before + 1);
  });

  test('Discard removes a failed row and sends nothing', async ({ page }) => {
    const net = await proxyWebSocket(page);
    net.mode = 'fail';
    await openDashboard(page);
    const card = page.locator('pawsistant-card').first();
    await expect(card.locator('#timeline-body .event-row').first()).toBeVisible();
    const before = await card.locator('#timeline-body .event-row').count();

    await holdToLog(page, card.locator('.log-btn[data-type="poop"]'));
    const row = pendingRow(card);
    await expect(row).toContainText('Not saved yet');
    await row.locator('.discard-btn').click();
    await expect(row).toHaveCount(0);
    await expect(card.locator('#timeline-body .event-row')).toHaveCount(before);
    expect(net.sent).toHaveLength(1);
  });
});
