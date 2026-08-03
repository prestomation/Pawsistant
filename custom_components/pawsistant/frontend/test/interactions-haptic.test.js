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
    expect(events[0].detail).toBe('medium');
    expect(events[0].bubbles).toBe(true);
    expect(events[0].composed).toBe(true);
  });

  it('defaults to medium haptic type', () => {
    const el = document.createElement('div');
    const events = [];
    el.addEventListener('haptic', (e) => events.push(e));
    fireHaptic(el);
    expect(events[0].detail).toBe('medium');
  });
});

describe('haptic payload contract with the HA Companion app', () => {
  /**
   * Home Assistant's external-app bridge forwards our event to the Companion
   * app verbatim:
   *
   *   window.addEventListener("haptic", (ev) =>
   *     external.fireMessage({ type: "haptic", payload: { hapticType: ev.detail } }))
   *       — frontend/src/external_app/external_app_entrypoint.ts
   *
   * So `detail` must be the bare HapticType string. Wrapping it in an object
   * produces {"hapticType":{"haptic":"medium"}}, which the Android app's
   * polymorphic deserializer resolves to HapticType.Unknown and silently
   * discards ("Ignoring unknown haptic type" in HapticFeedbackPerformer).
   * That is invisible in a browser, so assert the forwarded payload directly.
   */
  function captureAppPayload(fire) {
    const messages = [];
    const listener = (ev) => messages.push({ type: 'haptic', payload: { hapticType: ev.detail } });
    window.addEventListener('haptic', listener);
    try {
      fire();
    } finally {
      window.removeEventListener('haptic', listener);
    }
    return messages;
  }

  it('forwards the bare haptic type the app can deserialise', () => {
    const el = document.createElement('div');
    document.body.appendChild(el);
    try {
      const messages = captureAppPayload(() => fireHaptic(el, 'medium'));
      expect(messages).toEqual([{ type: 'haptic', payload: { hapticType: 'medium' } }]);
    } finally {
      el.remove();
    }
  });

  it('uses a haptic type the Companion app recognises', () => {
    // Mirrors HapticType in frontend/src/data/haptics.ts; anything else maps
    // to HapticType.Unknown on Android.
    const VALID = ['success', 'warning', 'failure', 'light', 'medium', 'heavy', 'selection'];
    const el = document.createElement('div');
    document.body.appendChild(el);
    try {
      const messages = captureAppPayload(() => fireHaptic(el));
      expect(VALID).toContain(messages[0].payload.hapticType);
    } finally {
      el.remove();
    }
  });

  it('reaches the app from inside a shadow root', () => {
    // Buttons live in the card's shadow DOM; without composed: true the event
    // never escapes to window and the app is never told.
    const host = document.createElement('div');
    document.body.appendChild(host);
    const root = host.attachShadow({ mode: 'open' });
    const btn = document.createElement('button');
    root.appendChild(btn);
    try {
      const messages = captureAppPayload(() => fireHaptic(btn, 'medium'));
      expect(messages).toEqual([{ type: 'haptic', payload: { hapticType: 'medium' } }]);
    } finally {
      host.remove();
    }
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
    expect(haptics[0].detail).toBe('medium');

    cleanup();
  });
});
