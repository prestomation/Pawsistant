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

  it('does not fire onTap when a long-press already fired', () => {
    const btn = document.createElement('button');
    const taps = [];
    const holds = [];
    const cleanup = setupLongPress(btn, {
      onTap: () => taps.push(1),
      onLongPress: () => holds.push(1),
    }, []);

    vi.useFakeTimers();
    btn.dispatchEvent(new MouseEvent('pointerdown'));
    vi.advanceTimersByTime(500); // trigger long-press
    btn.dispatchEvent(new MouseEvent('pointerup'));
    btn.dispatchEvent(new MouseEvent('click')); // synthesized after pointerup
    vi.useRealTimers();

    expect(holds.length).toBe(1);
    expect(taps.length).toBe(0);
    cleanup();
  });

  it('provides a cleanup function that removes listeners', () => {
    const btn = document.createElement('button');
    const cleanup = setupLongPress(btn, { onTap: () => {}, onLongPress: () => {} }, []);
    // Should not throw
    cleanup();
  });

  it('fires a composed bubbling "haptic" event on long press when haptics is true', () => {
    const root = document.createElement('div');
    document.body.appendChild(root);
    const btn = document.createElement('button');
    root.appendChild(btn);

    const captured = [];
    // Listen at the document level to confirm the event bubbles + composes.
    const listener = (e) => captured.push({ type: e.type, detail: e.detail });
    document.addEventListener('haptic', listener);

    const cleanup = setupLongPress(btn, {
      onTap: () => {},
      onLongPress: () => {},
      haptics: true,
    }, []);

    vi.useFakeTimers();
    btn.dispatchEvent(new MouseEvent('pointerdown'));
    vi.advanceTimersByTime(500);
    vi.useRealTimers();

    expect(captured).toHaveLength(1);
    expect(captured[0].type).toBe('haptic');
    expect(captured[0].detail).toEqual({ haptic: 'medium' });

    cleanup();
    document.removeEventListener('haptic', listener);
    root.remove();
  });

  it('does not fire a "haptic" event when haptics is false', () => {
    const btn = document.createElement('button');
    document.body.appendChild(btn);
    const captured = [];
    const listener = () => captured.push(1);
    document.addEventListener('haptic', listener);

    const cleanup = setupLongPress(btn, {
      onTap: () => {},
      onLongPress: () => {},
      haptics: false,
    }, []);

    vi.useFakeTimers();
    btn.dispatchEvent(new MouseEvent('pointerdown'));
    vi.advanceTimersByTime(500);
    vi.useRealTimers();

    expect(captured).toEqual([]);

    cleanup();
    document.removeEventListener('haptic', listener);
    btn.remove();
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