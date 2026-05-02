/**
 * Unit tests for pawsistant-card.js core logic.
 *
 * These test the pure functions extracted from:
 *   custom_components/pawsistant/frontend/pawsistant-card.js
 *
 * Keep these functions in sync with the card source.
 * Run with: npx vitest
 */

// ── FALLBACK_EVENT_META ──────────────────────────────────────────────────────
// Source: pawsistant-card.js line ~20
const FALLBACK_EVENT_META = {
  poop:     { emoji: '💩', label: 'Poop',     color: 'var(--warning-color, #FF8A65)' },
  pee:      { emoji: '💧', label: 'Pee',      color: 'var(--info-color, #4FC3F7)' },
  medicine: { emoji: '💊', label: 'Medicine', color: 'var(--error-color, #EF5350)' },
  sick:     { emoji: '🤒', label: 'Sick',     color: 'var(--error-color, #EF5350)' },
  food:     { emoji: '🍖', label: 'Food',     color: 'var(--warning-color, #FF8A65)' },
  treat:    { emoji: '🍪', label: 'Treat',    color: 'var(--warning-color, #FFCA28)' },
  walk:     { emoji: '🦮', label: 'Walk',     color: 'var(--success-color, #66BB6A)' },
  water:    { emoji: '🥤', label: 'Water',    color: 'var(--info-color, #29B6F6)' },
  sleep:    { emoji: '😴', label: 'Sleep',    color: 'var(--info-color, #7E57C2)' },
  vaccine:  { emoji: '💉', label: 'Vaccine',  color: 'var(--info-color, #26A69A)' },
  training: { emoji: '🎓', label: 'Training', color: 'var(--info-color, #5C6BC0)' },
  weight:   { emoji: '⚖️',  label: 'Weight',   color: 'var(--secondary-text-color, #78909C)' },
  teeth:    { emoji: '🦷', label: 'Teeth',   color: 'var(--secondary-text-color, #B0BEC5)' },
  grooming: { emoji: '✂️',  label: 'Grooming', color: 'var(--warning-color, #EC407A)' },
};

// ── iconToEmoji ──────────────────────────────────────────────────────────────
function iconToEmoji(icon) {
  if (!icon) return undefined;
  const map = {
    'mdi:walk': '🦮', 'mdi:food-drumstick': '🍖', 'mdi:cookie': '🍪',
    'mdi:bowl': '🍽️', 'mdi:cup-water': '🥤', 'mdi:water': '💧',
    'mdi:emoticon-poop': '💩', 'mdi:pill': '💊', 'mdi:scale-bathroom': '⚖️',
    'mdi:needle': '💉', 'mdi:sleep': '😴', 'mdi:content-cut': '✂️',
    'mdi:hand-pointing-up': '🎯', 'mdi:toothbrush': '🦷', 'mdi:emoticon-sick': '🤒',
    'mdi:tag': '🏷️', 'mdi:school': '🎓',
  };
  return map[icon] || '📝';
}

// ── buildRegistry ─────────────────────────────────────────────────────────────
function buildRegistry(hass) {
  // Deep-copy of fallback so Object.assign never mutates the module constant
  const registry = {};
  for (const [k, v] of Object.entries(FALLBACK_EVENT_META)) {
    registry[k] = { ...v };
  }

  const metrics = {};

  if (hass && hass.states) {
    for (const state of Object.values(hass.states)) {
      const attrs = state.attributes || {};
      if (attrs.event_types && typeof attrs.event_types === 'object') {
        // Shallow-merge: live icon wins, but preserve fallback emoji when live icon is absent
        for (const [k, v] of Object.entries(attrs.event_types || {})) {
          if (v && typeof v === 'object') {
            registry[k] = {
              emoji:    v.icon ? iconToEmoji(v.icon) : (registry[k]?.emoji || '📝'),
              label:    v.name  || k,
              color:    v.color || registry[k]?.color || '#888',
              icon:     v.icon  || '',
            };
          }
        }
      }
      if (attrs.button_metrics && typeof attrs.button_metrics === 'object') {
        Object.assign(metrics, attrs.button_metrics);
      }
      if (Object.keys(registry).length > Object.keys(FALLBACK_EVENT_META).length ||
          Object.keys(metrics).length > 0) {
        break;
      }
    }
  }

  return { registry, metrics };
}

