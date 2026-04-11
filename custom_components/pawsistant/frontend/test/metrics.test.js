/**
 * Pawsistant Card — Metrics module tests
 */
import { describe, it, expect } from 'vitest';
import { METRIC_LABELS } from '../src/metrics.js';

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