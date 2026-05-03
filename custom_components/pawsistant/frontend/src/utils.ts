/**
 * Pawsistant Card — Utility functions
 */

import type { HomeAssistant, DogEntities, PawsistantCardConfig } from './types';

/** U13 — slugify handles non-ASCII names */
export function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
}

const ROLE_SUFFIXES: Record<keyof DogEntities, string> = {
  timeline:      'recent timeline',
  pee_count:     'daily pee count',
  poop_count:    'daily poop count',
  medicine_days: 'days since medicine',
  weight:        'weight',
};

/**
 * Resolve entity IDs for a dog by scanning hass.states for sensors with
 * `attributes.dog === dogName`. Rename-safe.
 */
export function findEntitiesByDog(hass: HomeAssistant | null, dogName: string | undefined): DogEntities {
  const slug = slugify(dogName || '');
  const fallback: DogEntities = {
    timeline:      `sensor.${slug}_recent_timeline`,
    pee_count:     `sensor.${slug}_daily_pee_count`,
    poop_count:    `sensor.${slug}_daily_poop_count`,
    medicine_days: `sensor.${slug}_days_since_medicine`,
    weight:        `sensor.${slug}_weight`,
  };

  if (!hass || !dogName) return fallback;

  const nameLower = dogName.toLowerCase();
  const result: DogEntities = { ...fallback };

  for (const [entityId, state] of Object.entries(hass.states)) {
    const attrDog = state.attributes?.dog;
    if (!attrDog || attrDog.toLowerCase() !== nameLower) continue;

    const friendlyName = (state.attributes?.friendly_name || '').toLowerCase();
    for (const [role, suffix] of Object.entries(ROLE_SUFFIXES)) {
      if (friendlyName.endsWith(suffix)) {
        (result as unknown as Record<string, string>)[role] = entityId;
        break;
      }
    }
  }

  return result;
}

export function stateNum(hass: HomeAssistant, entity: string | undefined): number | null {
  if (!entity || !hass.states[entity]) return null;
  const val = parseFloat(hass.states[entity].state);
  return isNaN(val) ? null : val;
}

export function stateStr(hass: HomeAssistant, entity: string | undefined): string | null {
  if (!entity || !hass.states[entity]) return null;
  const s = hass.states[entity].state;
  if (s === 'unavailable' || s === 'unknown') return null;
  return s;
}

export function stateAttr(hass: HomeAssistant, entity: string | undefined, attr: string): unknown {
  if (!entity || !hass.states[entity]) return null;
  return hass.states[entity].attributes[attr] ?? null;
}

/** Simple hash of the relevant state for render diffing */
export function buildHash(hass: HomeAssistant, cfg: PawsistantCardConfig): string {
  const entities = findEntitiesByDog(hass, cfg.dog || '');
  const tEnt = cfg.timeline_entity || entities.timeline;
  const peeEnt = cfg.pee_count_entity || entities.pee_count;
  const poopEnt = cfg.poop_count_entity || entities.poop_count;
  const medEnt = cfg.medicine_days_entity || entities.medicine_days;
  const parts: string[] = [
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
 */
export function toDisplayWeight(lbs: number | null | undefined, unit: string): number | null {
  if (lbs === null || lbs === undefined) return null;
  if (unit === 'kg') return Math.round((lbs / 2.20462) * 10) / 10;
  return lbs;
}

/** Shared escape helper (XSS prevention) */
export function _escapeHTML(str: string): string {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}