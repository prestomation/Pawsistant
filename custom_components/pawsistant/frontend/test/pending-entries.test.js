/**
 * Pawsistant Card — pending log entries.
 *
 * A fake hass lets the service call hang, reject or answer late. The tests check
 * the state of each pending entry at 0, 5, 15 and 30 seconds.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { PendingLog, mergePending, formatLocal, PENDING_TIMEOUT_MS } from '../src/pending.js';

/** A fake Home Assistant. `mode` sets how the next log_event calls behave. */
function makeNet() {
  const net = {
    mode: 'hang', // 'hang' | 'reject' | 'ok'
    serverEvents: [], // newest first, as get_events returns them
    calls: [],
    open: [], // calls with no answer yet
    readFails: false,
    reads: [], // get_events requests
  };
  let n = 0;
  const store = (data) => {
    const event_id = `ev${++n}`;
    net.serverEvents.unshift({ type: data.event_type, event_id, iso: data.timestamp, note: data.note || '' });
    return event_id;
  };
  net.hass = {
    states: {},
    callService: vi.fn((domain, service, data) => {
      net.calls.push(data);
      if (net.mode === 'reject') return Promise.reject(new Error('Connection lost'));
      if (net.mode === 'ok') return Promise.resolve({ response: { event_id: store(data) } });
      return new Promise((resolve, reject) => {
        net.open.push({ data, resolve, reject });
      });
    }),
    connection: {
      sendMessagePromise: vi.fn(async (msg) => {
        if (net.readFails) throw new Error('Connection lost');
        net.reads.push(msg);
        const all = msg.event_type ? net.serverEvents.filter((e) => e.type === msg.event_type) : net.serverEvents;
        return { events: all.slice(msg.offset, msg.offset + msg.limit), total: all.length };
      }),
    },
  };
  /** The server stores the event. The reply may be lost or late. */
  net.arrive = (i = 0) => store(net.open[i].data);
  /** The reply of an open call comes back. */
  net.answer = (i = 0) => {
    const id = net.arrive(i);
    net.open[i].resolve({ response: { event_id: id } });
    return id;
  };
  return net;
}

function makeLog(net, extra = {}) {
  const changes = vi.fn();
  const saved = vi.fn();
  const log = new PendingLog({
    getHass: () => net.hass,
    getDogId: () => 'dog1',
    onChange: changes,
    onSaved: saved,
    ...extra,
  });
  return { log, changes, saved };
}

const spec = (over = {}) => ({ dog: 'Sharky', type: 'pee', iso: '2026-11-16T17:41:00.000Z', ...over });
const flush = async () => {
  for (let i = 0; i < 100; i++) await Promise.resolve();
};

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('PendingLog — a call that hangs', () => {
  it('is "saving" at 0, 5 and 14.9 s, and "failed" at 15 s and 30 s', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    const entry = log.add(spec());
    expect(entry.state).toBe('saving');
    expect(log.entries).toHaveLength(1);

    await vi.advanceTimersByTimeAsync(5000);
    expect(log.entries[0].state).toBe('saving');
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS - 5000 - 100);
    expect(log.entries[0].state).toBe('saving');
    await vi.advanceTimersByTimeAsync(100);
    expect(log.entries[0].state).toBe('failed');
    await vi.advanceTimersByTimeAsync(15000);
    expect(log.entries[0].state).toBe('failed');
  });

  it('sends the tap time as a UTC ISO timestamp and sends the note', () => {
    const net = makeNet();
    const { log } = makeLog(net);
    log.add(spec({ note: 'park' }));
    expect(net.calls[0]).toEqual({
      dog: 'Sharky',
      event_type: 'pee',
      timestamp: '2026-11-16T17:41:00.000Z',
      note: 'park',
    });
    // Home Assistant must show its own toast and send back the id
    expect(net.hass.callService.mock.calls[0].slice(3)).toEqual([undefined, true, true]);
  });

  it('tells the card to draw again on each change', async () => {
    const net = makeNet();
    const { log, changes } = makeLog(net);
    log.add(spec());
    expect(changes).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS);
    expect(changes).toHaveBeenCalledTimes(2);
  });
});