// ── getMeta ──────────────────────────────────────────────────────────────────
function getMeta(type, registry) {
  if (registry && registry[type]) {
    const entry = registry[type];
    const resolvedEmoji = (entry.emoji && entry.emoji !== '📝')
      ? entry.emoji
      : (entry.icon ? iconToEmoji(entry.icon) : (entry.emoji || '📝'));
    return {
      emoji: resolvedEmoji,
      label: entry.label || type,
      color: entry.color || 'var(--secondary-text-color, #888)',
      icon: entry.icon || '',
    };
  }
  const fallback = FALLBACK_EVENT_META[type];
  if (fallback) return { ...fallback, icon: '' };
  return { emoji: '📝', label: type, color: 'var(--secondary-text-color, #888)', icon: '' };
}

// ── METRIC_LABELS ───────────────────────────────────────────────────────────
const METRIC_LABELS = {
  daily_count: (n) => `${n} today`,
  days_since:  (n) => `${n} days`,
  last_value:  (v, unit) => `${v}${unit ? ' ' + unit : ''}`,
  hours_since: (n) => `${n} hours`,
};

// ════════════════════════════════════════════════════════════════════════════════
// TESTS
// ════════════════════════════════════════════════════════════════════════════════

describe('FALLBACK_EVENT_META', () => {
  test('has all 14 default event types', () => {
    expect(Object.keys(FALLBACK_EVENT_META)).toHaveLength(14);
  });

  test('walk has correct emoji and color', () => {
    expect(FALLBACK_EVENT_META.walk.emoji).toBe('🦮');
    expect(FALLBACK_EVENT_META.walk.label).toBe('Walk');
  });

  test('medicine has correct emoji and color', () => {
    expect(FALLBACK_EVENT_META.medicine.emoji).toBe('💊');
    expect(FALLBACK_EVENT_META.medicine.label).toBe('Medicine');
  });
});

describe('iconToEmoji', () => {
  test('known icons return correct emoji', () => {
    expect(iconToEmoji('mdi:walk')).toBe('🦮');
    expect(iconToEmoji('mdi:emoticon-poop')).toBe('💩');
    expect(iconToEmoji('mdi:pill')).toBe('💊');
    expect(iconToEmoji('mdi:cookie')).toBe('🍪');
    expect(iconToEmoji('mdi:bowl')).toBe('🍽️');
  });

  test('unknown icon returns 📝', () => {
    expect(iconToEmoji('mdi:unknown-xyz')).toBe('📝');
  });

  test('null/undefined/empty returns undefined (triggers fallback in getMeta)', () => {
    expect(iconToEmoji(null)).toBe(undefined);
    expect(iconToEmoji(undefined)).toBe(undefined);
    expect(iconToEmoji('')).toBe(undefined);
  });
});

