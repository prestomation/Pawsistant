/**
 * Pawsistant Card — Registry module tests
 *
 * These tests import directly from the src/ modules — no copy-paste drift.
 */
import { describe, it, expect } from 'vitest';
import {
  FALLBACK_EVENT_META, EVENT_META, DEFAULT_SHOWN_TYPES,
  buildRegistry, getMeta, iconToEmoji,
} from '../src/registry.js';

describe('FALLBACK_EVENT_META', () => {
  it('has entries for all default event types', () => {
    for (const key of DEFAULT_SHOWN_TYPES) {
      expect(FALLBACK_EVENT_META[key]).toBeDefined();
      expect(FALLBACK_EVENT_META[key].emoji).toBeTruthy();
      expect(FALLBACK_EVENT_META[key].label).toBeTruthy();
    }
  });

  it('EVENT_META is an alias for FALLBACK_EVENT_META', () => {
    expect(EVENT_META).toBe(FALLBACK_EVENT_META);
  });
});

describe('iconToEmoji', () => {
  it('maps known MDI icons to emojis', () => {
    expect(iconToEmoji('mdi:walk')).toBe('🦮');
    expect(iconToEmoji('mdi:food-drumstick')).toBe('🍖');
    expect(iconToEmoji('mdi:pill')).toBe('💊');
  });

  it('returns 📝 for unknown icons', () => {
    expect(iconToEmoji('mdi:some-new-icon')).toBe('📝');
  });

  it('returns undefined for empty/null icon', () => {
    expect(iconToEmoji('')).toBeUndefined();
    expect(iconToEmoji(null)).toBeUndefined();
    expect(iconToEmoji(undefined)).toBeUndefined();
  });
});

describe('buildRegistry', () => {
  it('returns fallback registry when hass is null', () => {
    const { registry, metrics } = buildRegistry(null);
    expect(Object.keys(registry)).toContain('poop');
    expect(Object.keys(registry)).toContain('pee');
    expect(metrics).toEqual({});
  });

  it('returns fallback registry when hass.states is empty', () => {
    const { registry } = buildRegistry({ states: {} });
    // Should still have the fallback keys
    expect(Object.keys(registry)).toContain('poop');
  });

  it('uses live event_types from sensor attributes', () => {
    const hass = {
      states: {
        'sensor.sharky_recent_timeline': {
          attributes: {
            dog: 'Sharky',
            event_types: {
              poop: { name: 'Poop', icon: 'mdi:emoticon-poop', color: '#FF8A65' },
              custom_type: { name: 'Custom', icon: 'mdi:star', color: '#FFD700' },
            },
          },
        },
      },
    };
    const { registry } = buildRegistry(hass);
    expect(registry.poop).toBeDefined();
    expect(registry.poop.label).toBe('Poop');
    expect(registry.custom_type).toBeDefined();
    expect(registry.custom_type.label).toBe('Custom');
  });

  it('ignores array event_types (legacy bug)', () => {
    const hass = {
      states: {
        'sensor.backup_automatic_backup': {
          attributes: {
            event_types: ['poop', 'pee'],  // Array, not object — should be ignored
          },
        },
      },
    };
    const { registry } = buildRegistry(hass);
    // Should fall back to defaults since no valid event_types found
    expect(Object.keys(registry)).toContain('poop');
  });

  it('extracts button_metrics from sensor attributes', () => {
    const hass = {
      states: {
        'sensor.sharky_recent_timeline': {
          attributes: {
            dog: 'Sharky',
            event_types: { poop: { name: 'Poop', icon: 'mdi:emoticon-poop' } },
            button_metrics: { poop: 'daily_count', weight: 'last_value' },
          },
        },
      },
    };
    const { metrics } = buildRegistry(hass);
    expect(metrics.poop).toBe('daily_count');
    expect(metrics.weight).toBe('last_value');
  });
  it('collects button_metrics from sensors even without event_types', () => {
    const hass = {
      states: {
        'sensor.sharky_recent_timeline': {
          attributes: {
            dog: 'Sharky',
            event_types: { poop: { name: 'Poop', icon: 'mdi:emoticon-poop' } },
          },
        },
        'sensor.sharky_daily_pee_count': {
          attributes: {
            dog: 'Sharky',
            button_metrics: { pee: 'daily_count' },
          },
        },
      },
    };
    const { registry, metrics } = buildRegistry(hass);
    expect(registry.poop).toBeDefined();
    expect(metrics.pee).toBe('daily_count');
  });
});

describe('getMeta', () => {
  it('returns fallback for known type with no registry', () => {
    const meta = getMeta('poop', null);
    expect(meta.emoji).toBe('💩');
    expect(meta.label).toBe('Poop');
    expect(meta.icon).toBe('');
  });

  it('returns entry from live registry', () => {
    const registry = {
      poop: { emoji: '💩', label: 'Poop', icon: 'mdi:emoticon-poop', color: '#FF8A65' },
    };
    const meta = getMeta('poop', registry);
    expect(meta.emoji).toBe('💩');
    expect(meta.icon).toBe('mdi:emoticon-poop');
  });

  it('returns generic entry for unknown type', () => {
    const meta = getMeta('unknown_type', null);
    expect(meta.emoji).toBe('📝');
    expect(meta.label).toBe('unknown_type');
  });
});