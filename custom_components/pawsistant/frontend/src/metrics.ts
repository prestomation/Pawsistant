/**
 * Pawsistant Card — Metric label formatters + shared per-type value resolver
 */

import type { HomeAssistant, DogEntities, Registry, MetricLabels } from './types';
import { stateAttr, stateNum, toDisplayWeight } from './utils';
import { getMeta } from './registry';

export const METRIC_LABELS: MetricLabels = {
  daily_count: (n: number): string => `${n} today`,
  days_since:  (n: number): string => `${n} days`,
  last_value:  (v: number, unit?: string): string => `${v}${unit ? ' ' + unit : ''}`,
  hours_since: (n: number): string => `${n} hours`,
};

/**
 * Resolve the numeric value for a button metric for one event type, or null
 * when there's nothing to show. Shared by both cards (main + button) so the
 * per-type lookup can't drift between them — each card formats the returned
 * value in its own style.
 *
 * Values are read from the timeline sensor's per-type maps (`daily_counts`,
 * `days_since`, `last_event_ts`), which cover every event type (built-in and
 * custom), with backward-compatible fallbacks to the older dedicated sensors
 * and `last_<type>_ts` attribute.
 *
 * Returned units by metric:
 *   daily_count → count today (int)
 *   days_since  → whole days since most recent event (floored int)
 *   last_value  → most recent weight in the display unit (weight type only)
 *   hours_since → whole hours since most recent event (int)
 */
export function resolveMetricValue(
  hass: HomeAssistant,
  ent: DogEntities,
  dog: string,
  eventType: string,
  metric: string,
  weightUnit: string,
  registry: Registry,
): number | null {
  const dailyCounts = (stateAttr(hass, ent.timeline, 'daily_counts') as Record<string, number> | null) || {};
  const daysSinceMap = (stateAttr(hass, ent.timeline, 'days_since') as Record<string, number> | null) || {};
  const lastEventTs = (stateAttr(hass, ent.timeline, 'last_event_ts') as Record<string, string> | null) || {};

  if (metric === 'daily_count') {
    if (typeof dailyCounts[eventType] === 'number') return dailyCounts[eventType];
    // Backward-compat: older backends only expose dedicated pee/poop sensors.
    if (eventType === 'pee') return stateNum(hass, ent.pee_count);
    if (eventType === 'poop') return stateNum(hass, ent.poop_count);
    return null;
  }
  if (metric === 'days_since') {
    const d = daysSinceMap[eventType];
    if (typeof d === 'number') return Math.floor(d);
    // Backward-compat: match the dedicated days-since sensor by friendly name.
    const meta = getMeta(eventType, registry);
    const daysLabel = `days since ${meta.label.toLowerCase()}`;
    for (const [, st] of Object.entries(hass.states)) {
      if (st.attributes?.dog?.toLowerCase() === dog?.toLowerCase() &&
          (st.attributes?.friendly_name as string | undefined)?.toLowerCase().endsWith(daysLabel)) {
        const daysVal = parseFloat(st.state);
        if (!isNaN(daysVal)) return Math.floor(daysVal);
      }
    }
    return null;
  }
  if (metric === 'last_value') {
    // last_value is sourced from the weight sensor, which is weight-specific —
    // only the weight button may show it, else every last_value button would
    // borrow the dog's weight.
    if (eventType === 'weight') return toDisplayWeight(stateNum(hass, ent.weight), weightUnit);
    return null;
  }
  if (metric === 'hours_since') {
    const lastTs = lastEventTs[eventType]
      || (stateAttr(hass, ent.timeline, 'last_' + eventType + '_ts') as string | null);
    if (lastTs) {
      const hrs = Math.floor((Date.now() - new Date(lastTs).getTime()) / 3600000);
      if (hrs >= 0) return hrs;
    }
    return null;
  }
  return null;
}