describe('buildRegistry', () => {
  test('with no hass, returns deep-copied fallback', () => {
    const { registry } = buildRegistry(null);
    expect(Object.keys(registry)).toHaveLength(14);
    expect(registry.walk.emoji).toBe('🦮');
    expect(registry.poop.emoji).toBe('💩');
  });

  test('with empty hass.states, returns deep-copied fallback', () => {
    const { registry } = buildRegistry({ states: {} });
    expect(Object.keys(registry)).toHaveLength(14);
    expect(registry.walk.emoji).toBe('🦮');
  });

  test('live event_types overrides fallback values', () => {
    const hass = {
      states: {
        'sensor.sharky_recent': {
          attributes: {
            event_types: {
              walk: { name: 'Stroll', icon: 'mdi:run', color: '#FF0000' },
            },
          },
        },
      },
    };
    const { registry } = buildRegistry(hass);
    expect(registry.walk.label).toBe('Stroll');
    expect(registry.walk.color).toBe('#FF0000');
    expect(registry.walk.icon).toBe('mdi:run');
  });

  test('live event_types without icon preserves fallback emoji', () => {
    const hass = {
      states: {
        'sensor.sharky_recent': {
          attributes: {
            event_types: {
              walk: { name: 'Stroll', color: '#FF0000' }, // no icon
            },
          },
        },
      },
    };
    const { registry } = buildRegistry(hass);
    // Fallback emoji should be preserved since live has no icon
    expect(registry.walk.emoji).toBe('🦮');
    expect(registry.walk.label).toBe('Stroll');
    expect(registry.walk.color).toBe('#FF0000');
  });

  test('custom event type added to registry', () => {
    const hass = {
      states: {
        'sensor.sharky_recent': {
          attributes: {
            event_types: {
              custom_bark: { name: 'Bark', icon: 'mdi:volume-high', color: '#FF9800' },
            },
          },
        },
      },
    };
    const { registry } = buildRegistry(hass);
    expect(registry.custom_bark).toBeDefined();
    expect(registry.custom_bark.label).toBe('Bark');
    expect(registry.custom_bark.emoji).toBe('📝'); // not in iconToEmoji map
  });

  test('does not mutate FALLBACK_EVENT_META (deep-copy isolation)', () => {
    const hass = {
      states: {
        'sensor.sharky_recent': {
          attributes: {
            event_types: {
              walk: { name: 'Stroll', icon: 'mdi:run', color: '#FF0000' },
            },
          },
        },
      },
    };
    buildRegistry(hass);
    expect(FALLBACK_EVENT_META.walk.label).toBe('Walk');  // original unchanged
    expect(FALLBACK_EVENT_META.walk.emoji).toBe('🦮');   // original unchanged
    expect(FALLBACK_EVENT_META.walk.color).not.toBe('#FF0000');
  });

  test('button_metrics extracted from hass', () => {
    const hass = {
      states: {
        'sensor.sharky_recent': {
          attributes: {
            button_metrics: { walk: 'days_since', medicine: 'days_since' },
          },
        },
      },
    };
    const { metrics } = buildRegistry(hass);
    expect(metrics.walk).toBe('days_since');
    expect(metrics.medicine).toBe('days_since');
  });
});

describe('getMeta', () => {
  test('returns fallback for known type with no live override', () => {
    // FALLBACK_EVENT_META.walk has emoji='🦮' (no icon field)
    // entry.emoji='🦮', entry.icon=undefined
    // resolvedEmoji: entry.emoji='🦮' !== '📝' → use entry.emoji = '🦮'
    const meta = getMeta('walk', FALLBACK_EVENT_META);
    expect(meta.label).toBe('Walk');
    expect(meta.emoji).toBe('🦮');  // fallback emoji preserved
  });

  test('returns live registry values when available', () => {
    // liveRegistry entry: emoji='🏃', icon='mdi:run'
    // iconToEmoji('mdi:run')='📝' (not in map), so resolvedEmoji falls back to entry.emoji='🏃'
    const liveRegistry = {
      walk: { emoji: '🏃', label: 'Stroll', color: '#FF0000', icon: 'mdi:run' },
    };
    const meta = getMeta('walk', liveRegistry);
    expect(meta.label).toBe('Stroll');
    expect(meta.emoji).toBe('🏃');  // icon maps to 📝, so fallback emoji is preserved
    expect(meta.color).toBe('#FF0000');
    expect(meta.icon).toBe('mdi:run');
  });

  test('icon with no emoji map entry falls back to 📝', () => {
    // When buildRegistry processes an unmapped icon, it sets emoji='📝' in the registry
    // getMeta should then use that pre-resolved '📝'
    const liveRegistry = {
      walk: { emoji: '📝', label: 'Stroll', color: '#FF0000', icon: 'mdi:some-new-icon' },
    };
    const meta = getMeta('walk', liveRegistry);
    expect(meta.emoji).toBe('📝');
  });

  test('buildRegistry + getMeta chain: unmapped icon stays as 📝', () => {
    // Real chain: buildRegistry processes an unmapped icon → getMeta reads the registry
    const hass = {
      states: {
        'sensor.test': {
          attributes: {
            event_types: {
              walk: { name: 'Stroll', icon: 'mdi:completely-unknown-icon', color: '#FF0000' },
            },
          },
        },
      },
    };
    const { registry } = buildRegistry(hass);
    const meta = getMeta('walk', registry);
    // buildRegistry resolved the unmapped icon to 📝, getMeta preserves it
    expect(meta.emoji).toBe('📝');
    expect(meta.label).toBe('Stroll');
    expect(meta.icon).toBe('mdi:completely-unknown-icon');
  });

  test('unknown type returns generic fallback', () => {
    const meta = getMeta('custom_unknown', {});
    expect(meta.emoji).toBe('📝');
    expect(meta.label).toBe('custom_unknown');
  });

  test('icon: undefined falls back to 📝 emoji', () => {
    const liveRegistry = {
      walk: { label: 'Stroll', color: '#FF0000', icon: '' },
    };
    const meta = getMeta('walk', liveRegistry);
    expect(meta.emoji).toBe('📝');
    expect(meta.icon).toBe('');
  });
});

