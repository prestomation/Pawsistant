/**
 * Pawsistant Card — Standalone timeline (event log) tests
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { createEventLog } from '../src/standalone-timeline.js';

const REGISTRY = {
  pee: { emoji: '💧', label: 'Pee', color: '#888' },
  poop: { emoji: '💩', label: 'Poop', color: '#888' },
  weight: { emoji: '⚖️', label: 'Weight', color: '#888' },
};

function ev(id, overrides = {}) {
  return {
    type: 'pee',
    event_id: id,
    time: '14:32',
    day: 'Today',
    date: 'Jun 12',
    iso: '2026-06-12T14:32:00.000Z',
    note: '',
    ...overrides,
  };
}

/** hass mock whose WS responder is driven by pageFn(offset, limit). */
function mockHass(pageFn) {
  return {
    states: {},
    callService: vi.fn().mockResolvedValue(undefined),
    connection: {
      sendCommand: vi.fn(),
      sendMessagePromise: vi.fn(async (msg) => pageFn(msg.offset, msg.limit)),
    },
  };
}

function makeDom() {
  const container = document.createElement('div');
  const formSlot = document.createElement('div');
  document.body.appendChild(formSlot);
  document.body.appendChild(container);
  return { container, formSlot };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe('createEventLog', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    vi.useRealTimers();
  });

  it('fetches page 0 and renders rows grouped by day headers', async () => {
    const { container, formSlot } = makeDom();
    const events = [
      ev('e1', { note: 'at park' }),
      ev('e2', { type: 'poop', time: '09:00' }),
      ev('e3', { day: 'Yesterday', date: 'Jun 11', time: '21:00' }),
    ];
    const hass = mockHass(() => ({ events, total: 3 }));

    const handle = createEventLog({ container, formSlot, hass, dogId: 'dog1', registry: REGISTRY, weightUnit: 'lbs' });
    await flush();

    expect(hass.connection.sendMessagePromise).toHaveBeenCalledWith({
      type: 'pawsistant/get_events',
      dog_id: 'dog1',
      offset: 0,
      limit: 50,
    });
    expect(container.querySelectorAll('.event-row').length).toBe(3);
    expect(container.querySelectorAll('.day-header').length).toBe(2);
    expect(container.querySelector('.event-note').textContent).toBe('at park');
    // All loaded — no load-more button
    expect(container.querySelector('.load-more-btn')).toBeNull();

    handle.cleanup();
  });

  it('renders empty state when there are no events', async () => {
    const { container, formSlot } = makeDom();
    const hass = mockHass(() => ({ events: [], total: 0 }));

    const handle = createEventLog({ container, formSlot, hass, dogId: 'dog1', registry: REGISTRY, weightUnit: 'lbs' });
    await flush();

    expect(container.querySelector('.empty')).not.toBeNull();
    expect(container.querySelectorAll('.event-row').length).toBe(0);
    handle.cleanup();
  });

  it('renders empty state without throwing when hass.connection is missing', async () => {
    const { container, formSlot } = makeDom();
    const hass = { states: {}, callService: vi.fn() };

    const handle = createEventLog({ container, formSlot, hass, dogId: 'dog1', registry: REGISTRY, weightUnit: 'lbs' });
    await flush();

    expect(container.querySelector('.empty')).not.toBeNull();
    handle.cleanup();
  });

  it('paginates via the load-more button without duplicating day headers', async () => {
    const { container, formSlot } = makeDom();
    const page0 = [ev('e1'), ev('e2', { time: '13:00' })];
    const page1 = [ev('e3', { time: '12:00' }), ev('e4', { day: 'Yesterday', date: 'Jun 11' })];
    const hass = mockHass((offset) => (offset === 0 ? { events: page0, total: 4 } : { events: page1, total: 4 }));

    const handle = createEventLog({ container, formSlot, hass, dogId: 'dog1', registry: REGISTRY, weightUnit: 'lbs' });
    await flush();

    const loadMoreBtn = container.querySelector('.load-more-btn');
    expect(loadMoreBtn).not.toBeNull();
    expect(loadMoreBtn.textContent).toContain('2');
    expect(loadMoreBtn.textContent).toContain('4');

    loadMoreBtn.click();
    await flush();

    expect(hass.connection.sendMessagePromise).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 2, limit: 50 }),
    );
    expect(container.querySelectorAll('.event-row').length).toBe(4);
    // 'Jun 12' continues into the second page — only one header for it
    expect(container.querySelectorAll('.day-header').length).toBe(2);
    // All loaded now — button removed
    expect(container.querySelector('.load-more-btn')).toBeNull();
    handle.cleanup();
  });

  it('deletes an event after two-tap confirmation and refetches', async () => {
    const { container, formSlot } = makeDom();
    const hass = mockHass(() => ({ events: [ev('e1')], total: 1 }));

    const handle = createEventLog({ container, formSlot, hass, dogId: 'dog1', registry: REGISTRY, weightUnit: 'lbs' });
    await flush();

    const delBtn = container.querySelector('.delete-btn');
    delBtn.click();
    expect(delBtn.classList.contains('confirm-pending')).toBe(true);
    expect(hass.callService).not.toHaveBeenCalled();

    delBtn.click();
    await flush();
    expect(hass.callService).toHaveBeenCalledWith('pawsistant', 'delete_event', { event_id: 'e1' });
    // Refetched page 0 after delete
    expect(hass.connection.sendMessagePromise).toHaveBeenCalledTimes(2);
    handle.cleanup();
  });

  it('reverts delete confirmation after 3 seconds', async () => {
    vi.useFakeTimers();
    const { container, formSlot } = makeDom();
    const hass = mockHass(() => ({ events: [ev('e1')], total: 1 }));

    const handle = createEventLog({ container, formSlot, hass, dogId: 'dog1', registry: REGISTRY, weightUnit: 'lbs' });
    await vi.advanceTimersByTimeAsync(0);

    const delBtn = container.querySelector('.delete-btn');
    delBtn.click();
    expect(delBtn.classList.contains('confirm-pending')).toBe(true);

    await vi.advanceTimersByTimeAsync(3000);
    expect(delBtn.classList.contains('confirm-pending')).toBe(false);

    // A click after the revert is a fresh first tap, not a confirm
    delBtn.click();
    expect(hass.callService).not.toHaveBeenCalled();
    handle.cleanup();
  });

  it('opens a prefilled edit form and submits update_event, then refetches', async () => {
    const { container, formSlot } = makeDom();
    const hass = mockHass(() => ({ events: [ev('e1', { note: 'at park' })], total: 1 }));

    const handle = createEventLog({ container, formSlot, hass, dogId: 'dog1', registry: REGISTRY, weightUnit: 'lbs' });
    await flush();

    container.querySelector('.edit-btn').click();
    await flush();

    const noteInput = formSlot.querySelector('#pbc-edit-note');
    expect(noteInput).not.toBeNull();
    expect(noteInput.value).toBe('at park');

    formSlot.querySelector('#pbc-edit-form-submit').click();
    await flush();

    expect(hass.callService).toHaveBeenCalledWith('pawsistant', 'update_event', expect.objectContaining({
      event_id: 'e1',
      note: 'at park',
      timestamp: expect.any(String),
    }));
    // Form removed and timeline refetched
    expect(formSlot.querySelector('.inline-form')).toBeNull();
    expect(hass.connection.sendMessagePromise).toHaveBeenCalledTimes(2);
    handle.cleanup();
  });

  it('cleanup empties container and form slot', async () => {
    const { container, formSlot } = makeDom();
    const hass = mockHass(() => ({ events: [ev('e1')], total: 1 }));

    const handle = createEventLog({ container, formSlot, hass, dogId: 'dog1', registry: REGISTRY, weightUnit: 'lbs' });
    await flush();
    expect(container.querySelectorAll('.event-row').length).toBe(1);

    handle.cleanup();
    expect(container.innerHTML).toBe('');
    expect(formSlot.innerHTML).toBe('');
  });
});
