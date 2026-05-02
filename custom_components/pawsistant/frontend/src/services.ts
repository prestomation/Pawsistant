/**
 * Pawsistant Card — Service call wrappers
 */

import type { HomeAssistant } from './types';

export function logEvent(hass: HomeAssistant, dog: string, eventType: string, extra: Record<string, unknown> = {}): Promise<unknown> {
  return hass.callService('pawsistant', 'log_event', {
    dog,
    event_type: eventType,
    ...extra,
  });
}

export function deleteEvent(hass: HomeAssistant, eventId: string): Promise<unknown> {
  return hass.callService('pawsistant', 'delete_event', {
    event_id: eventId,
  });
}

export function updateEvent(hass: HomeAssistant, eventId: string, opts: { timestamp?: string; note?: string; value?: number | string | null } = {}): Promise<unknown> {
  const data: Record<string, unknown> = { event_id: eventId };
  if (opts.timestamp !== undefined) data.timestamp = opts.timestamp;
  if (opts.note !== undefined) data.note = opts.note;
  if (opts.value !== undefined) data.value = opts.value;
  return hass.callService('pawsistant', 'update_event', data);
}

export function setShownTypes(hass: HomeAssistant, dog: string, shownTypes: string[]): Promise<unknown> {
  return hass.callService('pawsistant', 'set_shown_types', {
    dog,
    shown_types: shownTypes,
  });
}

export function addEventType(hass: HomeAssistant, payload: Record<string, unknown>): Promise<unknown> {
  return hass.callService('pawsistant', 'add_event_type', payload);
}

export function updateEventType(hass: HomeAssistant, payload: Record<string, unknown>): Promise<unknown> {
  return hass.callService('pawsistant', 'update_event_type', payload);
}

export function deleteEventType(hass: HomeAssistant, eventType: string): Promise<unknown> {
  return hass.callService('pawsistant', 'delete_event_type', { event_type: eventType });
}