/**
 * Pawsistant Card — Pending log entries
 *
 * A tap adds a pending entry at once. The entry is in memory only. It is "saving"
 * until Home Assistant answers, and "failed" after 15 s or on an error. A late answer
 * still makes it "saved". Retry reads the list first, so a lost reply makes no
 * second event. No framework, no storage, no card coupling.
 */

import type { HomeAssistant, TimelineEvent } from './types';
import { logEventWithId } from './services';

/** Time without an answer before the row says "Not saved yet". */
export const PENDING_TIMEOUT_MS = 15000;

export type PendingState = 'saving' | 'failed' | 'saved';

export interface PendingEntry {
  id: string;
  dog: string;
  type: string;
  /** UTC ISO time of the tap, or the time the user chose. */
  iso: string;
  note?: string;
  state: PendingState;
  /** The id Home Assistant gave, once saved. */
  eventId?: string | null;
}

export interface PendingHooks {
  onSaved?: (eventId: string | null) => void;
  onFailed?: () => void;
}

export interface PendingOptions {
  getHass: () => HomeAssistant | undefined;
  getDogId: () => string | null;
  /** The list of entries or the state of one entry changed. */
  onChange: () => void;
  /** An entry became "saved": the card loads the list again. */
  onSaved: (entry: PendingEntry) => void;
}

interface Slot {
  entry: PendingEntry;
  hooks: PendingHooks;
  timer: ReturnType<typeof setTimeout> | null;
  /** Counts the sends, so an old rejection does not hide a newer try. */
  attempt: number;
}

export class PendingLog {
  private slots: Slot[] = [];
  private seq = 0;
  private listeners = new Set<() => void>();

  constructor(private opts: PendingOptions) {}

  /** The entries, oldest first. */
  get entries(): PendingEntry[] {
    return this.slots.map((s) => s.entry);
  }

  /** Call fn on each change, for a second view of the same list (the popup). Returns the stop function. */
  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  /** Add an entry and send it. */
  add(spec: { dog: string; type: string; iso: string; note?: string }, hooks: PendingHooks = {}): PendingEntry {
    const entry: PendingEntry = { id: `pending-${++this.seq}`, state: 'saving', ...spec };
    const slot: Slot = { entry, hooks, timer: null, attempt: 0 };
    this.slots.push(slot);
    this.arm(slot);
    this.send(slot);
    this.notify();
    return entry;
  }

  /** Try a "failed" entry again. It reads the list first: the first call may have arrived. */
  retry(id: string): void {
    const slot = this.find(id);
    if (!slot || slot.entry.state !== 'failed') return;
    slot.entry.state = 'saving';
    this.arm(slot);
    this.notify();
    void this.checkThenSend(slot);
  }

  discard(id: string): void {
    const slot = this.find(id);
    if (!slot) return;
    this.disarm(slot);
    this.slots = this.slots.filter((s) => s !== slot);
    this.notify();
  }

  /**
   * Drop the saved entries. The card calls this after the list is loaded again, with the
   * ids of the loaded events: a solid row stays until the list has its event.
   */
  clearSaved(loadedIds?: Iterable<string>): void {
    const ids = loadedIds ? new Set(loadedIds) : null;
    this.slots = this.slots.filter(
      (s) => s.entry.state !== 'saved' || (ids !== null && !!s.entry.eventId && !ids.has(s.entry.eventId)),
    );
  }

  dispose(): void {
    for (const s of this.slots) this.disarm(s);
    this.slots = [];
    this.listeners.clear();
  }

  private notify(): void {
    this.opts.onChange();
    for (const fn of this.listeners) fn();
  }

  private find(id: string): Slot | undefined {
    return this.slots.find((s) => s.entry.id === id);
  }

  private arm(slot: Slot): void {
    this.disarm(slot);
    slot.timer = setTimeout(() => {
      slot.timer = null;
      this.fail(slot);
    }, PENDING_TIMEOUT_MS);
  }

  private disarm(slot: Slot): void {
    if (slot.timer !== null) clearTimeout(slot.timer);
    slot.timer = null;
  }

  private send(slot: Slot): void {
    const hass = this.opts.getHass();
    if (!hass) {
      this.fail(slot);
      return;
    }
    const { entry } = slot;
    const attempt = ++slot.attempt;
    const extra: Record<string, unknown> = { timestamp: entry.iso };
    if (entry.note) extra['note'] = entry.note;
    logEventWithId(hass, entry.dog, entry.type, extra).then(
      // A late answer still counts, also from an older try.
      (eventId) => this.settle(slot, eventId),
      (err) => {
        console.warn('[pawsistant-card] log_event failed:', err);
        if (attempt === slot.attempt) this.fail(slot);
      },
    );
  }

