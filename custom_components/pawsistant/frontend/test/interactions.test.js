/**
 * Pawsistant Card — Interactions module tests
 */
import { describe, it, expect, vi } from 'vitest';
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

  it('calls navigator.vibrate(40) on long press when haptics is true', () => {
    const btn = document.createElement('button');
    const vibrateCalls = [];
    const originalVibrate = navigator.vibrate;
    navigator.vibrate = (ms) => { vibrateCalls.push(ms); return true; };

    const cleanup = setupLongPress(btn, {
      onTap: () => {},
      onLongPress: () => {},
      haptics: true,
    }, []);

    vi.useFakeTimers();
    btn.dispatchEvent(new MouseEvent('pointerdown'));
    vi.advanceTimersByTime(500);
    vi.useRealTimers();

    expect(vibrateCalls).toEqual([40]);
    cleanup();
    navigator.vibrate = originalVibrate;
  });

  it('does not call navigator.vibrate when haptics is false', () => {
    const btn = document.createElement('button');
    const vibrateCalls = [];
    const originalVibrate = navigator.vibrate;
    navigator.vibrate = (ms) => { vibrateCalls.push(ms); return true; };

    const cleanup = setupLongPress(btn, {
      onTap: () => {},
      onLongPress: () => {},
      haptics: false,
    }, []);

    vi.useFakeTimers();
    btn.dispatchEvent(new MouseEvent('pointerdown'));
    vi.advanceTimersByTime(500);
    vi.useRealTimers();

    expect(vibrateCalls).toEqual([]);
    cleanup();
    navigator.vibrate = originalVibrate;
  });

  it('does not throw when navigator.vibrate is undefined and haptics is true', () => {
    const btn = document.createElement('button');
    const originalVibrate = navigator.vibrate;
    delete navigator.vibrate;

    const cleanup = setupLongPress(btn, {
      onTap: () => {},
      onLongPress: () => {},
      haptics: true,
    }, []);

    vi.useFakeTimers();
    expect(() => {
      btn.dispatchEvent(new MouseEvent('pointerdown'));
      vi.advanceTimersByTime(500);
    }).not.toThrow();
    vi.useRealTimers();

    cleanup();
    navigator.vibrate = originalVibrate;
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