/**
 * Pawsistant Card — pending rows in the log (main card and button card popup).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { PawsistantCard } from '../src/index.js';
import { PawsistantButtonCard } from '../src/button-card.js';
import { buildEventRowsHTML } from '../src/timeline-render.js';
import { openBackdateForm } from '../src/forms.js';
import { createEventLog } from '../src/standalone-timeline.js';

const REGISTRY = {
  pee: { emoji: '💧', label: 'Pee', color: '#888' },
  poop: { emoji: '💩', label: 'Poop', color: '#888' },
};

const old = (id, iso, time, type = 'poop') => ({
  type, event_id: id, time, day: 'Mon', date: '11/16', iso, note: '',
});

/** A fake hass whose log_event call hangs until the test lets it go. */
function makeHass() {
  const net = { open: [], server: [old('old1', '2026-11-16T08:52:00-08:00', '8:52 AM')] };
  net.hass = {
    states: {
      'sensor.sharky_recent_timeline': {
        state: 'ok',
        attributes: { dog: 'Sharky', dog_id: 'sharky', friendly_name: 'Sharky Recent Timeline' },
      },
    },
    language: 'en',
    config: { time_zone: 'America/Los_Angeles' },
    callService: vi.fn((d, s, data) => new Promise((resolve, reject) => net.open.push({ data, resolve, reject }))),
    connection: {
      sendMessagePromise: vi.fn(async () => ({ events: [...net.server], total: net.server.length })),
    },
  };
  net.answer = (i = 0) => {
    const { data, resolve } = net.open[i];
    const id = `new${i}`;
    net.server.unshift(old(id, data.timestamp, '9:41 AM', data.event_type));
    resolve({ response: { event_id: id } });
  };
  return net;
}

const settle = async () => {
  await vi.advanceTimersByTimeAsync(0);
  await vi.advanceTimersByTimeAsync(0);
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-11-16T17:41:00.000Z')); // 9:41 AM in Seattle
});
afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = '';
});

async function mountMain(net) {
  const card = new PawsistantCard();
  card.setConfig({ type: 'custom:pawsistant-card', dog: 'Sharky', shown_types: ['pee', 'poop'] });
  card.hass = net.hass;
  document.body.appendChild(card);
  await settle();
  return card;
}

const rows = (card) => [...card.shadowRoot.querySelectorAll('.timeline-body .event-row')];

describe('buildEventRowsHTML — pending rows', () => {
  const base = { event_id: '', time: '9:41 AM', day: 'Mon', date: '11/16', iso: '2026-11-16T17:41:00.000Z', note: '' };

  it('draws a faded row with a spinner and no edit or delete button', () => {
    const { html } = buildEventRowsHTML([{ ...base, type: 'pee', pending: { id: 'p1', state: 'saving' } }], REGISTRY, null);
    const el = document.createElement('div');
    el.innerHTML = html;
    const row = el.querySelector('.event-row');
    expect(row.classList.contains('pending')).toBe(true);
    expect(row.dataset.pendingId).toBe('p1');
    expect(row.querySelector('.pending-status').textContent).toContain('Saving…');
    expect(row.querySelector('.pending-spin')).not.toBeNull();
    expect(row.querySelector('.delete-btn, .edit-btn, .retry-btn')).toBeNull();
  });

  it('draws "Not saved yet" with Retry and Discard when failed', () => {
    const { html } = buildEventRowsHTML([{ ...base, type: 'pee', pending: { id: 'p1', state: 'failed' } }], REGISTRY, null);
    const el = document.createElement('div');
    el.innerHTML = html;
    expect(el.querySelector('.event-row').classList.contains('failed')).toBe(true);
    expect(el.querySelector('.pending-status').textContent).toContain('Not saved yet');
    expect(el.querySelector('.retry-btn').textContent).toBe('Retry');
    expect(el.querySelector('.discard-btn').textContent).toBe('Discard');
    expect(el.querySelector('.retry-btn').dataset.pendingId).toBe('p1');
  });

  it('keeps the edit and delete buttons of a normal row, and escapes the note', () => {
    const { html } = buildEventRowsHTML([{ ...base, type: 'pee', event_id: 'a', note: '<b>x</b>' }], REGISTRY, null);
    expect(html).toContain('delete-btn');
    expect(html).not.toContain('<b>x</b>');
  });
});

