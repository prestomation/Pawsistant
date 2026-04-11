/**
 * Pawsistant Card — Service call wrappers
 */

export function logEvent(hass, dog, eventType, extra = {}) {
  return hass.callService('pawsistant', 'log_event', {
    dog,
    event_type: eventType,
    ...extra,
  });
}

export function deleteEvent(hass, eventId) {
  return hass.callService('pawsistant', 'delete_event', {
    event_id: eventId,
  });
}

export function setShownTypes(hass, dog, shownTypes) {
  return hass.callService('pawsistant', 'set_shown_types', {
    dog,
    shown_types: shownTypes,
  });
}

export function addEventType(hass, payload) {
  return hass.callService('pawsistant', 'add_event_type', payload);
}

export function updateEventType(hass, payload) {
  return hass.callService('pawsistant', 'update_event_type', payload);
}

export function deleteEventType(hass, eventType) {
  return hass.callService('pawsistant', 'delete_event_type', { event_type: eventType });
}