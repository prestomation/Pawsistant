/**
 * What the confirmation dialog says for each delete. Pure, so tests read the texts
 * without a DOM. Each text names the item, says what goes with it, and gives the
 * button the name of the action.
 */

import { T } from './i18n';
import type { ConfirmContent } from './confirm-dialog';

/** The lines of a body, with the empty ones left out. */
function lines(...parts: (string | undefined | null | false)[]): string {
  return parts.filter(Boolean).join('\n');
}

/** A date and time for the dialog, or '' when the time is missing or not a date. */
function formatWhen(iso: string, lang?: string): string {
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return '';
  return d.toLocaleString(lang || undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

/** Delete 1 log entry. */
export function eventDeleteText(label: string, iso: string, note: string, lang?: string): ConfirmContent {
  const when = formatWhen(iso, lang);
  return {
    title: T('confirm.event_title', { type: label }),
    body: lines(when ? `${label} · ${when}` : label, note, T('confirm.cannot_undo')),
    confirmLabel: T('confirm.event_confirm'),
  };
}

/** Delete an event type. The entries stay. A supply link goes with the type. */
export function eventTypeDeleteText(name: string, supplyName?: string): ConfirmContent {
  return {
    title: T('confirm.type_title', { name }),
    body: lines(
      T('confirm.type_kept'),
      supplyName && T('confirm.type_supply', { supply: supplyName }),
      T('confirm.cannot_undo'),
    ),
    confirmLabel: T('confirm.type_confirm'),
  };
}

/** Stop using a supply on an event type. */
export function supplyUnlinkText(typeName: string, supplyName: string): ConfirmContent {
  return {
    title: T('confirm.unlink_title', { supply: supplyName }),
    body: T('confirm.unlink_body', { type: typeName }),
    confirmLabel: T('confirm.unlink_confirm'),
  };
}
