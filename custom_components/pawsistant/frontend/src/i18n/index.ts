/**
 * Pawsistant Card — Dependency-free i18n module.
 *
 * Inline TS dictionaries (no JSON imports). English is the source of truth and
 * the per-key fallback. Plurals use Intl.PluralRules (available in ES2020).
 */
import { en } from './en';
import { LOCALES, FALLBACK_LANG } from './locales';
import type { TranslationKey, Dict } from './en';

export type { TranslationKey, Dict };

/**
 * Resolve a (possibly null) HA language code to a key present in LOCALES.
 * Tries exact match (e.g. "zh-Hans"), then the base before "-" (e.g.
 * "de-DE" → "de"), then falls back to English.
 */
export function resolveLang(lang: string | null | undefined): string {
  if (!lang) return FALLBACK_LANG;
  if (LOCALES[lang]) return lang;
  const base = lang.split('-')[0];
  if (base && LOCALES[base]) return base;
  return FALLBACK_LANG;
}

/** Replace {token} placeholders with String(vars[token]); leave unknown tokens literal. */
export function interpolate(s: string, vars?: Record<string, unknown>): string {
  if (!vars) return s;
  return s.replace(/\{(\w+)\}/g, (match, name: string) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : match,
  );
}

/** Translate a key for a language, with per-key English fallback. Never blank. */
export function t(lang: string | null | undefined, key: TranslationKey, vars?: Record<string, unknown>): string {
  const dict = LOCALES[resolveLang(lang)] || {};
  const raw = dict[key] ?? en[key] ?? key;
  return vars ? interpolate(raw, vars) : raw;
}

/**
 * Plural-aware translation. Looks up `${baseKey}.${category}` where category is
 * derived from Intl.PluralRules, falling back to `${baseKey}.other`, then the
 * English equivalents, then the baseKey itself. Interpolates with { n, ...vars }.
 */
export function tPlural(
  lang: string | null | undefined,
  baseKey: string,
  n: number,
  vars?: Record<string, unknown>,
): string {
  const code = resolveLang(lang);
  const dict = (LOCALES[code] || {}) as Record<string, string>;
  const enDict = en as Record<string, string>;
  let cat: string;
  try {
    cat = new Intl.PluralRules(code).select(n);
  } catch {
    cat = 'other';
  }
  const raw =
    dict[`${baseKey}.${cat}`] ??
    dict[`${baseKey}.other`] ??
    enDict[`${baseKey}.${cat}`] ??
    enDict[`${baseKey}.other`] ??
    baseKey;
  return interpolate(raw, { n, ...vars });
}

/* ── Ambient active-language helpers ──────────────────────────────────────
 * The card renders synchronously and reads the language from `hass`. To avoid
 * threading `lang` through every render helper and standalone form function,
 * the card sets the active language once per hass update (see set hass), and
 * call sites use the ambient T()/TP() wrappers. The explicit t()/tPlural()
 * API above remains the source of truth (and is what the unit tests exercise).
 */
let _activeLang: string | null = FALLBACK_LANG;

/** Set the language used by the ambient T()/TP() helpers. */
export function setLang(lang: string | null | undefined): void {
  _activeLang = lang ?? FALLBACK_LANG;
}

/** The currently active ambient language. */
export function getLang(): string | null {
  return _activeLang;
}

/** Translate `key` in the active language (ambient wrapper around t()). */
export function T(key: TranslationKey, vars?: Record<string, unknown>): string {
  return t(_activeLang, key, vars);
}

/** Plural-aware translate in the active language (ambient wrapper around tPlural()). */
export function TP(baseKey: string, n: number, vars?: Record<string, unknown>): string {
  return tPlural(_activeLang, baseKey, n, vars);
}