  private async checkThenSend(slot: Slot): Promise<void> {
    const found = await this.findOnServer(slot.entry);
    if (slot.entry.state !== 'saving' || !this.slots.includes(slot)) return;
    if (found === undefined) {
      // We cannot tell if the first call arrived. A second call could make a copy.
      this.fail(slot);
    } else if (found) {
      this.settle(slot, found);
    } else {
      this.send(slot);
    }
  }

  /** The id of the same event on the server, null if it is not there, undefined if we cannot read. */
  private async findOnServer(entry: PendingEntry): Promise<string | null | undefined> {
    const hass = this.opts.getHass();
    const dogId = this.opts.getDogId();
    if (!hass?.connection || !dogId) return undefined;
    try {
      const result = (await hass.connection.sendMessagePromise({
        type: 'pawsistant/get_events',
        dog_id: dogId,
        offset: 0,
        limit: 50,
      })) as { events?: TimelineEvent[] };
      const at = Date.parse(entry.iso);
      const same = (result.events || []).find((e) => e.type === entry.type && Date.parse(e.iso) === at);
      return same ? same.event_id : null;
    } catch (err) {
      console.warn('[pawsistant-card] could not read events for Retry:', err);
      return undefined;
    }
  }

  private fail(slot: Slot): void {
    if (slot.entry.state === 'saved' || !this.slots.includes(slot)) return;
    this.disarm(slot);
    slot.entry.state = 'failed';
    slot.hooks.onFailed?.();
    this.notify();
  }

  private settle(slot: Slot, eventId: string | null): void {
    // A discarded entry or a second answer (a Retry that did arrive twice) does nothing.
    if (slot.entry.state === 'saved' || !this.slots.includes(slot)) return;
    this.disarm(slot);
    slot.entry.state = 'saved';
    slot.entry.eventId = eventId;
    slot.hooks.onSaved?.(eventId);
    this.opts.onSaved(slot.entry);
    this.notify();
  }
}

/* ── Show pending entries in the list ─────────────────────────────────── */

/** Time, weekday and date as the server writes them (__init__.py, get_events), in the HA time zone. */
export function formatLocal(iso: string, timeZone?: string): { time: string; day: string; date: string } {
  const d = new Date(iso);
  const make = (tz?: string) =>
    new Intl.DateTimeFormat('en-US', {
      ...(tz ? { timeZone: tz } : {}),
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      weekday: 'short',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(d);
  let parts: Intl.DateTimeFormatPart[];
  try {
    parts = make(timeZone);
  } catch {
    parts = make(undefined);
  }
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  return {
    time: `${get('hour')}:${get('minute')} ${get('dayPeriod').toUpperCase()}`,
    day: get('weekday'),
    date: `${get('month')}/${get('day')}`,
  };
}

/** Put the entries into the loaded events, newest first. */
export function mergePending(events: TimelineEvent[], entries: PendingEntry[], timeZone?: string): TimelineEvent[] {
  if (!entries.length) return events;
  const loaded = new Set(events.map((e) => e.event_id));
  const rows = entries
    // A solid row that the loaded list already has would show twice.
    .filter((e) => !(e.state === 'saved' && e.eventId && loaded.has(e.eventId)))
    .map((e, order) => ({ row: toRow(e, timeZone), ms: Date.parse(e.iso), order }))
    // Newest first; for the same time, the later tap first
    .sort((a, b) => b.ms - a.ms || b.order - a.order);
  const out: TimelineEvent[] = [];
  let i = 0;
  for (const ev of events) {
    const at = Date.parse(ev.iso);
    while (i < rows.length && rows[i].ms >= at) out.push(rows[i++].row);
    out.push(ev);
  }
  while (i < rows.length) out.push(rows[i++].row);
  return out;
}

function toRow(e: PendingEntry, timeZone?: string): TimelineEvent {
  const row: TimelineEvent = {
    type: e.type,
    event_id: e.eventId || '',
    ...formatLocal(e.iso, timeZone),
    iso: e.iso,
    note: e.note || '',
  };
  if (e.state !== 'saved') row.pending = { id: e.id, state: e.state };
  return row;
}
