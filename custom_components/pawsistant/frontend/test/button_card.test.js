/**
 * Pawsistant Button Card — integration tests
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import '../src/button-card.js';

function makeHass(overrides = {}) {
  return {
    states: {
      'sensor.rex_daily_poop_count': {
        state: '3',
        attributes: { dog: 'Rex', friendly_name: 'Rex Daily Poop Count' },
      },
      'sensor.rex_recent_timeline': {
        state: 'ok',
        attributes: {
          dog: 'Rex',
          friendly_name: 'Rex Recent Timeline',
          event_types: { poop: { name: 'Poop', icon: 'mdi:emoticon-poop', color: '#FF8A65' } },
          button_metrics: { poop: 'daily_count' },
        },
      },
    },
    callService: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

describe('pawsistant-button-card', () => {
  let card;
  beforeEach(() => {
    card = document.createElement('pawsistant-button-card');
    document.body.appendChild(card);
  });
  afterEach(() => { card.remove(); });

  it('renders an error when dog is missing', () => {
    card.setConfig({ event_type: 'poop' });
    card.hass = makeHass();
    expect(card.shadowRoot.textContent).toMatch(/dog/i);
  });

  it('renders an error when dog is not found in hass.states', () => {
    card.setConfig({ dog: 'Ghost', event_type: 'poop' });
    card.hass = makeHass();
    expect(card.shadowRoot.textContent).toMatch(/not found|unknown/i);
  });

  it('renders an error when event_type is missing', () => {
    card.setConfig({ dog: 'Rex' });
    card.hass = makeHass();
    expect(card.shadowRoot.textContent).toMatch(/event/i);
  });

  it('renders the button with correct label for valid config', () => {
    card.setConfig({ dog: 'Rex', event_type: 'poop' });
    card.hass = makeHass();
    const btn = card.shadowRoot.querySelector('.log-btn');
    expect(btn).not.toBeNull();
    expect(btn.querySelector('.btn-label').textContent).toContain('Poop');
  });

  it('shows dog name as title when show_title is not false', () => {
    card.setConfig({ dog: 'Rex', event_type: 'poop' });
    card.hass = makeHass();
    expect(card.shadowRoot.querySelector('.card-title').textContent).toContain('Rex');
  });

  it('hides title when show_title: false', () => {
    card.setConfig({ dog: 'Rex', event_type: 'poop', show_title: false });
    card.hass = makeHass();
    expect(card.shadowRoot.querySelector('.card-title')).toBeNull();
  });

  it('long press calls log_event service', () => {
    const hass = makeHass();
    card.setConfig({ dog: 'Rex', event_type: 'poop' });
    card.hass = hass;

    const btn = card.shadowRoot.querySelector('.log-btn');
    vi.useFakeTimers();
    btn.dispatchEvent(new MouseEvent('pointerdown'));
    vi.advanceTimersByTime(500);
    vi.useRealTimers();

    expect(hass.callService).toHaveBeenCalledWith('pawsistant', 'log_event',
      expect.objectContaining({ dog: 'Rex', event_type: 'poop' }));
  });

  it('getCardSize returns a positive number', () => {
    card.setConfig({ dog: 'Rex', event_type: 'poop' });
    expect(card.getCardSize()).toBeGreaterThan(0);
  });

  it('getStubConfig returns a valid starter config', () => {
    const Ctor = customElements.get('pawsistant-button-card');
    const stub = Ctor.getStubConfig ? Ctor.getStubConfig(makeHass()) : null;
    expect(stub).not.toBeNull();
    expect(stub.type).toBe('custom:pawsistant-button-card');
    expect(stub.event_type).toBe('poop');
  });
});