describe('PendingLog — answers', () => {
  it('turns solid when the answer arrives in time', async () => {
    const net = makeNet();
    const { log, saved } = makeLog(net);
    const onSaved = vi.fn();
    log.add(spec(), { onSaved });
    await vi.advanceTimersByTimeAsync(5000);
    const id = net.answer();
    await flush();
    expect(log.entries[0].state).toBe('saved');
    expect(log.entries[0].eventId).toBe(id);
    expect(onSaved).toHaveBeenCalledWith(id);
    expect(saved).toHaveBeenCalledTimes(1);
    // The timer must not turn a solid row to "failed"
    await vi.advanceTimersByTimeAsync(60000);
    expect(log.entries[0].state).toBe('saved');
  });

  it('shows "failed" at once when the call rejects', async () => {
    const net = makeNet();
    net.mode = 'reject';
    const { log } = makeLog(net);
    const onFailed = vi.fn();
    log.add(spec(), { onFailed });
    await flush();
    expect(log.entries[0].state).toBe('failed');
    expect(onFailed).toHaveBeenCalledTimes(1);
  });

  it('turns solid when a late answer comes after "Not saved yet"', async () => {
    const net = makeNet();
    const { log, saved } = makeLog(net);
    log.add(spec());
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS);
    expect(log.entries[0].state).toBe('failed');
    await vi.advanceTimersByTimeAsync(15000); // 30 s
    net.answer();
    await flush();
    expect(log.entries[0].state).toBe('saved');
    expect(saved).toHaveBeenCalledTimes(1);
  });

  it('clearSaved drops solid rows only', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    log.add(spec());
    log.add(spec({ type: 'poop' }));
    net.answer(0);
    await flush();
    log.clearSaved();
    expect(log.entries.map((e) => e.type)).toEqual(['poop']);
  });
});

describe('PendingLog — two entries', () => {
  it('keeps one state for each entry', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    log.add(spec({ type: 'pee' }));
    await vi.advanceTimersByTimeAsync(10000);
    log.add(spec({ type: 'poop', iso: '2026-11-16T17:42:00.000Z' }));
    await vi.advanceTimersByTimeAsync(5000); // 15 s for the first, 5 s for the second
    expect(log.entries.map((e) => [e.type, e.state])).toEqual([
      ['pee', 'failed'],
      ['poop', 'saving'],
    ]);
    net.answer(1);
    await flush();
    expect(log.entries.map((e) => [e.type, e.state])).toEqual([
      ['pee', 'failed'],
      ['poop', 'saved'],
    ]);
  });
});

describe('PendingLog — Discard', () => {
  it('removes the entry and stops its timer', async () => {
    const net = makeNet();
    const { log, changes } = makeLog(net);
    const entry = log.add(spec());
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS);
    changes.mockClear();
    log.discard(entry.id);
    expect(log.entries).toHaveLength(0);
    expect(changes).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(60000);
    expect(changes).toHaveBeenCalledTimes(1);
  });

  it('ignores a late answer of a discarded entry', async () => {
    const net = makeNet();
    const { log, saved } = makeLog(net);
    const entry = log.add(spec());
    log.discard(entry.id);
    net.answer();
    await flush();
    expect(log.entries).toHaveLength(0);
    expect(saved).not.toHaveBeenCalled();
  });
});