describe('METRIC_LABELS', () => {
  test('daily_count formats correctly', () => {
    expect(METRIC_LABELS.daily_count(3)).toBe('3 today');
    expect(METRIC_LABELS.daily_count(0)).toBe('0 today');
    expect(METRIC_LABELS.daily_count(1)).toBe('1 today');
  });

  test('days_since formats correctly', () => {
    expect(METRIC_LABELS.days_since(2)).toBe('2 days');
    expect(METRIC_LABELS.days_since(0)).toBe('0 days');
  });

  test('last_value formats with and without unit', () => {
    expect(METRIC_LABELS.last_value(28.5, 'lbs')).toBe('28.5 lbs');
    expect(METRIC_LABELS.last_value(28.5, '')).toBe('28.5');
    expect(METRIC_LABELS.last_value(28.5)).toBe('28.5');
    expect(METRIC_LABELS.last_value(25, 'kg')).toBe('25 kg');
  });

  test('hours_since formats correctly', () => {
    expect(METRIC_LABELS.hours_since(6)).toBe('6 hours');
  });
});

// ════════════════════════════════════════════════════════════════════════════════
// CARD METHOD REFERENCE INTEGRITY TEST
// ════════════════════════════════════════════════════════════════════════════════

const fs = require('fs');
const path = require('path');

describe('Card source method references', () => {
  let cardSource;

  beforeAll(() => {
    const srcPath = path.resolve(__dirname, '../../custom_components/pawsistant/frontend/src/index.ts');
    cardSource = fs.readFileSync(srcPath, 'utf8');
  });

  // Extract all this._method() calls from the source and verify they're defined
  test('all this._method() calls in source have corresponding method definitions', () => {
    // Find all this._foo() calls (invocations via this.)
    const methodCalls = [...cardSource.matchAll(/this\.(_\w+)\s*\(/g)].map(m => m[1]);
    const uniqueCalls = [...new Set(methodCalls)];

    // Find method definitions: start of line + optional async + _foo(
    // Also match class field assignments like _foo = withCooldown(...)
    const defRegex = /(?:^|\n)\s*(?:async\s+)?(_\w+)\s*\(/g;
    const fieldRegex = /(?:^|\n)\s+(_\w+)\s*=\s/g;
    const methodDefs = [...cardSource.matchAll(defRegex)].map(m => m[1]);
    const fieldDefs = [...cardSource.matchAll(fieldRegex)].map(m => m[1]);
    const uniqueDefs = [...new Set([...methodDefs, ...fieldDefs])];

    const missing = uniqueCalls.filter(m => !uniqueDefs.includes(m));
    if (missing.length > 0) {
      throw new Error(
        'Methods called but not defined in card source:\n' +
        missing.map(m => '  this.' + m + '()').join('\n') + '\n' +
        'Available methods: ' + uniqueDefs.sort().join(', ')
      );
    }
  });
});
