/**
 * Pawsistant Card — main card (pawsistant-card) tests
 */
import { describe, it, expect, vi } from 'vitest';
import { PawsistantCard } from '../src/index.js';
import { openBackdateForm, openWeightForm } from '../src/forms.js';

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

describe('PawsistantCard.getStubConfig', () => {
  it('binds the preview to a real pet so the picker does not show an error', () => {
    // The picker renders this stub and hands it to setConfig on add, so a name
    // nobody owns surfaces as "Unknown dog" both in the preview and on the board.
    const cfg = PawsistantCard.getStubConfig(mockHass(['Sharky']));
    expect(cfg.dog).toBe('Sharky');
    expect(cfg.type).toBe('custom:pawsistant-card');
  });

  it('picks a pet deterministically when several exist', () => {
    // dogNamesFromHass sorts, so the preview does not flip between pets.
    const cfg = PawsistantCard.getStubConfig(mockHass(['Rex', 'Ada']));
    expect(cfg.dog).toBe('Ada');
  });

  it('falls back to a placeholder before any pet exists', () => {
    expect(PawsistantCard.getStubConfig(mockHass([])).dog).toBe('MyDog');
  });

  it('does not throw when hass has no states at all', () => {
    expect(() => PawsistantCard.getStubConfig({ states: {} })).not.toThrow();
  });
});

describe('PawsistantCard event types panel delete button', () => {
  // The delete_event_type service is admin-only. The card must show the
  // delete button only to an admin user.
  function openPanel(user) {
    const card = new PawsistantCard();
    card.setConfig({ type: 'custom:pawsistant-card', dog: 'Sharky' });
    const hass = mockHass(['Sharky']);
    if (user !== undefined) hass.user = user;
    card.hass = hass;
    card._openEventTypesPanel();
    return card.shadowRoot;
  }

  it('does not render the delete button for a non-admin user', () => {
    const root = openPanel({ is_admin: false });
    expect(root.querySelectorAll('.event-type-row').length).toBeGreaterThan(0);
    expect(root.querySelectorAll('.et-btn.edit').length).toBeGreaterThan(0);
    expect(root.querySelectorAll('.et-btn.delete').length).toBe(0);
  });

  it('renders 1 delete button for each row for an admin user', () => {
    const root = openPanel({ is_admin: true });
    const rows = root.querySelectorAll('.event-type-row').length;
    expect(rows).toBeGreaterThan(0);
    expect(root.querySelectorAll('.et-btn.delete').length).toBe(rows);
    expect(root.querySelectorAll('.et-btn.edit').length).toBe(rows);
  });

  it('does not render the delete button when hass.user is missing', () => {
    const root = openPanel(undefined);
    expect(root.querySelectorAll('.event-type-row').length).toBeGreaterThan(0);
    expect(root.querySelectorAll('.et-btn.delete').length).toBe(0);
  });
});

describe('PawsistantCard storage button with an open care item form', () => {
  const SUPPLY = { entity_id: 'number.rolls_spares', amount: 1, name: 'Poop bag rolls' };

  function mount() {
    const hass = mockHass(['Sharky']);
    hass.states['sensor.sharky_recent_timeline'].attributes.event_types = {
      poop_bag: { name: 'Poop bag', icon: 'mdi:paper-roll', supply: SUPPLY },
      poop: { name: 'Poop', icon: 'mdi:emoticon-poop' },
      weight: { name: 'Weight', icon: 'mdi:scale-bathroom' },
    };
    hass.states['number.rolls_spares'] = {
      state: '3',
      attributes: { unit_of_measurement: 'roll', status: 'ok', reorder_at: 1, restock_quantity: 8 },
    };
    const card = new PawsistantCard();
    card.setConfig({
      type: 'custom:pawsistant-card',
      dog: 'Sharky',
      shown_types: ['poop_bag', 'poop', 'weight'],
    });
    card.hass = hass;
    return card;
  }

  function openCareItem(card, type) {
    const btn = card.shadowRoot.querySelector(`.log-btn[data-type="${type}"]`);
    expect(btn).not.toBeNull();
    openBackdateForm(card, btn, type);
  }

  it('closes the care item form and opens the supplies dialog', () => {
    const card = mount();
    openCareItem(card, 'poop');
    expect(card._activeForm).toBe('backdate');
    expect(card.shadowRoot.getElementById('inline-form-wrap').classList.contains('open')).toBe(true);

    card.shadowRoot.getElementById('supplies-btn').click();

    expect(card.shadowRoot.querySelector('.pw-sup-dialog')).not.toBeNull();
    expect(card._activeForm).toBe('supplies');
    expect(card._activeType).toBeNull();
    expect(card.shadowRoot.getElementById('inline-form-wrap').classList.contains('open')).toBe(false);
  });

  it('also works from the weight form', () => {
    const card = mount();
    const btn = card.shadowRoot.querySelector('.log-btn[data-weight="true"]');
    expect(btn).not.toBeNull();
    openWeightForm(card, btn);
    expect(card._activeForm).toBe('weight');
    card.shadowRoot.getElementById('supplies-btn').click();
    expect(card.shadowRoot.querySelector('.pw-sup-dialog')).not.toBeNull();
    expect(card._activeForm).toBe('supplies');
  });

  it('lets a care item open again after the supplies dialog closes', () => {
    const card = mount();
    openCareItem(card, 'poop');
    card.shadowRoot.getElementById('supplies-btn').click();
    card.shadowRoot.querySelector('.pw-sup-close').click();
    expect(card._activeForm).toBeNull();
    openCareItem(card, 'poop');
    expect(card._activeForm).toBe('backdate');
  });

  it('clears the open form when the settings panel opens', () => {
    const card = mount();
    openCareItem(card, 'poop');
    card._openEventTypesPanel();
    card._closeEventTypesPanel();
    expect(card._activeForm).toBeNull();
    card.shadowRoot.getElementById('supplies-btn').click();
    expect(card.shadowRoot.querySelector('.pw-sup-dialog')).not.toBeNull();
  });
});
