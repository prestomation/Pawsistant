import { describe, expect, it } from 'vitest';
import { eventDeleteText, eventTypeDeleteText, supplyUnlinkText } from '../src/confirm-texts.ts';

const UNDO = 'This cannot be undone.';

describe('eventDeleteText', () => {
  it('names the entry, its time and its note, and the button says what it does', () => {
    const out = eventDeleteText('Pee', '2026-03-01T10:00:00Z', 'at the park', 'en');
    expect(out.title).toBe('Delete this Pee entry?');
    expect(out.confirmLabel).toBe('Delete entry');
    const lines = out.body.split('\n');
    expect(lines[0]).toMatch(/^Pee · .*2026/);
    expect(lines[1]).toBe('at the park');
    expect(lines[2]).toBe(UNDO);
  });

  it('leaves out an empty note and a missing time', () => {
    const out = eventDeleteText('Walk', '', '', 'en');
    expect(out.body).toBe(`Walk\n${UNDO}`);
  });
});

describe('eventTypeDeleteText', () => {
  it('says that logged entries stay', () => {
    const out = eventTypeDeleteText('Meds');
    expect(out.title).toBe("Delete event type 'Meds'?");
    expect(out.confirmLabel).toBe('Delete event type');
    expect(out.body).toBe(`Entries already logged stay in the log.\n${UNDO}`);
  });

  it('says that the supply link goes with the type', () => {
    expect(eventTypeDeleteText('Poop', 'Poop bag rolls').body).toBe(
      `Entries already logged stay in the log.\nThe link to the supply Poop bag rolls is removed.\n${UNDO}`,
    );
  });
});

describe('supplyUnlinkText', () => {
  it('names the supply and the type', () => {
    const out = supplyUnlinkText('Poop', 'Poop bag rolls');
    expect(out.title).toBe("Stop using the supply 'Poop bag rolls'?");
    expect(out.confirmLabel).toBe('Stop using supply');
    expect(out.body).toBe('New Poop entries no longer take from this supply.');
  });
});
