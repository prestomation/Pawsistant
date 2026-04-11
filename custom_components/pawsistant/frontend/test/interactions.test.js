/**
 * Pawsistant Card — Interactions module tests
 */
import { describe, it, expect } from 'vitest';
import { setupLongPress, withCooldown } from '../src/interactions.js';

describe('setupLongPress', () => {
  it('calls onTap on short click', () => {
    const btn = document.createElement('button');
    const taps = [];
    const holds = [];
    const cleanup = setupLongPress(btn, {
      onTap: () => taps.push(1),
      onLongPress: () => holds.push(1),
    }, []);

    btn.dispatchEvent(new MouseEvent('pointerdown'));
    btn.dispatchEvent(new MouseEvent('pointerup'));
    btn.dispatchEvent(new MouseEvent('click'));

    expect(taps.length).toBe(1);
    expect(holds.length).toBe(0);
    cleanup();
  });

  it('provides a cleanup function that removes listeners', () => {
    const btn = document.createElement('button');
    const cleanup = setupLongPress(btn, { onTap: () => {}, onLongPress: () => {} }, []);
    // Should not throw
    cleanup();
  });
});

describe('withCooldown', () => {
  it('calls the wrapped function immediately', () => {
    const calls = [];
    const fn = withCooldown(() => calls.push(1), 1000);
    fn();
    expect(calls.length).toBe(1);
  });

  it('blocks re-invocation during cooldown', () => {
    const calls = [];
    const fn = withCooldown(() => calls.push(1), 100000); // long cooldown
    fn();
    fn();
    fn();
    expect(calls.length).toBe(1);
  });
});