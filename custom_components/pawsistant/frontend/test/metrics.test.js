/**
 * Pawsistant Card — Metrics module tests
 */
import { describe, it, expect } from 'vitest';
import { METRIC_LABELS, resolveMetricValue } from '../src/metrics.js';

describe('METRIC_LABELS', () => {
  it('has daily_count label', () => {
    expect(METRIC_LABELS.daily_count(5)).toBe('5 today');
  });

  it('has days_since label', () => {
    expect(METRIC_LABELS.days_since(3)).toBe('3 days');
  });

  it('has last_value label with unit', () => {
    expect(METRIC_LABELS.last_value(45, 'lbs')).toBe('45 lbs');
  });

  it('has last_value label without unit', () => {
    expect(METRIC_LABELS.last_value(45, '')).toBe('45');
  });

  it('has hours_since label', () => {
    expect(METRIC_LABELS.hours_since(2)).toBe('2 hours');
  });
});

describe('resolveMetricValue (shared by both cards)', () => {
  const ent = {
    timeline: 'sensor.sharky_recent_timeline',
    pee_count: 'sensor.sharky_daily_pee_count',
    poop_count: 'sensor.sharky_daily_poop_count',
    medicine_days: 'sensor.sharky_days_since_medicine',
    weight: 'sensor.sharky_weight',
  };
  const registry = {};

  function hass(timelineAttrs = {}, extra = {}) {
    return {
      states: {
        'sensor.sharky_recent_timeline': { state: 'ok', attributes: { dog: 'Sharky', friendly_name: 'Sharky Recent Timeline', ...timelineAttrs } },
        'sensor.sharky_weight': { state: '80', attributes: { dog: 'Sharky', friendly_name: 'Sharky Weight' } },
        'sensor.sharky_daily_pee_count': { state: '3', attributes: { dog: 'Sharky', friendly_name: 'Sharky Daily Pee Count' } },
        'sensor.sharky_daily_poop_count': { state: '2', attributes: { dog: 'Sharky', friendly_name: 'Sharky Daily Poop Count' } },
        ...extra,
      },
    };
  }

  it('daily_count: reads the per-type map for any type', () => {
    const h = hass({ daily_counts: { walk: 4, playtime: 1 } });
    expect(resolveMetricValue(h, ent, 'Sharky', 'walk', 'daily_count', 'lbs', registry)).toBe(4);
    expect(resolveMetricValue(h, ent, 'Sharky', 'playtime', 'daily_count', 'lbs', registry)).toBe(1);
  });

  it('daily_count: falls back to pee/poop sensors when no map (old backend)', () => {
    const h = hass();
    expect(resolveMetricValue(h, ent, 'Sharky', 'pee', 'daily_count', 'lbs', registry)).toBe(3);
    expect(resolveMetricValue(h, ent, 'Sharky', 'poop', 'daily_count', 'lbs', registry)).toBe(2);
    // No data source for a custom type without the map → null.
    expect(resolveMetricValue(h, ent, 'Sharky', 'playtime', 'daily_count', 'lbs', registry)).toBeNull();
  });

  it('days_since: floors the per-type map value', () => {
    const h = hass({ days_since: { vaccine: 12.7 } });
    expect(resolveMetricValue(h, ent, 'Sharky', 'vaccine', 'days_since', 'lbs', registry)).toBe(12);
  });

  it('days_since: clamps a negative (future-dated event) value to 0', () => {
    const h = hass({ days_since: { vaccine: -0.1 } });
    // Must not render "(-1d)".
    expect(resolveMetricValue(h, ent, 'Sharky', 'vaccine', 'days_since', 'lbs', registry)).toBe(0);
  });

  it('last_value: only the weight type returns a value (no leak)', () => {
    const h = hass();
    expect(resolveMetricValue(h, ent, 'Sharky', 'weight', 'last_value', 'lbs', registry)).toBe(80);
    expect(resolveMetricValue(h, ent, 'Sharky', 'vaccine', 'last_value', 'lbs', registry)).toBeNull();
  });

  it('last_value: converts to the display unit', () => {
    const h = hass();
    expect(resolveMetricValue(h, ent, 'Sharky', 'weight', 'last_value', 'kg', registry)).toBe(36.3);
  });

  it('hours_since: computes from the last_event_ts map', () => {
    const h = hass({ last_event_ts: { walk: new Date(Date.now() - 5 * 3600000).toISOString() } });
    expect(resolveMetricValue(h, ent, 'Sharky', 'walk', 'hours_since', 'lbs', registry)).toBe(5);
    // No timestamp for the type → null (previously the metric was always blank).
    expect(resolveMetricValue(h, ent, 'Sharky', 'food', 'hours_since', 'lbs', registry)).toBeNull();
  });
});