/**
 * Pawsistant Card — main card (pawsistant-card) tests
 */
import { describe, it, expect, vi } from 'vitest';
import { PawsistantCard } from '../src/index.js';

function mockHass(dogs = ['Sharky']) {
  const states = {};
  for (const dog of dogs) {
    const slug = dog.toLowerCase();
    states[`sensor.${slug}_recent_timeline`] = {
      state: 'ok',
      attributes: { dog, dog_id: slug, friendly_name: `${dog} Recent Timeline` },
    };
    states[`sensor.${slug}_weight`] = {
      state: '80',
      attributes: { dog, friendly_name: `${dog} Weight` },
    };
  }
  // No `connection` → _fetchTimeline no-ops, keeping render synchronous.
  return { states, callService: vi.fn().mockResolvedValue(undefined), language: 'en' };
}

describe('PawsistantCard unknown dog', () => {
  it('renders an error card when the configured dog does not exist', () => {
    const card = new PawsistantCard();
    card.setConfig({ type: 'custom:pawsistant-card', dog: 'Ghost' });
    card.hass = mockHass(['Sharky']);
    const err = card.shadowRoot.querySelector('.pc-error');
    expect(err).not.toBeNull();
    expect(err.textContent).toContain('Ghost');
  });

  it('does not render an error card for a known dog', () => {
    const card = new PawsistantCard();
    card.setConfig({ type: 'custom:pawsistant-card', dog: 'Sharky' });
    card.hass = mockHass(['Sharky']);
    expect(card.shadowRoot.querySelector('.pc-error')).toBeNull();
  });

  it('escapes HTML in the unknown dog name', () => {
    const card = new PawsistantCard();
    card.setConfig({ type: 'custom:pawsistant-card', dog: '<b>x</b>' });
    card.hass = mockHass(['Sharky']);
    expect(card.shadowRoot.innerHTML).not.toContain('<b>x</b>');
  });
});