describe('main card — a tap', () => {
  it('shows a faded row at 0 s, "Not saved yet" at 15 s, and a solid row after a late answer', async () => {
    const net = makeHass();
    const card = await mountMain(net);
    expect(rows(card)).toHaveLength(1);

    const btn = card.shadowRoot.querySelector('.log-btn[data-type="pee"]');
    card._instantLog(btn, 'pee');
    // The tap sends the phone time
    expect(net.open[0].data.timestamp).toBe('2026-11-16T17:41:00.000Z');
    expect(rows(card)).toHaveLength(2);
    expect(rows(card)[0].classList.contains('pending')).toBe(true);
    expect(rows(card)[0].textContent).toContain('9:41 AM');
    expect(rows(card)[0].textContent).toContain('Saving…');

    await vi.advanceTimersByTimeAsync(5000);
    expect(rows(card)[0].textContent).toContain('Saving…');
    await vi.advanceTimersByTimeAsync(10000);
    expect(rows(card)[0].classList.contains('failed')).toBe(true);
    expect(rows(card)[0].textContent).toContain('Not saved yet');
    // The button is free again
    expect(btn.dataset.pending).toBeUndefined();

    await vi.advanceTimersByTimeAsync(15000); // 30 s
    net.answer();
    await settle();
    const after = rows(card);
    expect(after).toHaveLength(2);
    expect(after[0].classList.contains('pending')).toBe(false);
    expect(after[0].classList.contains('failed')).toBe(false);
    expect(after[0].querySelector('.delete-btn')).not.toBeNull();
    expect(card._pending.entries).toHaveLength(0);
  });

  it('keeps the list in place when a state push re-renders the card', async () => {
    const net = makeHass();
    const card = await mountMain(net);
    card._instantLog(card.shadowRoot.querySelector('.log-btn[data-type="pee"]'), 'pee');
    card.hass = { ...net.hass, states: { ...net.hass.states, 'sensor.other': { state: '1', attributes: {} } } };
    expect(rows(card)[0].classList.contains('pending')).toBe(true);
  });

  it('shows two pending rows with their own state', async () => {
    const net = makeHass();
    const card = await mountMain(net);
    card._instantLog(card.shadowRoot.querySelector('.log-btn[data-type="pee"]'), 'pee');
    await vi.advanceTimersByTimeAsync(10000);
    vi.setSystemTime(new Date('2026-11-16T17:41:30.000Z'));
    card._instantLog(card.shadowRoot.querySelector('.log-btn[data-type="poop"]'), 'poop');
    await vi.advanceTimersByTimeAsync(5000);
    const [newer, older] = rows(card);
    expect(newer.dataset.type).toBe('poop');
    expect(newer.classList.contains('pending')).toBe(true);
    expect(older.dataset.type).toBe('pee');
    expect(older.classList.contains('failed')).toBe(true);
  });

  it('Discard removes the row; Retry reads the list first and shows no copy', async () => {
    const net = makeHass();
    const card = await mountMain(net);
    card._instantLog(card.shadowRoot.querySelector('.log-btn[data-type="pee"]'), 'pee');
    // The server stored it, the reply is lost
    net.server.unshift(old('lost', net.open[0].data.timestamp, '9:41 AM', 'pee'));
    await vi.advanceTimersByTimeAsync(15000);

    rows(card)[0].querySelector('.retry-btn').click();
    await settle();
    expect(net.hass.callService).toHaveBeenCalledTimes(1);
    const shown = rows(card);
    expect(shown).toHaveLength(2);
    expect(shown[0].dataset.id).toBe('lost');

    // A second tap, then Discard
    card._instantLog(card.shadowRoot.querySelector('.log-btn[data-type="poop"]'), 'poop');
    await vi.advanceTimersByTimeAsync(15000);
    rows(card)[0].querySelector('.discard-btn').click();
    expect(rows(card)).toHaveLength(2);
    expect(card._pending.entries).toHaveLength(0);
  });
});

describe('main card — a backdated entry', () => {
  it('shows the row at its own time and closes the form', async () => {
    const net = makeHass();
    const card = await mountMain(net);
    const btn = card.shadowRoot.querySelector('.log-btn[data-type="pee"]');
    openBackdateForm(card, btn, 'pee');
    card.shadowRoot.querySelector('#bd-minutes-slider').value = '60';
    card.shadowRoot.querySelector('#form-submit').click();

    expect(card._activeForm).toBeNull();
    expect(net.open[0].data.timestamp).toBe('2026-11-16T16:41:00.000Z');
    const shown = rows(card);
    // 8:41 AM is after 8:52 AM? No: it is before, so the row goes below the 8:52 AM event.
    expect(shown.map((r) => r.dataset.id ?? '')).toEqual(['old1', '']);
    expect(shown[1].classList.contains('pending')).toBe(true);
    expect(shown[1].textContent).toContain('8:41 AM');
  });
});

describe('button card popup', () => {
  function mountButton(net) {
    const card = new PawsistantButtonCard();
    card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Sharky', buttons: [{ event_type: 'pee' }] });
    card.hass = net.hass;
    document.body.appendChild(card);
    return card;
  }

  it('shows a tap that was made before the popup opened, and updates it', async () => {
    const net = makeHass();
    const card = mountButton(net);
    card._instantLog(card.shadowRoot.querySelector('.log-btn'), 'pee');
    card._openEventLog();
    await settle();
    const body = () => [...card.shadowRoot.querySelectorAll('#pbc-log-body .event-row')];
    expect(body()[0].classList.contains('pending')).toBe(true);
    await vi.advanceTimersByTimeAsync(15000);
    expect(body()[0].textContent).toContain('Not saved yet');
    net.answer();
    await settle();
    expect(body()[0].classList.contains('pending')).toBe(false);
    expect(body()[0].classList.contains('failed')).toBe(false);
    expect(body()).toHaveLength(2);
  });

  it('a backdated entry closes the form at once and shows its row', async () => {
    const net = makeHass();
    const card = mountButton(net);
    card._openEventLog();
    await settle();
    card._closeEventLog();
    card._openBackdate(card.shadowRoot.querySelector('.log-btn'), { emoji: '💧', label: 'Pee', color: '#888' }, 'pee');
    card.shadowRoot.querySelector('#pbc-form-submit').click();
    await settle();
    expect(card.shadowRoot.querySelector('#pbc-form-submit')).toBeNull();
    expect(card._pending.entries).toHaveLength(1);
    expect(net.open[0].data.timestamp).toBeDefined();
  });
});

describe('standalone log with no pending list', () => {
  it('still works with no pending option', async () => {
    const container = document.createElement('div');
    const formSlot = document.createElement('div');
    document.body.append(formSlot, container);
    const net = makeHass();
    const log = createEventLog({ container, formSlot, hass: net.hass, dogId: 'sharky', registry: REGISTRY, weightUnit: 'kg' });
    await settle();
    expect(container.querySelectorAll('.event-row')).toHaveLength(1);
    log.cleanup();
  });
});
