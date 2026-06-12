/**
 * Pawsistant Card — Shared timeline rendering helpers
 *
 * Pure functions + CSS shared between the big card's timeline and the
 * button card's event log popup. No card-instance coupling.
 */

import type { EventMeta, Registry, TimelineEvent } from './types';
import { getMeta, FALLBACK_EVENT_META } from './registry';
import { _escapeHTML } from './utils';
import { T } from './i18n';

/** Localized label for DISPLAY only. Built-in event types are translated;
 *  custom types keep their user-defined name. Never use this for the
 *  days_since sensor friendly_name match — that must stay the English label. */
export function displayLabel(type: string, meta: EventMeta): string {
  if (type in FALLBACK_EVENT_META) {
    return T(`eventtype.${type}` as Parameters<typeof T>[0]);
  }
  return meta.label;
}

/** Generate HTML for a batch of events, including day headers.
 *  `lastDate` is the date of the previously rendered row (or null) so
 *  appended batches don't repeat the day header for a continuing date. */
export function buildEventRowsHTML(
  events: TimelineEvent[],
  registry: Registry,
  lastDate: string | null,
): { html: string; lastDate: string | null } {
  let html = '';
  let currentDate = lastDate;
  for (const ev of events) {
    const meta = getMeta(ev.type, registry);
    const evDate = ev.date || '';
    if (evDate !== currentDate) {
      const label = evDate || ev.day || '';
      html += `<div class="day-header">${_escapeHTML(label)}</div>`;
      currentDate = evDate;
    }
    const noteHTML = ev.note
      ? `<span class="event-note" title="${_escapeHTML(ev.note)}">${_escapeHTML(ev.note)}</span>`
      : '';
    const delAriaLabel = T('timeline.aria.delete_event', { type: _escapeHTML(ev.type), time: _escapeHTML(ev.time) });
    const editAriaLabel = T('timeline.aria.edit_event', { type: _escapeHTML(ev.type), time: _escapeHTML(ev.time) });
    html += `
        <div class="event-row" data-id="${_escapeHTML(ev.event_id)}" data-type="${_escapeHTML(ev.type)}" data-timestamp="${_escapeHTML(ev.iso || '')}" data-note="${_escapeHTML(ev.note || '')}" data-value="${ev.value !== undefined && ev.value !== null ? ev.value : ''}"  >
          <span class="event-emoji">${meta.emoji}</span>
          <span class="event-time">${_escapeHTML(ev.time)}</span>
          <span class="event-type">${_escapeHTML(displayLabel(ev.type, meta))}</span>
          ${noteHTML}
          <button class="edit-btn" data-id="${_escapeHTML(ev.event_id)}"
            aria-label="${editAriaLabel}" title="${T('timeline.aria.edit_event_title')}">✏️</button>
          <button class="delete-btn" data-id="${_escapeHTML(ev.event_id)}"
            aria-label="${delAriaLabel}" title="${T('timeline.aria.delete_event_title')}">🗑️</button>
        </div>
      `;
  }
  return { html, lastDate: currentDate };
}

/** Timeline list CSS (rows, day headers, load-more) for standalone use.
 *  Mirrors the big card's inline timeline styles, minus the 380px
 *  max-height — the popup dialog controls its own height. */
export const TIMELINE_STYLES = `
  .timeline-body {
    padding: 0 4px 8px;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .day-header {
    font-size: 10px;
    font-weight: 700;
    color: var(--secondary-text-color);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 4px 8px 2px;
    margin-top: 2px;
  }
  .event-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 6px;
    border-radius: 6px;
    transition: background 0.15s;
  }
  .event-row:hover { background: var(--secondary-background-color, #f5f5f5); }
  .event-emoji { font-size: 15px; flex-shrink: 0; width: 20px; text-align: center; }
  .event-time { font-size: 11px; color: var(--secondary-text-color); white-space: nowrap; flex-shrink: 0; min-width: 58px; }
  .event-type { font-size: 12px; font-weight: 500; color: var(--primary-text-color); flex-shrink: 0; }
  .event-note { font-size: 12px; color: var(--secondary-text-color); flex: 1; font-style: italic; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .edit-btn {
    background: none;
    border: none;
    cursor: pointer;
    opacity: 0;
    font-size: 12px;
    padding: 8px;
    border-radius: 4px;
    min-width: 36px;
    min-height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: opacity 0.15s, background 0.15s;
    flex-shrink: 0;
  }
  .event-row:hover .edit-btn, .event-row:focus-within .edit-btn { opacity: 0.5; }
  .edit-btn:hover { opacity: 1 !important; background: color-mix(in srgb, var(--primary-color, #03a9f4) 12%, transparent); }
  .delete-btn {
    background: none;
    border: none;
    cursor: pointer;
    opacity: 0.4;
    font-size: 14px;
    padding: 10px;
    border-radius: 4px;
    min-width: 44px;
    min-height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: opacity 0.15s, background 0.15s;
    flex-shrink: 0;
    margin-left: auto;
  }
  .delete-btn:hover { opacity: 1; background: color-mix(in srgb, var(--error-color, #ef5350) 12%, transparent); }
  .delete-btn.confirm-pending {
    opacity: 1;
    color: var(--error-color, #ef5350);
    background: color-mix(in srgb, var(--error-color, #ef5350) 15%, transparent);
    font-size: 11px;
  }
  .empty {
    text-align: center;
    padding: 24px;
    color: var(--secondary-text-color);
    font-size: 14px;
  }
  .load-more-btn {
    display: block;
    width: calc(100% - 32px);
    margin: 8px 16px 12px;
    padding: 10px;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 8px;
    background: transparent;
    color: var(--secondary-text-color);
    font-size: 13px;
    cursor: pointer;
    transition: background 0.15s;
  }
  .load-more-btn:hover { background: var(--secondary-background-color, #f5f5f5); }
`;

/** Inject timeline CSS into a root (ShadowRoot or element), deduplicated. */
export function ensureTimelineStyles(root: ShadowRoot | HTMLElement): void {
  if (root.querySelector('[data-pawsistant-timeline]')) return;
  const style = document.createElement('style');
  style.setAttribute('data-pawsistant-timeline', '');
  style.textContent = TIMELINE_STYLES;
  root.appendChild(style);
}
