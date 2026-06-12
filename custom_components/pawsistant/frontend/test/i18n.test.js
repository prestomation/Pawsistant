/**
 * Pawsistant Card — i18n module tests.
 *
 * Verifies the translation core (resolveLang / interpolate / t / tPlural) and
 * that every registered locale mirrors the English source-of-truth key set.
 */
import { describe, it, expect } from 'vitest';
import { resolveLang, interpolate, t, tPlural } from '../src/i18n/index.js';
import { LOCALES, FALLBACK_LANG } from '../src/i18n/locales.js';
import { en } from '../src/i18n/en.js';

const EN_KEYS = Object.keys(en).sort();

describe('resolveLang', () => {
  it('returns an exact match when present', () => {
    expect(resolveLang('de')).toBe('de');
    expect(resolveLang('zh-Hans')).toBe('zh-Hans');
  });

  it('falls back to the base language for region variants', () => {
    expect(resolveLang('de-DE')).toBe('de');
    expect(resolveLang('fr-CA')).toBe('fr');
  });

  it('falls back to English for unknown or empty input', () => {
    expect(resolveLang('xx')).toBe(FALLBACK_LANG);
    expect(resolveLang('')).toBe(FALLBACK_LANG);
    expect(resolveLang(null)).toBe(FALLBACK_LANG);
    expect(resolveLang(undefined)).toBe(FALLBACK_LANG);
  });
});

describe('interpolate', () => {
  it('replaces known tokens and leaves unknown ones literal', () => {
    expect(interpolate('Log {label}', { label: 'Walk' })).toBe('Log Walk');
    expect(interpolate('Hi {missing}', { other: 1 })).toBe('Hi {missing}');
  });

  it('returns the string unchanged when no vars are given', () => {
    expect(interpolate('Cancel')).toBe('Cancel');
  });

  it('coerces non-string values', () => {
    expect(interpolate('{n} today', { n: 3 })).toBe('3 today');
  });
});

describe('t', () => {
  it('translates a known key into the requested locale', () => {
    expect(t('de', 'form.cancel')).toBe('Abbrechen');
    expect(t('en', 'form.cancel')).toBe('Cancel');
  });

  it('interpolates variables', () => {
    expect(t('en', 'form.log_title', { label: 'Walk' })).toBe('Log Walk');
  });

  it('falls back to English for an unknown language', () => {
    expect(t('xx', 'form.cancel')).toBe(en['form.cancel']);
  });

  it('uses base-language resolution', () => {
    expect(t('de-DE', 'form.cancel')).toBe(t('de', 'form.cancel'));
  });
});

describe('tPlural', () => {
  it('interpolates the count and resolves a plural category', () => {
    expect(tPlural('en', 'time.min_ago', 1)).toBe('1 min ago');
    expect(tPlural('en', 'time.min_ago', 5)).toBe('5 min ago');
  });

  it('falls back to English categories for unknown languages', () => {
    expect(tPlural('xx', 'time.min_ago', 2)).toBe('2 min ago');
  });
});

describe('locale coverage', () => {
  it('includes English as the fallback language', () => {
    expect(FALLBACK_LANG).toBe('en');
    expect(LOCALES[FALLBACK_LANG]).toBeDefined();
  });

  for (const [code, dict] of Object.entries(LOCALES)) {
    it(`locale "${code}" mirrors the English key set with non-empty values`, () => {
      expect(Object.keys(dict).sort()).toEqual(EN_KEYS);
      for (const key of EN_KEYS) {
        expect(typeof dict[key]).toBe('string');
        expect(dict[key].trim().length).toBeGreaterThan(0);
      }
    });
  }
});
