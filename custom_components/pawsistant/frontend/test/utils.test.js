/**
 * Pawsistant Card — Utils module tests
 */
import { describe, it, expect } from 'vitest';
import { slugify, findEntitiesByDog, stateNum, stateStr, stateAttr, buildHash, _escapeHTML } from '../src/utils.js';

describe('slugify', () => {
  it('lowercases and replaces non-alphanum with underscores', () => {
    expect(slugify('Sharky')).toBe('sharky');
    expect(slugify('Mr. Fluff')).toBe('mr_fluff');
    expect(slugify('O\'Malley')).toBe('o_malley');
  });

  it('strips leading/trailing underscores', () => {
    expect(slugify('  Dog  ')).toBe('dog');
  });

  it('handles non-ASCII (accented) characters', () => {
    expect(slugify('Röy')).toBe('r_y');
  });
});

describe('findEntitiesByDog', () => {
  it('returns fallback slug-based IDs when hass is null', () => {
    const result = findEntitiesByDog(null, 'Sharky');
    expect(result.timeline).toBe('sensor.sharky_recent_timeline');
    expect(result.pee_count).toBe('sensor.sharky_daily_pee_count');
  });

  it('resolves entities by attributes.dog match', () => {
    const hass = {
      states: {
        'sensor.custom_entity_1': {
          attributes: { dog: 'Sharky', friendly_name: 'Sharky Recent Timeline' },
        },
      },
    };
    const result = findEntitiesByDog(hass, 'Sharky');
    expect(result.timeline).toBe('sensor.custom_entity_1');
  });

  it('is case-insensitive', () => {
    const hass = {
      states: {
        'sensor.dog_timeline': {
          attributes: { dog: 'ShARKY', friendly_name: 'ShARKY Recent Timeline' },
        },
      },
    };
    const result = findEntitiesByDog(hass, 'sharky');
    expect(result.timeline).toBe('sensor.dog_timeline');
  });
});

describe('_escapeHTML', () => {
  it('escapes HTML special characters', () => {
    expect(_escapeHTML('<script>alert("xss")</script>')).toBe('&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;');
  });

  it('escapes ampersands', () => {
    expect(_escapeHTML('a & b')).toBe('a &amp; b');
  });
});

describe('stateNum / stateStr / stateAttr', () => {
  const hass = {
    states: {
      'sensor.temp': { state: '72.5', attributes: { unit: '°F', friendly_name: 'Temp' } },
      'sensor.unavailable': { state: 'unavailable', attributes: {} },
      'sensor.unknown': { state: 'unknown', attributes: {} },
    },
  };

  it('stateNum returns float from state', () => {
    expect(stateNum(hass, 'sensor.temp')).toBe(72.5);
  });

  it('stateNum returns null for missing entity', () => {
    expect(stateNum(hass, 'sensor.nonexistent')).toBeNull();
  });

  it('stateStr returns state string', () => {
    expect(stateStr(hass, 'sensor.temp')).toBe('72.5');
  });

  it('stateStr returns null for unavailable/unknown', () => {
    expect(stateStr(hass, 'sensor.unavailable')).toBeNull();
    expect(stateStr(hass, 'sensor.unknown')).toBeNull();
  });

  it('stateAttr returns attribute value', () => {
    expect(stateAttr(hass, 'sensor.temp', 'unit')).toBe('°F');
  });

  it('stateAttr returns null for missing attribute', () => {
    expect(stateAttr(hass, 'sensor.temp', 'nonexistent')).toBeNull();
  });
});

describe('buildHash', () => {
  it('returns a deterministic hash string', () => {
    const hass = {
      states: {
        'sensor.sharky_recent_timeline': {
          state: '2024-01-01',
          attributes: { dog: 'Sharky', events: [], event_types: {}, button_metrics: {} },
        },
      },
    };
    const h1 = buildHash(hass, { dog: 'Sharky' });
    const h2 = buildHash(hass, { dog: 'Sharky' });
    expect(h1).toBe(h2);
    expect(typeof h1).toBe('string');
    expect(h1.length).toBeGreaterThan(0);
  });
});