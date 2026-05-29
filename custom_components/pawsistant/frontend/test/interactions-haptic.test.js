/**
 * Pawsistant Card — Interactions: haptic + click-through fix tests
 */
import { describe, it, expect, vi } from 'vitest';
import { setupLongPress, fireHaptic } from '../src/interactions.js';

describe('fireHaptic', () => {
  it('dispatches a haptic CustomEvent with composed: true', () => {
    const el = document.createElement('div');
    const events = [];
    el.addEventListener('haptic', (e) => events.push(e));
    fireHaptic(el, 'medium');
    expect(events.length).toBe(1);
    expect(events[0].detail).toEqual({ haptic: 'medium' });
    expect(events[0].bubbles).toBe(true);
    expect(events[0].composed).toBe(true);
  });

  it('defaults to medium haptic type', () => {
    const el = document.createElement('div');
    const events = [];
    el.addEventListener('haptic', (e) => events.push(e));
    fireHaptic(el);
    expect(events[0].detail).toEqual({ haptic: 'medium' });
  });
});

describe('setupLongPress click-through fix', () => {
  it('does NOT fire onTap after a long-press (click-through fix)', async () => {
    const btn = document.createElement('button');
    const taps = [];
    const holds = [];
    const cleanup = setupLongPress(btn, {
      onTap: () => taps.push(1),
      onLongPress: () => holds.push(1),
    }, []);

    // Simulate long press: pointerdown, wait 600ms, pointerup, click
    btn.dispatchEvent(new MouseEvent('pointerdown'));
    await new Promise(r => setTimeout(r, 600));
    btn.dispatchEvent(new MouseEvent('pointerup'));
    // Browser synthesizes click after pointerup
    btn.dispatchEvent(new MouseEvent('click'));

    expect(holds.length).toBe(1);
    expect(taps.length).toBe(0); // This was the bug — taps would be 1 without the fix

    cleanup();
  });

  it('fires haptic event on long-press', async () => {
    const btn = document.createElement('button');
    const haptics = [];
    btn.addEventListener('haptic', (e) => haptics.push(e));
    const cleanup = setupLongPress(btn, {
      onLongPress: () => {},
    }, []);

    btn.dispatchEvent(new MouseEvent('pointerdown'));
    await new Promise(r => setTimeout(r, 600));

    expect(haptics.length).toBe(1);
    expect(haptics[0].detail.haptic).toBe('medium');

    cleanup();
  });
});
