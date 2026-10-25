/**
 * Pawsistant Card — Button card tests
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { PawsistantButtonCard } from '../src/button-card.js';

// Stub customElements.define to avoid duplicate registration errors
const originalDefine = customElements.define.bind(customElements);

function mockHass(dogs = ['Sharky'], eventTypes = {}) {
  const states = {};
  for (const dog of dogs) {
    const slug = dog.toLowerCase();
    states[`sensor.${slug}_recent_timeline`] = {
      state: 'ok',
      attributes: {
        dog,
        friendly_name: `${dog} Recent Timeline`,
        event_types: Object.keys(eventTypes).length > 0 ? eventTypes : undefined,
        button_metrics: {},
      },
    };
    states[`sensor.${slug}_daily_pee_count`] = {
      state: '3',
      attributes: { dog, friendly_name: `${dog} Daily Pee Count` },
    };
    states[`sensor.${slug}_daily_poop_count`] = {
      state: '2',
      attributes: { dog, friendly_name: `${dog} Daily Poop Count` },
    };
    states[`sensor.${slug}_days_since_medicine`] = {
      state: '5',
      attributes: { dog, friendly_name: `${dog} Days Since Medicine` },
    };
    states[`sensor.${slug}_weight`] = {
      state: '80',
      attributes: { dog, friendly_name: `${dog} Weight` },
    };
  }
  return {
    states,
    callService: vi.fn().mockResolvedValue(undefined),
  };
}

describe('PawsistantButtonCard', () => {
  describe('setConfig', () => {
    it('throws if dog is missing', () => {
      const card = new PawsistantButtonCard();
      expect(() => card.setConfig({ type: 'custom:pawsistant-button-card', dog: '', buttons: [{ event_type: 'poop' }] }))
        .toThrow(/dog/);
    });

    it('throws if buttons is empty', () => {
      const card = new PawsistantButtonCard();
      expect(() => card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Sharky', buttons: [] }))
        .toThrow(/button/);
    });

    it('accepts valid config with buttons array', () => {
      const card = new PawsistantButtonCard();
      expect(() => card.setConfig({
        type: 'custom:pawsistant-button-card',
        dog: 'Sharky',
        buttons: [{ event_type: 'poop' }, { event_type: 'pee' }],
      })).not.toThrow();
    });

    it('auto-migrates old single event_type to buttons array', () => {
      const card = new PawsistantButtonCard();
      card.setConfig({
        type: 'custom:pawsistant-button-card',
        dog: 'Sharky',
        event_type: 'poop',
      });
      expect(card._config.buttons).toEqual([{ event_type: 'poop' }]);
      expect(card._config.event_type).toBeUndefined();
    });

    it('throws if neither buttons nor event_type is provided', () => {
      const card = new PawsistantButtonCard();
      expect(() => card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Sharky' }))
        .toThrow(/button/);
    });
  });

  describe('hash comparison', () => {
    it('skips re-render when hash unchanged', () => {
      const card = new PawsistantButtonCard();
      card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Sharky', buttons: [{ event_type: 'poop' }] });
      const hass = mockHass();
      card.hass = hass;
      const firstHash = card._lastHash;

      // Set same hass again
      card.hass = hass;
      expect(card._lastHash).toBe(firstHash);
    });

    it('hash changes when button event_types change', () => {
      const card = new PawsistantButtonCard();
      card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Sharky', buttons: [{ event_type: 'poop' }] });
      const hass = mockHass();
      card._hass = hass;
      const hash1 = card._computeHash();

      card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Sharky', buttons: [{ event_type: 'poop' }, { event_type: 'pee' }] });
      const hash2 = card._computeHash();

      expect(hash1).not.toBe(hash2);
    });
  });

  describe('state enumeration cost (issue #94)', () => {
    // Wrap hass.states in a Proxy that counts every full enumeration
    // (Object.entries / values / keys all trigger the ownKeys trap).
    function countingHass(hass) {
      const counter = { n: 0 };
      hass.states = new Proxy(hass.states, {
        ownKeys(t) { counter.n++; return Reflect.ownKeys(t); },
      });
      return { hass, counter };
    }
    function makeCard(buttons = [{ event_type: 'poop' }, { event_type: 'pee' }]) {
      const card = new PawsistantButtonCard();
      card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Sharky', buttons });
      return card;
    }
    function nextHass(prev, patch = {}) {
      const states = { ...prev.states, ...patch };
      return { ...prev, states };
    }

    it('does not enumerate hass.states in _computeHash after the first hass', () => {
      const card = makeCard();
      card.hass = mockHass();
      const { hass, counter } = countingHass(nextHass(card._hass));
      card._hass = hass;
      counter.n = 0;
      card._computeHash();
      card._computeHash();
      expect(counter.n).toBe(0);
    });

    it('does not enumerate hass.states on a hass update with no relevant change', () => {
      const card = makeCard();
      card.hass = mockHass();
      const { hass, counter } = countingHass(nextHass(card._hass, {
        'light.kitchen': { state: 'on', attributes: { friendly_name: 'Kitchen' } },
      }));
      card.hass = hass;
      card.hass = hass;
      expect(counter.n).toBe(0);
    });

    it('still picks up a changed state of a cached entity', () => {
      const card = makeCard();
      card.hass = mockHass();
      const before = card._lastHash;
      card.hass = nextHass(card._hass, {
        'sensor.sharky_daily_pee_count': { state: '4', attributes: { dog: 'Sharky', friendly_name: 'Sharky Daily Pee Count' } },
      });
      expect(card._lastHash).not.toBe(before);
    });

    describe('timeline missing or dog unknown', () => {
      afterEach(() => { vi.useRealTimers(); });

      // The dog is known (its weight sensor exists) but the timeline is not there yet.
      function hassWithoutTimeline() {
        const h = mockHass();
        delete h.states['sensor.sharky_recent_timeline'];
        return h;
      }
      function updates(card, first, n) {
        const { hass: counted, counter } = countingHass(nextHass(first, {}));
        card.hass = counted;
        counter.n = 0;
        for (let i = 0; i < n; i++) {
          card.hass = { ...counted, states: counted.states };
        }
        return counter;
      }

      it('scans once, not on every update, while the timeline is missing', () => {
        const card = makeCard();
        const first = hassWithoutTimeline();
        card.hass = first;
        expect(updates(card, first, 5).n).toBe(0);
      });

      it('scans once, not on every update, for an unknown dog', () => {
        const card = makeCard();
        const first = mockHass(['Rex']);
        card.hass = first;
        expect(updates(card, first, 5).n).toBe(0);
      });

      it('finds a timeline that appears under its default id without a scan delay', () => {
        const card = makeCard();
        const first = hassWithoutTimeline();
        card.hass = first;
        card.hass = nextHass(first, { 'sensor.sharky_recent_timeline': mockHass().states['sensor.sharky_recent_timeline'] });
        expect(card._entities().timeline).toBe('sensor.sharky_recent_timeline');
        expect(card._entCache.timelineFound).toBe(true);
      });

      it('scans again after the rescan delay for a timeline with a custom id', () => {
        vi.useFakeTimers();
        const card = makeCard();
        const first = hassWithoutTimeline();
        card.hass = first;
        const tl = mockHass().states['sensor.sharky_recent_timeline'];
        card.hass = nextHass(first, { 'sensor.my_custom_timeline': tl });
        expect(card._entCache.timelineFound).toBe(false);
        vi.advanceTimersByTime(60_000);
        card.hass = nextHass(first, { 'sensor.my_custom_timeline': tl });
        expect(card._entities().timeline).toBe('sensor.my_custom_timeline');
      });
    });

    it('re-resolves entities after setConfig', () => {
      const card = makeCard();
      card.hass = mockHass(['Sharky', 'Rex']);
      card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Rex', buttons: [{ event_type: 'poop' }] });
      expect(card._entities().timeline).toBe('sensor.rex_recent_timeline');
    });

    it('re-resolves when a renamed entity replaces the cached one', () => {
      const card = makeCard();
      const first = mockHass();
      card.hass = first;
      const states = { ...first.states };
      const old = states['sensor.sharky_weight'];
      delete states['sensor.sharky_weight'];
      states['sensor.renamed_weight'] = old;
      card.hass = { ...first, states };
      expect(card._entities().weight).toBe('sensor.renamed_weight');
    });

    it('re-resolves when the cached entity changes dog', () => {
      const card = makeCard();
      const first = mockHass(['Sharky', 'Rex']);
      card.hass = first;
      const states = { ...first.states };
      states['sensor.sharky_weight'] = { state: '80', attributes: { dog: 'Rex', friendly_name: 'Rex Weight' } };
      states['sensor.sharky_weight_2'] = { state: '81', attributes: { dog: 'Sharky', friendly_name: 'Sharky Weight' } };
      card.hass = { ...first, states };
      expect(card._entities().weight).toBe('sensor.sharky_weight_2');
    });

    it('finds the entities when the dog appears after the first hass', () => {
      const card = makeCard();
      card.hass = { states: {}, callService: vi.fn() };
      card.hass = mockHass();
      expect(card._entities().timeline).toBe('sensor.sharky_recent_timeline');
    });
  });

  describe('_metricText', () => {
    it('returns daily_count for pee', () => {
      const card = new PawsistantButtonCard();
      card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Sharky', buttons: [{ event_type: 'pee' }] });
      card._hass = mockHass();
      const text = card._metricText('pee');
      expect(text).toBe('(3 today)');
    });

    it('returns daily_count for poop', () => {
      const card = new PawsistantButtonCard();
      card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Sharky', buttons: [{ event_type: 'poop' }] });
      card._hass = mockHass();
      const text = card._metricText('poop');
      expect(text).toBe('(2 today)');
    });

    it('returns last_value for weight', () => {
      const card = new PawsistantButtonCard();
      card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Sharky', buttons: [{ event_type: 'weight' }] });
      const hass = mockHass();
      hass.states['sensor.sharky_recent_timeline'].attributes.button_metrics = { weight: 'last_value' };
      card._hass = hass;
      const text = card._metricText('weight');
      expect(text).toBe('(80 lbs)');
    });

    it('returns empty string for unknown event type', () => {
      const card = new PawsistantButtonCard();
      card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Sharky', buttons: [{ event_type: 'custom_thing' }] });
      card._hass = mockHass();
      const text = card._metricText('custom_thing');
      expect(text).toBe('');
    });

    it('does not show the dog weight on non-weight buttons with last_value metric', () => {
      // Regression: the weight (last_value) reads the dog's weight sensor,
      // which is weight-specific. A non-weight button assigned last_value
      // must not display the dog's weight (forum bug: weight shown on every
      // button — Gewicht/Symptome/Tierarzt/Impfung all read "5.2 kg").
      const card = new PawsistantButtonCard();
      card.setConfig({
        type: 'custom:pawsistant-button-card',
        dog: 'Sharky',
        buttons: [{ event_type: 'weight' }, { event_type: 'vaccine' }],
      });
      const hass = mockHass();
      hass.states['sensor.sharky_recent_timeline'].attributes.button_metrics = {
        weight: 'last_value',
        vaccine: 'last_value',
      };
      card._hass = hass;

      // The weight button still shows the weight…
      expect(card._metricText('weight')).toBe('(80 lbs)');
      // …but the vaccine button must not borrow it.
      expect(card._metricText('vaccine')).toBe('');
    });

    it('shows daily_count for non-pee/poop and custom types from the daily_counts map', () => {
      const card = new PawsistantButtonCard();
      card.setConfig({
        type: 'custom:pawsistant-button-card',
        dog: 'Sharky',
        buttons: [{ event_type: 'walk' }, { event_type: 'playtime' }],
      });
      const hass = mockHass();
      const tl = hass.states['sensor.sharky_recent_timeline'].attributes;
      tl.button_metrics = { walk: 'daily_count', playtime: 'daily_count' };
      tl.daily_counts = { walk: 4, playtime: 1 };
      card._hass = hass;
      // Previously these silently showed nothing because the card only knew pee/poop.
      expect(card._metricText('walk')).toBe('(4 today)');
      expect(card._metricText('playtime')).toBe('(1 today)');
    });

    it('shows hours_since for any type from the last_event_ts map', () => {
      const card = new PawsistantButtonCard();
      card.setConfig({
        type: 'custom:pawsistant-button-card',
        dog: 'Sharky',
        buttons: [{ event_type: 'playtime' }],
      });
      const hass = mockHass();
      const tl = hass.states['sensor.sharky_recent_timeline'].attributes;
      tl.button_metrics = { playtime: 'hours_since' };
      tl.last_event_ts = { playtime: new Date(Date.now() - 3 * 3600000).toISOString() };
      card._hass = hass;
      // Previously hours_since read a last_<type>_ts attribute the backend never set.
      expect(card._metricText('playtime')).toBe('(3 hours)');
    });

    it('resolves days_since per-type from the map without label collisions', () => {
      // Two event types sharing a display name ("Shot") must show their own
      // value, not the first matching sensor's (the old friendly-name match leaked).
      const card = new PawsistantButtonCard();
      card.setConfig({
        type: 'custom:pawsistant-button-card',
        dog: 'Sharky',
        buttons: [{ event_type: 'rabies' }, { event_type: 'distemper' }],
      });
      const hass = mockHass(['Sharky'], { rabies: { name: 'Shot' }, distemper: { name: 'Shot' } });
      const tl = hass.states['sensor.sharky_recent_timeline'].attributes;
      tl.button_metrics = { rabies: 'days_since', distemper: 'days_since' };
      tl.days_since = { rabies: 10.2, distemper: 99.8 };
      card._hass = hass;
      expect(card._metricText('rabies')).toBe('(10d)');
      expect(card._metricText('distemper')).toBe('(99d)');
    });
  });

  describe('error cards', () => {
    it('renders error for unknown dog', () => {
      const card = new PawsistantButtonCard();
      card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Ghost', buttons: [{ event_type: 'poop' }] });
      card.hass = mockHass(['Sharky']);
      const errorEl = card.shadowRoot.querySelector('.pbc-error');
      expect(errorEl).not.toBeNull();
      expect(errorEl.textContent).toContain('Ghost');
    });
  });

  describe('_render grid layout', () => {
    it('renders grid with correct number of buttons', () => {
      const card = new PawsistantButtonCard();
      card.setConfig({
        type: 'custom:pawsistant-button-card',
        dog: 'Sharky',
        buttons: [{ event_type: 'poop' }, { event_type: 'pee' }, { event_type: 'weight' }],
      });
      card.hass = mockHass();
      const grid = card.shadowRoot.querySelector('.pbc-grid');
      expect(grid).not.toBeNull();
      const btns = grid.querySelectorAll('.log-btn');
      expect(btns.length).toBe(3);
    });

    it('renders error for empty buttons array after construction', () => {
      const card = new PawsistantButtonCard();
      // Manually set empty buttons to bypass setConfig validation
      card._config = { type: 'custom:pawsistant-button-card', dog: 'Sharky', buttons: [] };
      card._lastHash = null;
      card.hass = mockHass();
      const errorEl = card.shadowRoot.querySelector('.pbc-error');
      expect(errorEl).not.toBeNull();
      expect(errorEl.textContent).toContain('No buttons');
    });
  });

  describe('getCardSize', () => {
    it('returns 2 for single button', () => {
      const card = new PawsistantButtonCard();
      card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Sharky', buttons: [{ event_type: 'poop' }] });
      expect(card.getCardSize()).toBe(2);
    });

    it('returns correct size for multiple rows', () => {
      const card = new PawsistantButtonCard();
      card.setConfig({
        type: 'custom:pawsistant-button-card',
        dog: 'Sharky',
        buttons: [
          { event_type: 'poop' }, { event_type: 'pee' }, { event_type: 'weight' },
          { event_type: 'medicine' },
        ],
      });
      expect(card.getCardSize()).toBe(2); // ceil(4/3) = 2

      card.setConfig({
        type: 'custom:pawsistant-button-card',
        dog: 'Sharky',
        buttons: [
          { event_type: 'poop' }, { event_type: 'pee' }, { event_type: 'weight' },
          { event_type: 'medicine' }, { event_type: 'walk' }, { event_type: 'food' },
          { event_type: 'water' },
        ],
      });
      expect(card.getCardSize()).toBe(3); // ceil(7/3) = 3
    });
  });
});

describe('PawsistantButtonCard event log popup', () => {
  function popupHass() {
    const hass = mockHass(['Sharky']);
    hass.states['sensor.sharky_recent_timeline'].attributes.dog_id = 'dog1';
    hass.connection = {
      sendCommand: vi.fn(),
      sendMessagePromise: vi.fn().mockResolvedValue({ events: [], total: 0 }),
    };
    hass.language = 'en';
    return hass;
  }

  function popupCard(extraConfig = {}) {
    const card = new PawsistantButtonCard();
    card.setConfig({
      type: 'custom:pawsistant-button-card',
      dog: 'Sharky',
      buttons: [{ event_type: 'poop' }],
      ...extraConfig,
    });
    card.hass = popupHass();
    return card;
  }

  const flush = () => new Promise((r) => setTimeout(r, 0));

  it('does not render the event log button by default', () => {
    const card = popupCard();
    expect(card.shadowRoot.querySelector('#pbc-log-btn')).toBeNull();
  });

  it('renders the event log button when show_event_log is true', () => {
    const card = popupCard({ show_event_log: true });
    const btn = card.shadowRoot.querySelector('#pbc-log-btn');
    expect(btn).not.toBeNull();
    expect(btn.getAttribute('aria-haspopup')).toBe('dialog');
  });

  it('opens a dialog popup on click and fetches the event log', async () => {
    const card = popupCard({ show_event_log: true });
    card.shadowRoot.querySelector('#pbc-log-btn').click();
    await flush();

    const dialog = card.shadowRoot.querySelector('[role="dialog"]');
    expect(dialog).not.toBeNull();
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(card._hass.connection.sendMessagePromise).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'pawsistant/get_events', dog_id: 'dog1' }),
    );
  });

  it('keeps the popup open across hass updates', async () => {
    const card = popupCard({ show_event_log: true });
    card.shadowRoot.querySelector('#pbc-log-btn').click();
    await flush();

    // New hass with a changed metric state would normally trigger a re-render
    const newHass = popupHass();
    newHass.states['sensor.sharky_daily_poop_count'].state = '9';
    card.hass = newHass;

    expect(card.shadowRoot.querySelector('.pbc-overlay')).not.toBeNull();
    expect(card.shadowRoot.querySelector('[role="dialog"]')).not.toBeNull();
  });

  it('closes via the close button and restores the log button', async () => {
    const card = popupCard({ show_event_log: true });
    card.shadowRoot.querySelector('#pbc-log-btn').click();
    await flush();

    card.shadowRoot.querySelector('#pbc-dialog-close').click();
    expect(card.shadowRoot.querySelector('.pbc-overlay')).toBeNull();
    expect(card.shadowRoot.querySelector('#pbc-log-btn')).not.toBeNull();
    expect(card._activeForm).toBe(false);
  });

  it('closes on Escape', async () => {
    const card = popupCard({ show_event_log: true });
    card.shadowRoot.querySelector('#pbc-log-btn').click();
    await flush();

    const dialog = card.shadowRoot.querySelector('[role="dialog"]');
    dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(card.shadowRoot.querySelector('.pbc-overlay')).toBeNull();
  });

  it('closes on backdrop click but not on dialog click', async () => {
    const card = popupCard({ show_event_log: true });
    card.shadowRoot.querySelector('#pbc-log-btn').click();
    await flush();

    const overlay = card.shadowRoot.querySelector('.pbc-overlay');
    const dialog = overlay.querySelector('[role="dialog"]');
    dialog.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(card.shadowRoot.querySelector('.pbc-overlay')).not.toBeNull();

    overlay.dispatchEvent(new MouseEvent('click'));
    expect(card.shadowRoot.querySelector('.pbc-overlay')).toBeNull();
  });

  it('shows an empty state when the dog has no dog_id', async () => {
    const card = popupCard({ show_event_log: true });
    delete card._hass.states['sensor.sharky_recent_timeline'].attributes.dog_id;
    card.shadowRoot.querySelector('#pbc-log-btn').click();
    await flush();

    expect(card.shadowRoot.querySelector('[role="dialog"]')).not.toBeNull();
    expect(card.shadowRoot.querySelector('#pbc-log-body .empty')).not.toBeNull();
    expect(card._hass.connection.sendMessagePromise).not.toHaveBeenCalled();
  });
});

describe('PawsistantButtonCard supplies', () => {
  const SUPPLY = { entity_id: 'number.rolls_spares', amount: 1, name: 'Poop bag rolls' };

  function supplyHass(count = '3', status = 'ok') {
    const hass = mockHass(['Sharky'], {
      roll: { name: 'Roll', icon: 'mdi:paper-roll', color: '#888', supply: SUPPLY },
      poop: { name: 'Poop', icon: 'mdi:emoticon-poop', color: '#888' },
    });
    hass.states['number.rolls_spares'] = {
      state: count,
      attributes: { unit_of_measurement: 'roll', status, reorder_at: 1, restock_quantity: 8 },
    };
    return hass;
  }

  function mount(hass) {
    const card = new PawsistantButtonCard();
    card.setConfig({
      type: 'custom:pawsistant-button-card',
      dog: 'Sharky',
      buttons: [{ event_type: 'roll' }, { event_type: 'poop' }],
    });
    card.hass = hass;
    return card;
  }

  it('shows a stock badge only on the button that uses a supply', () => {
    const card = mount(supplyHass('1', 'low'));
    const buttons = card.shadowRoot.querySelectorAll('.log-btn');
    expect(buttons[0].querySelector('.stock-badge.low').textContent).toBe('1');
    expect(buttons[1].querySelector('.stock-badge')).toBeNull();
  });

  it('redraws the badge when the count changes', () => {
    const card = mount(supplyHass('3'));
    card.hass = supplyHass('2');
    expect(card.shadowRoot.querySelector('.stock-badge').textContent).toBe('2');
  });

  it('offers the Supplies popup from the header', () => {
    const card = mount(supplyHass('3'));
    const btn = card.shadowRoot.getElementById('pbc-supplies-btn');
    expect(btn).not.toBeNull();
    btn.click();
    expect(card.shadowRoot.querySelector('.pw-sup-dialog')).not.toBeNull();
    expect(card._activeForm).toBe(true);
    card.shadowRoot.querySelector('.pw-sup-close').click();
    expect(card._activeForm).toBe(false);
  });

  it('has no Supplies button when no button uses a supply', () => {
    const card = new PawsistantButtonCard();
    card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Sharky', buttons: [{ event_type: 'poop' }] });
    card.hass = supplyHass('3');
    expect(card.shadowRoot.getElementById('pbc-supplies-btn')).toBeNull();
  });

  it('shows what is left after a log, with an Undo that deletes the event', async () => {
    const hass = supplyHass('2');
    hass.callService.mockResolvedValue({ response: { event_id: 'ev-7' } });
    const card = mount(hass);
    const btn = card.shadowRoot.querySelector('.log-btn');
    card._instantLog(btn, 'roll');
    await Promise.resolve();
    await Promise.resolve();
    const toast = card.shadowRoot.querySelector('.pw-toast');
    expect(toast.textContent).toContain('Roll logged · 1 left');
    expect(toast.textContent).toContain('Low stock: Home Keeper added a Buy task');
    // The count arrives from Home Keeper: the card redraws, and the toast stays.
    const next = supplyHass('1', 'low');
    next.callService = hass.callService;
    card.hass = next;
    const again = card.shadowRoot.querySelector('.pw-toast');
    expect(again).not.toBeNull();
    again.querySelector('button').click();
    expect(hass.callService).toHaveBeenLastCalledWith('pawsistant', 'delete_event', { event_id: 'ev-7' });
  });

  it('shows no toast for a log that uses no supply', async () => {
    const hass = supplyHass('3');
    const card = mount(hass);
    const poop = card.shadowRoot.querySelectorAll('.log-btn')[1];
    card._instantLog(poop, 'poop');
    await Promise.resolve();
    await Promise.resolve();
    expect(card.shadowRoot.querySelector('.pw-toast')).toBeNull();
  });
});

describe('PawsistantButtonCard after a move in the page', () => {
  it('still answers a tap after it is taken out and put back', () => {
    const card = new PawsistantButtonCard();
    card.setConfig({ type: 'custom:pawsistant-button-card', dog: 'Sharky', buttons: [{ event_type: 'poop' }] });
    const hass = mockHass();
    card.hass = hass;
    document.body.appendChild(card);
    card.remove();
    document.body.appendChild(card);
    card.shadowRoot.querySelector('.log-btn').click();
    expect(card._activeForm).toBe(true);
    expect(card.shadowRoot.querySelector('#pbc-form-submit')).not.toBeNull();
    card.remove();
  });
});
