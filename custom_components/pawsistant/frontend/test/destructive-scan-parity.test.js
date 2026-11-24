import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { scan } from './destructive-scan-lib.js';

// Every call of a function that deletes, removes or clears data must sit under a
// confirmation. A new delete button that calls the service at once fails this test.
//
// It reads `src/*.ts` as text. `destructive-scan-lib.test.js` tests the scanner itself
// on small snippets.

// A call that may run without a question. The key is
// `file::function that holds the call::callee`. Each entry says why. An entry that no
// call needs any more fails the test, so this list cannot collect dead names.
const ALLOW = {
  'index.ts::_drawToast::deleteEvent':
    'The Undo button of the log toast. Pressing Undo is itself the answer to "keep it?", ' +
    'and the entry that goes is the one that the tap added a moment before.',
  'button-card.ts::_drawToast::deleteEvent':
    'The Undo button of the log toast. Pressing Undo is itself the answer to "keep it?", ' +
    'and the entry that goes is the one that the tap added a moment before.',
};

const SRC = resolve(__dirname, '../src');
const files = readdirSync(SRC)
  .filter((f) => f.endsWith('.ts'))
  .map((name) => ({ name, source: readFileSync(resolve(SRC, name), 'utf8') }));

describe('destructive actions are confirmed', () => {
  const { violations, stale } = scan(files, ALLOW);

  it('has no call that runs a delete without a confirmation', () => {
    const lines = violations.map((v) => `${v.file}:${v.line} ${v.where} calls ${v.callee}`);
    expect(lines, 'wrap it in confirmDestructive(...), or add a reasoned ALLOW entry').toEqual([]);
  });

  it('has no allowlist entry that nothing needs', () => {
    expect(stale).toEqual([]);
  });

  it('gives every allowlist entry a real reason', () => {
    for (const [key, reason] of Object.entries(ALLOW)) {
      expect(reason.length, key).toBeGreaterThan(40);
    }
  });

  it('keeps the native confirm out of the card', () => {
    const native = files
      .filter((f) => /(^|[^.\w])(window\.)?confirm\s*\(/.test(f.source.replace(/\/\/.*$/gm, '')))
      .map((f) => f.name);
    expect(native, 'use confirmDestructive from confirm-dialog.ts').toEqual(
      files.filter((f) => f.name === 'confirm-dialog.ts' && /confirm\s*\(/.test(f.source)).map((f) => f.name),
    );
  });

  it('keeps every destructive service call inside services.ts', () => {
    // A direct `callService('pawsistant', 'delete_...')` would bypass the names the
    // scan follows. The cards call the helpers of `services.ts`.
    const direct = files
      .filter((f) => f.name !== 'services.ts')
      .filter((f) => /['"`]pawsistant['"`]\s*,\s*['"`](delete_|remove_)/.test(f.source))
      .map((f) => f.name);
    expect(direct).toEqual([]);
  });

  it('finds the guarded calls that it should', () => {
    // A scan that sees no call at all would pass for the wrong reason.
    const timeline = files.find((f) => f.name === 'standalone-timeline.ts');
    expect(timeline, 'standalone-timeline.ts must be in src/').toBeDefined();
    expect(timeline.source).toContain('confirmDestructive');
    expect(timeline.source).toContain('deleteEvent');
    const main = files.find((f) => f.name === 'index.ts');
    expect(main.source).toContain('confirmDestructive');
    expect(main.source).toContain('deleteEventType');
  });
});
