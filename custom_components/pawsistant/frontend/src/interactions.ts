/**
 * Pawsistant Card — Interaction helpers
 *
 * Long-press detection, cooldown logic, and tap/hold handler setup.
 */

import type { LongPressHandlers } from './types';

/**
 * Set up a long-press / tap handler on a button element.
 *
 * - Long press (hold ≥ 500ms): triggers onLongPress, fires immediately on timeout.
 * - Short tap: triggers onTap.
 * - Keyboard: Enter = onTap, Space = onLongPress.
 *
 * Returns a cleanup function that removes all listeners.
 */
export function setupLongPress(
  btn: HTMLButtonElement,
  { onLongPress, onTap }: LongPressHandlers,
  timers: (ReturnType<typeof setTimeout> | number)[]
): () => void {
  let pressTimer: ReturnType<typeof setTimeout> | null = null;
  let didLongPress = false;

  const startPress = (e: PointerEvent): void => {
    didLongPress = false;
    pressTimer = setTimeout(() => {
      didLongPress = true;
      e.preventDefault();
      if (onLongPress) onLongPress(btn);
    }, 500);
    timers.push(pressTimer);
  };

  const endPress = (): void => {
    if (pressTimer) {
      clearTimeout(pressTimer);
      const idx = timers.indexOf(pressTimer);
      if (idx !== -1) {
        timers.splice(idx, 1);
      }
      pressTimer = null;
    }
    didLongPress = false;
  };

  const handleClick = (): void => {
    if (!didLongPress) {
      if (onTap) onTap(btn);
    }
  };

  const handleKeydown = (e: KeyboardEvent): void => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (onTap) onTap(btn);
    } else if (e.key === ' ') {
      e.preventDefault();
      if (onLongPress) onLongPress(btn);
    }
  };

  btn.addEventListener('pointerdown', startPress as EventListener);
  btn.addEventListener('pointerup', endPress);
  btn.addEventListener('pointerleave', endPress);
  btn.addEventListener('pointercancel', endPress);
  btn.addEventListener('click', handleClick);
  btn.addEventListener('keydown', handleKeydown);

  return () => {
    btn.removeEventListener('pointerdown', startPress as EventListener);
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
export function withCooldown<T extends (...args: any[]) => any>(fn: T, delayMs: number = 500): T {
  let active = false;
  return function (this: unknown, ...args: Parameters<T>): ReturnType<T> | undefined {
    if (active) return undefined;
    active = true;
    setTimeout(() => { active = false; }, delayMs);
    return fn.apply(this, args);
  } as T;
}