describe('PendingLog — Retry', () => {
  async function failedWithLostReply(net, log) {
    const entry = log.add(spec());
    net.arrive(0); // the server stored it, the reply is lost
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS);
    expect(log.entries[0].state).toBe('failed');
    return entry;
  }

  it('sends nothing when the event is already on the server', async () => {
    const net = makeNet();
    const { log, saved } = makeLog(net);
    const entry = await failedWithLostReply(net, log);
    log.retry(entry.id);
    expect(log.entries[0].state).toBe('saving');
    await flush();
    expect(net.hass.callService).toHaveBeenCalledTimes(1);
    expect(log.entries[0].state).toBe('saved');
    expect(log.entries[0].eventId).toBe(net.serverEvents[0].event_id);
    expect(saved).toHaveBeenCalledTimes(1);
    expect(net.serverEvents).toHaveLength(1);
  });

  it('matches the time as a moment, not as text (local offset in the reply)', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    const entry = await failedWithLostReply(net, log);
    net.serverEvents[0].iso = '2026-11-16T09:41:00-08:00';
    log.retry(entry.id);
    await flush();
    expect(net.hass.callService).toHaveBeenCalledTimes(1);
    expect(log.entries[0].state).toBe('saved');
  });

  it('finds a backdated event that is deeper than 50 newer events', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    const entry = log.add(spec({ iso: '2026-11-10T17:41:00.000Z' }));
    net.arrive(0); // stored, reply lost
    // 120 newer events of the same type sit above it in the list
    for (let i = 0; i < 120; i++) {
      net.serverEvents.unshift({ type: 'pee', event_id: `n${i}`, iso: new Date(Date.UTC(2026, 10, 12, 0, i)).toISOString() });
    }
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS);
    log.retry(entry.id);
    await flush();
    expect(net.hass.callService).toHaveBeenCalledTimes(1);
    expect(log.entries[0].state).toBe('saved');
  });

  it('stops reading when the list is older than the entry', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    for (let i = 0; i < 600; i++) {
      net.serverEvents.push({ type: 'pee', event_id: `o${i}`, iso: new Date(Date.UTC(2026, 0, 1, 0, 600 - i)).toISOString() });
    }
    const entry = log.add(spec({ iso: '2026-11-16T17:41:00.000Z' }));
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS);
    log.retry(entry.id);
    await flush();
    expect(net.reads).toHaveLength(1); // the first page is already older
    expect(net.hass.callService).toHaveBeenCalledTimes(2);
  });

  it('stays "failed" and sends nothing when the list is too long to read', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    for (let i = 0; i < 6000; i++) {
      net.serverEvents.push({ type: 'pee', event_id: `n${i}`, iso: new Date(Date.UTC(2027, 0, 1) - i * 60000).toISOString() });
    }
    const entry = log.add(spec({ iso: '2026-01-01T00:00:00.000Z' }));
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS);
    log.retry(entry.id);
    await flush();
    expect(net.hass.callService).toHaveBeenCalledTimes(1);
    expect(log.entries[0].state).toBe('failed');
  });

  it('does not match an event of another type or time', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    net.serverEvents.push({ type: 'poop', event_id: 'x1', iso: '2026-11-16T17:41:00.000Z' });
    net.serverEvents.push({ type: 'pee', event_id: 'x2', iso: '2026-11-16T17:40:00.000Z' });
    const entry = log.add(spec());
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS);
    log.retry(entry.id);
    await flush();
    expect(net.hass.callService).toHaveBeenCalledTimes(2);
    expect(net.calls[1].timestamp).toBe('2026-11-16T17:41:00.000Z');
  });

  it('sends the same timestamp again when the event is not there, and then turns solid', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    const entry = log.add(spec());
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS);
    net.mode = 'ok';
    log.retry(entry.id);
    await flush();
    expect(net.calls).toHaveLength(2);
    expect(net.calls[1].timestamp).toBe(net.calls[0].timestamp);
    expect(log.entries[0].state).toBe('saved');
  });

  it('shows "Not saved yet" again after 15 s without an answer', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    const entry = log.add(spec());
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS);
    log.retry(entry.id);
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS - 100);
    expect(log.entries[0].state).toBe('saving');
    await vi.advanceTimersByTimeAsync(100);
    expect(log.entries[0].state).toBe('failed');
  });

  it('sends nothing and stays "failed" when it cannot read the list', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    const entry = log.add(spec());
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS);
    net.readFails = true;
    log.retry(entry.id);
    await flush();
    expect(net.hass.callService).toHaveBeenCalledTimes(1);
    expect(log.entries[0].state).toBe('failed');
  });

  it('ignores a rejection of the first call after a Retry started', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    const entry = log.add(spec());
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS);
    net.mode = 'hang';
    log.retry(entry.id);
    await flush();
    net.open[0].reject(new Error('Connection lost'));
    await flush();
    expect(log.entries[0].state).toBe('saving');
  });

  it('turns a row that waits for the second try to "saved" when the first call answers late', async () => {
    const net = makeNet();
    const { log, saved } = makeLog(net);
    const entry = log.add(spec());
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS);
    net.mode = 'hang';
    log.retry(entry.id);
    await flush();
    expect(log.entries[0].state).toBe('saving');
    expect(net.open).toHaveLength(2);
    net.answer(0); // the first call answers late
    await flush();
    expect(log.entries[0].state).toBe('saved');
    expect(saved).toHaveBeenCalledTimes(1);
    net.open[1].resolve({ response: { event_id: 'second' } }); // a second answer changes nothing
    await flush();
    expect(saved).toHaveBeenCalledTimes(1);
  });

  it('ignores Retry for a row that is not "failed"', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    const entry = log.add(spec());
    log.retry(entry.id);
    await flush();
    expect(net.hass.callService).toHaveBeenCalledTimes(1);
  });
});

describe('PendingLog — dispose', () => {
  it('stops all timers', async () => {
    const net = makeNet();
    const { log, changes } = makeLog(net);
    log.add(spec());
    changes.mockClear();
    log.dispose();
    await vi.advanceTimersByTimeAsync(60000);
    expect(changes).not.toHaveBeenCalled();
  });
});

