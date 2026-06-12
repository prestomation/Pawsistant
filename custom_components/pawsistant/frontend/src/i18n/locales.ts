/**
 * Pawsistant Card — Locale registry.
 *
 * Maps Home Assistant language codes to their translation dictionaries.
 * English is the fallback language and the per-key fallback (see ./index → t).
 * Keys here must match the codes HA reports in `hass.language` (e.g. "zh-Hans",
 * "pt-BR"); resolveLang() also handles base-language fallback (e.g. "de-DE" → "de").
 */
import { en } from './en';
import { ar } from './ar';
import { de } from './de';
import { es } from './es';
import { fr } from './fr';
import { hi } from './hi';
import { it } from './it';
import { ja } from './ja';
import { ko } from './ko';
import { nl } from './nl';
import { pl } from './pl';
import { ptBR } from './pt-BR';
import { ru } from './ru';
import { sv } from './sv';
import { tr } from './tr';
import { zhHans } from './zh-Hans';
import type { Dict } from './en';

export const FALLBACK_LANG = 'en';

export const LOCALES: Record<string, Dict> = {
  en,
  ar,
  de,
  es,
  fr,
  hi,
  it,
  ja,
  ko,
  nl,
  pl,
  'pt-BR': ptBR,
  ru,
  sv,
  tr,
  'zh-Hans': zhHans,
};
