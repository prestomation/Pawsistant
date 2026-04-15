/**
 * Pawsistant Card — Weight unit conversion tests
 *
 * Two bugs on the read path (write path was already correct):
 *
 *   Bug 1 — Button badge: `(${w} ${weightUnit})` uses raw lbs value.
 *            When unit=kg and stored value=80lbs, badge shows "(80 kg)"
 *            instead of "(36.3 kg)".
 *
 *   Bug 2 — Form pre-fill: weight input is pre-filled with raw lbs value.
 *            When unit=kg and last weight=80lbs, form shows 80 in a kg field.
 *
 * Fix: extract toDisplayWeight(lbs, unit) into utils.js and call it at both sites.
 */

import { describe, it, expect } from 'vitest';
import { toDisplayWeight } from '../src/utils.js';

describe('toDisplayWeight', () => {
  it('returns lbs unchanged when unit is lbs', () => {
    expect(toDisplayWeight(80.0, 'lbs')).toBe(80.0);
  });

  it('converts lbs to kg when unit is kg', () => {
    // 80 lbs → 36.3 kg (rounded to 1 decimal)
    expect(toDisplayWeight(80.0, 'kg')).toBeCloseTo(36.3, 0);
  });

  it('returns null for null input regardless of unit', () => {
    expect(toDisplayWeight(null, 'kg')).toBeNull();
    expect(toDisplayWeight(null, 'lbs')).toBeNull();
  });

  it('round-trips: value entered in kg → stored as lbs → displayed as kg recovers original', () => {
    // User enters 36.3 kg, submit converts to lbs: 36.3 * 2.20462 ≈ 80.0
    const storedLbs = Math.round(36.3 * 2.20462 * 10) / 10;
    expect(toDisplayWeight(storedLbs, 'kg')).toBeCloseTo(36.3, 0);
  });

  it('does not affect lbs mode for any value', () => {
    expect(toDisplayWeight(0, 'lbs')).toBe(0);
    expect(toDisplayWeight(150.5, 'lbs')).toBe(150.5);
  });
});
