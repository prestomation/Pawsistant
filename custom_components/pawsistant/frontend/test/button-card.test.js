/**
 * Pawsistant Card — Button card tests
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
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
