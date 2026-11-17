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

/** A row that is not saved yet: "Saving…", or "Not saved yet" with Retry and Discard. */
function pendingRowHTML(ev: TimelineEvent, meta: EventMeta, noteHTML: string, label: string): string {
  const { id, state } = ev.pending!;
  const pid = _escapeHTML(id);
  const failed = state === 'failed';
  const status = failed
    ? `<span class="pending-status" role="alert">⚠ ${T('pending.failed')}</span>`
    : `<span class="pending-status" role="status"><span class="pending-spin" aria-hidden="true"></span>${T('pending.saving')}</span>`;
  const what = _escapeHTML(`${label} ${ev.time}`);
  const actions = failed
    ? `<span class="pending-actions">
        <button class="pending-btn retry-btn" data-pending-id="${pid}" aria-label="${T('pending.retry')}: ${what}">${T('pending.retry')}</button>
        <button class="pending-btn discard-btn" data-pending-id="${pid}" aria-label="${T('pending.discard')}: ${what}">${T('pending.discard')}</button>
      </span>`
    : '';
  return `
        <div class="event-row ${failed ? 'failed' : 'pending'}" data-pending-id="${pid}" data-type="${_escapeHTML(ev.type)}" data-timestamp="${_escapeHTML(ev.iso || '')}">
          <span class="event-emoji">${meta.emoji}</span>
          <span class="event-time">${_escapeHTML(ev.time)}</span>
          <span class="event-type">${_escapeHTML(label)}</span>
          ${noteHTML}
          ${status}
          ${actions}
        </div>
      `;
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
    if (ev.pending) {
      html += pendingRowHTML(ev, meta, noteHTML, displayLabel(ev.type, meta));
      continue;
    }
    const delAriaLabel = T('timeline.aria.delete_event', { type: _escapeHTML(ev.type), time: _escapeHTML(ev.time) });
    const editAriaLabel = T('timeline.aria.edit_event', { type: _escapeHTML(ev.type), time: _escapeHTML(ev.time) });
    html += `
        <div class="event-row" data-id="${_escapeHTML(ev.event_id)}" data-type="${_escapeHTML(ev.type)}" data-timestamp="${_escapeHTML(ev.iso || '')}" data-note="${_escapeHTML(ev.note || '')}" data-value="${ev.value !== undefined && ev.value !== null ? ev.value : ''}"  >
          <span class="event-emoji">${meta.emoji}</span>
          <span class="event-time">${_escapeHTML(ev.time)}</span>
          <span class="event-type">${_escapeHTML(displayLabel(ev.type, meta))}</span>
          ${noteHTML}
          ${ev.event_id ? `<button class="edit-btn" data-id="${_escapeHTML(ev.event_id)}"
            aria-label="${editAriaLabel}" title="${T('timeline.aria.edit_event_title')}">✏️</button>
          <button class="delete-btn" data-id="${_escapeHTML(ev.event_id)}"
            aria-label="${delAriaLabel}" title="${T('timeline.aria.delete_event_title')}">🗑️</button>` : ''}
        </div>
      `;
  }
  return { html, lastDate: currentDate };
}

/** CSS of the pending rows. Only the emoji and the row background fade: the text keeps its colors. */
export const PENDING_STYLES = `
  .event-row.pending, .event-row.failed { flex-wrap: wrap; }
  .event-row.pending {
    background: color-mix(in srgb, var(--primary-color, #03a9f4) 8%, transparent);
    outline: 1px dashed var(--divider-color, #e0e0e0);
    outline-offset: -1px;
  }
  .event-row.failed { background: color-mix(in srgb, var(--error-color, #db4437) 12%, transparent); }
  .event-row.pending .event-emoji, .event-row.failed .event-emoji { opacity: 0.45; filter: grayscale(1); }
  /* The tint lowers the contrast of the secondary text, so these rows use the primary text color. */
  .event-row.pending .event-time, .event-row.failed .event-time,
  .event-row.pending .event-note, .event-row.failed .event-note { color: var(--primary-text-color); }
  .pending-status {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    color: var(--primary-text-color);
  }
  .event-row.failed .pending-status {
    font-weight: 600;
    color: color-mix(in srgb, var(--error-color, #db4437) 55%, var(--primary-text-color, #212121));
  }
  .pending-spin {
    width: 11px;
    height: 11px;
    border: 2px solid var(--divider-color, #e0e0e0);
    border-top-color: var(--primary-color, #03a9f4);
    border-radius: 50%;
    animation: pending-spin 1s linear infinite;
  }
  @keyframes pending-spin { to { transform: rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) {
    .pending-spin { animation: none; border-top-color: var(--divider-color, #e0e0e0); border-right-color: var(--primary-color, #03a9f4); }
  }
  .pending-actions { display: flex; gap: 8px; width: 100%; padding: 2px 0 4px 26px; }
  .pending-btn {
    min-height: 44px;
    padding: 0 16px;
    border-radius: 8px;
    border: 1px solid var(--divider-color, #e0e0e0);
    background: transparent;
    color: var(--primary-text-color);
    font-size: 12.5px;
    font-weight: 600;
    cursor: pointer;
  }
  .pending-btn.retry-btn { border-color: var(--primary-color, #03a9f4); }
`;

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
  ${PENDING_STYLES}
`;

/** Inject timeline CSS into a root (ShadowRoot or element), deduplicated. */
export function ensureTimelineStyles(root: ShadowRoot | HTMLElement): void {
  if (root.querySelector('[data-pawsistant-timeline]')) return;
  const style = document.createElement('style');
  style.setAttribute('data-pawsistant-timeline', '');
  style.textContent = TIMELINE_STYLES;
  root.appendChild(style);
}
