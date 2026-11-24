/**
 * Main card: every destructive action asks first, in the shared dialog.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PawsistantCard } from '../src/index.js';

function mockHass() {
  return {
    states: {
      'sensor.sharky_recent_timeline': {
        state: 'ok',
        attributes: { dog: 'Sharky', dog_id: 'sharky', friendly_name: 'Sharky Recent Timeline' },
      },
    },
    callService: vi.fn().mockResolvedValue(undefined),
    language: 'en',
    user: { is_admin: true },
  };
}

function makeCard(events = []) {
  const card = new PawsistantCard();
  card.setConfig({ type: 'custom:pawsistant-card', dog: 'Sharky' });
  card._timelineEvents = events;
  card._timelineFetched = true;
  card._fetchTimeline = vi.fn();
  card.hass = mockHass();
  return card;
}

const scrim = () => document.querySelector('.pw-confirm-scrim');
const btn = (i) => document.querySelectorAll('.pw-confirm-scrim button')[i];

afterEach(() => {
  document.body.innerHTML = '';
});

describe('delete a log entry', () => {
  const ev = { type: 'pee', event_id: 'e1', time: '14:32', day: 'Today', date: 'Jun 12', iso: '2026-06-12T14:32:00.000Z', note: 'at the park' };

  it('asks first and does not delete on the first tap', () => {
    const card = makeCard([ev]);
    card._render();
    card.shadowRoot.querySelector('.delete-btn').click();
    expect(scrim()).not.toBeNull();
    expect(btn(1).textContent).toBe('Delete entry');
    expect(card._hass.callService).not.toHaveBeenCalledWith('pawsistant', 'delete_event', expect.anything());
  });

  it('deletes after the confirm button, and not after Cancel', async () => {
    const card = makeCard([ev]);
    card._render();
    card.shadowRoot.querySelector('.delete-btn').click();
    btn(0).click();
    expect(card._hass.callService).not.toHaveBeenCalledWith('pawsistant', 'delete_event', expect.anything());
    card.shadowRoot.querySelector('.delete-btn').click();
    btn(1).click();
    await Promise.resolve();
    expect(card._hass.callService).toHaveBeenCalledWith('pawsistant', 'delete_event', { event_id: 'e1' });
  });
});

describe('the other row and header buttons still work beside the delete button', () => {
  it('opens the event types panel from the gear when the timeline has rows', () => {
    const ev = { type: 'pee', event_id: 'e1', time: '14:32', day: 'Today', date: 'Jun 12', iso: '2026-06-12T14:32:00.000Z', note: '' };
    const card = makeCard([ev]);
    card._render();
    expect(card.shadowRoot.querySelectorAll('.delete-btn')).toHaveLength(1);
    card.shadowRoot.querySelector('#et-gear-btn').click();
    expect(card.shadowRoot.querySelectorAll('.event-type-row').length).toBeGreaterThan(0);
  });
});

describe('delete an event type', () => {
  function open() {
    const card = makeCard();
    card._openEventTypesPanel();
    return card;
  }

  it('asks first, names the type and says that entries stay', () => {
    const card = open();
    card.shadowRoot.querySelector('.et-btn.delete').click();
    expect(scrim().querySelector('.pw-confirm-title').textContent).toMatch(/^Delete event type '.+'\?$/);
    expect(scrim().querySelector('.pw-confirm-body').textContent).toContain('Entries already logged stay in the log.');
    expect(btn(1).textContent).toBe('Delete event type');
    expect(card._hass.callService).not.toHaveBeenCalledWith('pawsistant', 'delete_event_type', expect.anything());
  });

  it('deletes only after the confirm button', async () => {
    const card = open();
    const row = card.shadowRoot.querySelector('.et-btn.delete');
    const key = row.dataset.etKey;
    row.click();
    btn(1).click();
    await Promise.resolve();
    expect(card._hass.callService).toHaveBeenCalledWith('pawsistant', 'delete_event_type', { event_type: key });
  });

  it('does not call the native confirm', () => {
    const native = vi.fn(() => true);
    vi.stubGlobal('confirm', native);
    const card = open();
    card.shadowRoot.querySelector('.et-btn.delete').click();
    vi.unstubAllGlobals();
    expect(native).not.toHaveBeenCalled();
  });
});

describe('stop using a supply', () => {
  it('asks before a save that clears the supply name', () => {
    const card = makeCard();
    card._registryCache = { registry: { poop: { emoji: '💩', icon: 'mdi:paw', label: 'Poop', color: '#888', supply: { name: 'Poop bag rolls', amount: 1 } } }, metrics: {} };
    card._openEventTypesPanel();
    card._openEventTypeForm('poop');
    const root = card.shadowRoot;
    const nameInput = root.querySelector('#et-supply-name');
    expect(nameInput).not.toBeNull();
    nameInput.value = '';
    root.querySelector('#et-icon-input').value = 'mdi:paw';
    card._saveEventTypeForm();
    expect(scrim().querySelector('.pw-confirm-title').textContent).toBe("Stop using the supply 'Poop bag rolls'?");
    expect(card._hass.callService).not.toHaveBeenCalledWith('pawsistant', 'update_event_type', expect.anything());
  });
});
