/**
 * Pawsistant Card — Standalone event log timeline
 *
 * Self-contained timeline (fetch, pagination, edit, delete) that renders
 * into any container. Follows the standalone-forms pattern — not tied to
 * a card instance. Used by the button card's event log popup.
 */

import type { HomeAssistant, Registry, TimelineEvent } from './types';
import { getMeta } from './registry';
import { deleteEvent } from './services';
import { buildEventRowsHTML, ensureTimelineStyles } from './timeline-render';
import { openEditForm } from './standalone-forms';
import { T } from './i18n';

export interface EventLogOptions {
  /** Scrollable list container (gets the .timeline-body content). */
  container: HTMLElement;
  /** Where the edit form renders (typically above the list). */
  formSlot: HTMLElement;
  hass: HomeAssistant;
  dogId: string;
  registry: Registry;
  weightUnit: 'kg' | 'lbs';
  pageSize?: number;
}

export interface EventLogHandle {
  /** Re-fetch page 0 and re-render the list. */
  refresh: () => Promise<void>;
  /** Disconnect observers, clear timers, remove listeners and DOM. */
  cleanup: () => void;
}

interface EventsResult {
  events: TimelineEvent[];
  total: number;
}

export function createEventLog(opts: EventLogOptions): EventLogHandle {
  const { container, formSlot, hass, dogId, registry, weightUnit } = opts;
  const pageSize = opts.pageSize || 50;

  let events: TimelineEvent[] = [];
  let total = 0;
  let loading = false;
  let lastDate: string | null = null;
  let disposed = false;
  let editing = false;
  let observer: IntersectionObserver | null = null;
  let timers: ReturnType<typeof setTimeout>[] = [];
  const deleteConfirm = new Map<string, ReturnType<typeof setTimeout>>();

  const rootNode = container.getRootNode();
  ensureTimelineStyles(rootNode instanceof ShadowRoot ? rootNode : document.head);

  function setTimer(fn: () => void, delay: number): ReturnType<typeof setTimeout> {
    const id = setTimeout(() => {
      timers = timers.filter(t => t !== id);
      fn();
    }, delay);
    timers.push(id);
    return id;
  }

  async function fetchPage(offset: number): Promise<EventsResult | null> {
    if (!hass.connection) return null;
    try {
      return await hass.connection.sendMessagePromise({
        type: 'pawsistant/get_events',
        dog_id: dogId,
        offset,
        limit: pageSize,
      }) as EventsResult;
    } catch (err) {
      console.warn('[pawsistant-button-card] Failed to fetch event log:', err);
      return null;
    }
  }

  function loadMoreLabel(): string {
    return T('timeline.load_more', { shown: events.length, total });
  }

  function renderList(): void {
    if (events.length === 0) {
      container.innerHTML = `<div class="empty">${T('timeline.empty_no_events')}</div>`;
      return;
    }
    const built = buildEventRowsHTML(events, registry, null);
    lastDate = built.lastDate;
    const loadMoreHTML = total > events.length
      ? `<button class="load-more-btn" id="pbc-load-more-btn">${loadMoreLabel()}</button>`
      : '';
    container.innerHTML = built.html + loadMoreHTML;
    setupObserver();
  }

  async function refresh(): Promise<void> {
    if (disposed || loading) return;
    loading = true;
    if (events.length === 0) {
      container.innerHTML = `<div class="empty">${T('timeline.loading')}</div>`;
    }
    const result = await fetchPage(0);
    loading = false;
    if (disposed) return;
    if (!result) {
      container.innerHTML = `<div class="empty">${T('timeline.empty_no_events')}</div>`;
      return;
    }
    events = result.events || [];
    total = result.total || 0;
    renderList();
  }

  async function loadMore(): Promise<void> {
    if (disposed || loading || events.length >= total) return;
    loading = true;
    const btn = container.querySelector('#pbc-load-more-btn');
    if (btn) btn.textContent = T('timeline.loading_short');
    const result = await fetchPage(events.length);
    loading = false;
    if (disposed) return;
    if (!result) {
      if (btn) btn.textContent = loadMoreLabel();
      return;
    }
    const newEvents = result.events || [];
    events = [...events, ...newEvents];
    total = result.total || 0;
    if (newEvents.length > 0 && btn) {
      const built = buildEventRowsHTML(newEvents, registry, lastDate);
      lastDate = built.lastDate;
      btn.insertAdjacentHTML('beforebegin', built.html);
    }
    if (events.length >= total) {
      btn?.remove();
      if (observer) {
        observer.disconnect();
        observer = null;
      }
    } else if (btn) {
      btn.textContent = loadMoreLabel();
    }
  }

  function setupObserver(): void {
    if (observer) {
      observer.disconnect();
      observer = null;
    }
    // jsdom (unit tests) has no IntersectionObserver — click fallback still works
    if (typeof IntersectionObserver === 'undefined') return;
    const btn = container.querySelector('#pbc-load-more-btn');
    if (!btn) return;
    observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && !loading) {
        loadMore();
      }
    }, { root: container, rootMargin: '100px' });
    observer.observe(btn);
  }

  function handleDelete(btn: HTMLButtonElement): void {
    const eventId = btn.dataset.id;
    if (!eventId) return;

    if (deleteConfirm.has(eventId)) {
      // Second tap — confirm and delete
      clearTimeout(deleteConfirm.get(eventId)!);
      deleteConfirm.delete(eventId);
      btn.classList.remove('confirm-pending');
      btn.textContent = '🗑️';
      if (btn.dataset.pending) return;
      btn.dataset.pending = '1';
      deleteEvent(hass, eventId)
        .then(() => {
          delete btn.dataset.pending;
          refresh();
        })
        .catch(err => {
          console.error('[pawsistant-button-card] delete_event failed:', err);
          delete btn.dataset.pending;
          const row = btn.closest<HTMLElement>('.event-row');
          if (row) {
            row.style.background = 'color-mix(in srgb, var(--error-color, #ef5350) 15%, transparent)';
            setTimer(() => { row.style.background = ''; }, 2000);
          }
        });
    } else {
      // First tap — show confirm state
      btn.classList.add('confirm-pending');
      btn.textContent = T('timeline.delete_confirm');
      const revertId = setTimer(() => {
        deleteConfirm.delete(eventId);
        btn.classList.remove('confirm-pending');
        btn.textContent = '🗑️';
      }, 3000);
      deleteConfirm.set(eventId, revertId);
    }
  }

  async function handleEdit(btn: HTMLButtonElement): Promise<void> {
    if (editing) return;
    const row = btn.closest<HTMLElement>('.event-row');
    if (!row) return;
    const eventType = row.dataset.type || '';
    const eventId = row.dataset.id || '';
    if (!eventId) return;

    editing = true;
    const result = await openEditForm({
      container: formSlot,
      hass,
      meta: getMeta(eventType, registry),
      eventType,
      eventId,
      timestamp: row.dataset.timestamp || undefined,
      note: row.dataset.note || undefined,
      value: row.dataset.value || undefined,
      displayUnit: weightUnit,
    });
    editing = false;
    if (disposed) return;
    if (result) {
      result.cleanup();
      refresh();
    }
  }

  function onContainerClick(e: Event): void {
    const target = e.target as HTMLElement;
    const loadBtn = target.closest('.load-more-btn');
    if (loadBtn) {
      loadMore();
      return;
    }
    const delBtn = target.closest<HTMLButtonElement>('.delete-btn');
    if (delBtn) {
      e.stopPropagation();
      handleDelete(delBtn);
      return;
    }
    const editBtn = target.closest<HTMLButtonElement>('.edit-btn');
    if (editBtn) {
      e.stopPropagation();
      handleEdit(editBtn);
    }
  }

  // One delegated listener survives row injection and refreshes
  container.addEventListener('click', onContainerClick);

  function cleanup(): void {
    disposed = true;
    if (observer) {
      observer.disconnect();
      observer = null;
    }
    for (const id of timers) clearTimeout(id);
    timers = [];
    for (const id of deleteConfirm.values()) clearTimeout(id);
    deleteConfirm.clear();
    container.removeEventListener('click', onContainerClick);
    container.innerHTML = '';
    formSlot.innerHTML = '';
  }

  // Initial fetch
  refresh();

  return { refresh, cleanup };
}