describe('formatLocal', () => {
  it('writes the time, the weekday and the date as the server does', () => {
    // 17:41 UTC is 9:41 AM in Seattle on 16 Nov 2026 (a Monday)
    expect(formatLocal('2026-11-16T17:41:00.000Z', 'America/Los_Angeles')).toEqual({
      time: '9:41 AM',
      day: 'Mon',
      date: '11/16',
    });
  });

  it('uses the Home Assistant time zone, not the browser zone', () => {
    expect(formatLocal('2026-11-16T17:41:00.000Z', 'Asia/Tokyo')).toEqual({
      time: '2:41 AM',
      day: 'Tue',
      date: '11/17',
    });
  });

  it('shows noon and midnight as the server does', () => {
    expect(formatLocal('2026-11-16T20:05:00.000Z', 'America/Los_Angeles').time).toBe('12:05 PM');
    expect(formatLocal('2026-11-16T08:05:00.000Z', 'America/Los_Angeles').time).toBe('12:05 AM');
  });

  it('does not throw for an unknown time zone', () => {
    expect(() => formatLocal('2026-11-16T17:41:00.000Z', 'Mars/Base')).not.toThrow();
  });
});

describe('mergePending', () => {
  const ev = (id, iso, over = {}) => ({
    type: 'pee',
    event_id: id,
    time: 't',
    day: 'Mon',
    date: '11/16',
    iso,
    note: '',
    ...over,
  });
  const TZ = 'America/Los_Angeles';

  function entry(net, over = {}) {
    const { log } = makeLog(net);
    const e = log.add(spec(over));
    return [log, e];
  }

  it('returns the same list when there is nothing pending', () => {
    const events = [ev('a', '2026-11-16T08:00:00-08:00')];
    expect(mergePending(events, [], TZ)).toBe(events);
  });

  it('puts a new entry at the top', () => {
    const net = makeNet();
    const [log] = entry(net, { iso: '2026-11-16T17:41:00.000Z' });
    const events = [ev('a', '2026-11-16T08:52:00-08:00'), ev('b', '2026-11-16T07:30:00-08:00')];
    const rows = mergePending(events, log.entries, TZ);
    expect(rows.map((r) => r.event_id)).toEqual(['', 'a', 'b']);
    expect(rows[0].pending).toEqual({ id: log.entries[0].id, state: 'saving' });
    expect(rows[0].time).toBe('9:41 AM');
  });

  it('puts a backdated entry at its own time', () => {
    const net = makeNet();
    const [log] = entry(net, { iso: '2026-11-16T16:00:00.000Z' }); // 8:00 AM
    const events = [ev('a', '2026-11-16T08:52:00-08:00'), ev('b', '2026-11-16T07:30:00-08:00')];
    const rows = mergePending(events, log.entries, TZ);
    expect(rows.map((r) => r.event_id)).toEqual(['a', '', 'b']);
  });

  it('puts an entry older than every loaded event at the end', () => {
    const net = makeNet();
    const [log] = entry(net, { iso: '2026-11-15T01:00:00.000Z' });
    const events = [ev('a', '2026-11-16T08:52:00-08:00')];
    expect(mergePending(events, log.entries, TZ).map((r) => r.event_id)).toEqual(['a', '']);
  });

  it('orders two pending entries newest first', () => {
    const net = makeNet();
    const { log } = makeLog(net);
    log.add(spec({ type: 'pee', iso: '2026-11-16T17:41:00.000Z' }));
    log.add(spec({ type: 'poop', iso: '2026-11-16T17:44:00.000Z' }));
    const rows = mergePending([], log.entries, TZ);
    expect(rows.map((r) => r.type)).toEqual(['poop', 'pee']);
  });

  it('keeps the order of taps when two entries have the same time', () => {
    const net = makeNet();
    const { log } = makeLog(net);
    log.add(spec({ type: 'pee' }));
    log.add(spec({ type: 'poop' }));
    expect(mergePending([], log.entries, TZ).map((r) => r.type)).toEqual(['poop', 'pee']);
  });

  it('shows a solid row with its id, and no pending flag, once saved', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    log.add(spec());
    const id = net.answer();
    await flush();
    const rows = mergePending([], log.entries, TZ);
    expect(rows).toHaveLength(1);
    expect(rows[0].event_id).toBe(id);
    expect(rows[0].pending).toBeUndefined();
  });

  it('hides a solid row when the loaded list already has that event', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    log.add(spec());
    const id = net.answer();
    await flush();
    const rows = mergePending([ev(id, '2026-11-16T09:41:00-08:00')], log.entries, TZ);
    expect(rows.map((r) => r.event_id)).toEqual([id]);
  });

  it('carries the note and the failed state', async () => {
    const net = makeNet();
    const { log } = makeLog(net);
    log.add(spec({ note: 'park loop' }));
    await vi.advanceTimersByTimeAsync(PENDING_TIMEOUT_MS);
    const [row] = mergePending([], log.entries, TZ);
    expect(row.note).toBe('park loop');
    expect(row.pending.state).toBe('failed');
  });
});
