/**
 * Pawsistant Card — Utility functions
 */

/** U13 — slugify handles non-ASCII names */
export function slugify(name) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
}

/**
 * Resolve entity IDs for a dog by scanning hass.states for sensors with
 * `attributes.dog === dogName` (case-insensitive) and matching by friendly_name
 * suffix. Rename-safe: works even if the user renamed entity IDs in HA.
 *
 * Falls back to slug-derived IDs for any role not found via attribute scan.
 */
export function findEntitiesByDog(hass, dogName) {
  const slug = slugify(dogName);
  const fallback = {
    timeline:      `sensor.${slug}_recent_timeline`,
    pee_count:     `sensor.${slug}_daily_pee_count`,
    poop_count:    `sensor.${slug}_daily_poop_count`,
    medicine_days: `sensor.${slug}_days_since_medicine`,
    weight:        `sensor.${slug}_weight`,
  };

  if (!hass || !dogName) return fallback;

  const nameLower = dogName.toLowerCase();
  const result = { ...fallback };

  // Role → friendly_name suffix
  const ROLE_SUFFIXES = {
    timeline:      'recent timeline',
    pee_count:     'daily pee count',
    poop_count:    'daily poop count',
    medicine_days: 'days since medicine',
    weight:        'weight',
  };

  for (const [entityId, state] of Object.entries(hass.states)) {
    const attrDog = state.attributes && state.attributes.dog;
    if (!attrDog || attrDog.toLowerCase() !== nameLower) continue;

    const friendlyName = (state.attributes.friendly_name || '').toLowerCase();
    for (const [role, suffix] of Object.entries(ROLE_SUFFIXES)) {
      if (friendlyName.endsWith(suffix)) {
        result[role] = entityId;
        break;
      }
    }
  }

  return result;
}

export function stateNum(hass, entity) {
  if (!entity || !hass.states[entity]) return null;
  const val = parseFloat(hass.states[entity].state);
  return isNaN(val) ? null : val;
}

export function stateStr(hass, entity) {
  if (!entity || !hass.states[entity]) return null;
  const s = hass.states[entity].state;
  if (s === 'unavailable' || s === 'unknown') return null;
  return s;
}

export function stateAttr(hass, entity, attr) {
  if (!entity || !hass.states[entity]) return null;
  return hass.states[entity].attributes[attr] ?? null;
}

/** Simple hash of the relevant state for render diffing */
export function buildHash(hass, cfg) {
  const entities = findEntitiesByDog(hass, cfg.dog || '');
  const tEnt = cfg.timeline_entity || entities.timeline;
  const peeEnt = cfg.pee_count_entity || entities.pee_count;
  const poopEnt = cfg.poop_count_entity || entities.poop_count;
  const medEnt = cfg.medicine_days_entity || entities.medicine_days;
  const parts = [
    stateStr(hass, tEnt) || '',
    stateStr(hass, peeEnt) || '',
    stateStr(hass, poopEnt) || '',
    stateStr(hass, medEnt) || '',
    JSON.stringify(stateAttr(hass, tEnt, 'events') || []),
    JSON.stringify(stateAttr(hass, tEnt, 'event_types') || {}),
    JSON.stringify(stateAttr(hass, tEnt, 'button_metrics') || {}),
    JSON.stringify(stateAttr(hass, tEnt, 'shown_types') || null),
  ];
  return parts.join('|');
}

/**
 * Convert a stored lbs value to the display unit.
 * The weight sensor always stores values in lbs; call this wherever a value
 * from the sensor is shown to the user (button badge, form pre-fill).
 */
export function toDisplayWeight(lbs, unit) {
  if (lbs === null || lbs === undefined) return null;
  if (unit === 'kg') return Math.round((lbs / 2.20462) * 10) / 10;
  return lbs;
}

/** Shared escape helper (XSS prevention) */
export function _escapeHTML(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}