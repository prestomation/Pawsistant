/**
 * Pawsistant Card — Services module tests
 */
import { describe, it, expect, vi } from 'vitest';
import { logEvent, deleteEvent, setShownTypes, addEventType, updateEventType, deleteEventType } from '../src/services.js';

function mockHass() {
  return { callService: vi.fn() };
}

describe('logEvent', () => {
  it('calls pawsistant.log_event with dog and event_type', () => {
    const hass = mockHass();
    logEvent(hass, 'Sharky', 'poop');
    expect(hass.callService).toHaveBeenCalledWith('pawsistant', 'log_event', {
      dog: 'Sharky',
      event_type: 'poop',
    });
  });

  it('merges extra fields', () => {
    const hass = mockHass();
    logEvent(hass, 'Sharky', 'weight', { value: 45 });
    expect(hass.callService).toHaveBeenCalledWith('pawsistant', 'log_event', {
      dog: 'Sharky',
      event_type: 'weight',
      value: 45,
    });
  });
});

describe('deleteEvent', () => {
  it('calls pawsistant.delete_event with event_id', () => {
    const hass = mockHass();
    deleteEvent(hass, 'evt_123');
    expect(hass.callService).toHaveBeenCalledWith('pawsistant', 'delete_event', {
      event_id: 'evt_123',
    });
  });
});

describe('setShownTypes', () => {
  it('calls pawsistant.set_shown_types with dog and shown_types', () => {
    const hass = mockHass();
    setShownTypes(hass, 'Sharky', ['poop', 'pee']);
    expect(hass.callService).toHaveBeenCalledWith('pawsistant', 'set_shown_types', {
      dog: 'Sharky',
      shown_types: ['poop', 'pee'],
    });
  });
});

describe('addEventType', () => {
  it('calls pawsistant.add_event_type with payload', () => {
    const hass = mockHass();
    addEventType(hass, { dog: 'Sharky', event_type: 'bark', name: 'Bark', icon: 'mdi:dog', color: '#F00' });
    expect(hass.callService).toHaveBeenCalledWith('pawsistant', 'add_event_type', {
      dog: 'Sharky',
      event_type: 'bark',
      name: 'Bark',
      icon: 'mdi:dog',
      color: '#F00',
    });
  });
});

describe('updateEventType', () => {
  it('calls pawsistant.update_event_type with payload', () => {
    const hass = mockHass();
    updateEventType(hass, { event_type: 'bark', name: 'Barking' });
    expect(hass.callService).toHaveBeenCalledWith('pawsistant', 'update_event_type', {
      event_type: 'bark',
      name: 'Barking',
    });
  });
});

describe('deleteEventType', () => {
  it('calls pawsistant.delete_event_type with event_type', () => {
    const hass = mockHass();
    deleteEventType(hass, 'bark');
    expect(hass.callService).toHaveBeenCalledWith('pawsistant', 'delete_event_type', {
      event_type: 'bark',
    });
  });
});