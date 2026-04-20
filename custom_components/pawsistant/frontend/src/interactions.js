/**
 * Pawsistant Card — Interaction helpers
 *
 * Long-press detection, cooldown logic, and tap/hold handler setup.
 */

/**
 * Fire Home Assistant's "haptic" custom event. The HA Companion mobile app
 * listens for this on the document and triggers native haptics (Taptic
 * Engine on iOS, system vibration on Android). Valid types per HA frontend:
 * "success" | "warning" | "failure" | "light" | "medium" | "heavy" | "selection".
 *
 * `composed: true` lets the event cross the shadow boundary and bubble up
 * to wherever HA's listener is attached.
 */
export function fireHaptic(node, type = 'medium') {
  const event = new Event('haptic', { bubbles: true, composed: true });
  event.detail = { haptic: type };
  node.dispatchEvent(event);
}

/**
 * Set up a long-press / tap handler on a button element.
 *
 * - Long press (hold ≥ 500ms): triggers onLongPress, fires immediately on timeout.
 * - Short tap: triggers onTap.
 * - Keyboard: Enter = onTap, Space = onLongPress.
 *
 * Returns a cleanup function that removes all listeners.
 */
export function setupLongPress(btn, { onLongPress, onTap, haptics = false }, timers) {
  let pressTimer = null;
  let didLongPress = false;

  const startPress = (e) => {
    didLongPress = false;
    pressTimer = setTimeout(() => {
      didLongPress = true;
      e.preventDefault();
      if (haptics) fireHaptic(btn, 'medium');
      if (onLongPress) onLongPress(btn);
    }, 500);
    timers.push(pressTimer);
  };

  const endPress = () => {
    if (pressTimer) {
      clearTimeout(pressTimer);
      const idx = timers.indexOf(pressTimer);
      if (idx !== -1) {
        timers.splice(idx, 1);
      }
      pressTimer = null;
    }
    // Do NOT reset didLongPress here. The synthesized `click` fires after
    // `pointerup`; if we cleared the flag, `handleClick` would misfire `onTap`
    // after a successful long-press. `startPress` resets it on the next press.
  };

  const handleClick = () => {
    if (!didLongPress) {
      if (onTap) onTap(btn);
    }
  };

  const handleKeydown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (onTap) onTap(btn);
    } else if (e.key === ' ') {
      e.preventDefault();
      if (onLongPress) onLongPress(btn);
    }
  };

  btn.addEventListener('pointerdown', startPress);
  btn.addEventListener('pointerup', endPress);
  btn.addEventListener('pointerleave', endPress);
  btn.addEventListener('pointercancel', endPress);
  btn.addEventListener('click', handleClick);
  btn.addEventListener('keydown', handleKeydown);

  return () => {
    btn.removeEventListener('pointerdown', startPress);
    btn.removeEventListener('pointerup', endPress);
    btn.removeEventListener('pointerleave', endPress);
    btn.removeEventListener('pointercancel', endPress);
    btn.removeEventListener('click', handleClick);
    btn.removeEventListener('keydown', handleKeydown);
  };
}

/**
 * Create a cooldown-guarded function.
 * Calls fn immediately, then blocks re-invocation for `delayMs` ms.
 */
export function withCooldown(fn, delayMs = 500) {
  let active = false;
  return function (...args) {
    if (active) return;
    active = true;
    setTimeout(() => { active = false; }, delayMs);
    return fn.apply(this, args);
  };
}