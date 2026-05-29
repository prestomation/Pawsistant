/**
 * Pawsistant Card — Reusable log button
 *
 * Creates a quick-log button with emoji, label, metric badge,
 * and long-press / tap handling via setupLongPress.
 */

import type { EventMeta } from './types';
import { setupLongPress } from './interactions';

interface RenderButtonOptions {
  container: HTMLElement;
  meta: EventMeta;
  metricText: string;
  onTap: (btn: HTMLButtonElement) => void;
  onLongPress: (btn: HTMLButtonElement) => void;
  timers: (ReturnType<typeof setTimeout> | number)[];
}

interface RenderButtonResult {
  element: HTMLButtonElement;
  cleanup: () => void;
}

export function renderPawsistantButton(opts: RenderButtonOptions): RenderButtonResult {
  const { meta, metricText, onTap, onLongPress, timers } = opts;

  const btn = document.createElement('button');
  btn.className = 'log-btn';

  const emojiSpan = document.createElement('span');
  emojiSpan.className = 'btn-emoji';
  emojiSpan.setAttribute('aria-hidden', 'true');
  emojiSpan.textContent = meta.emoji;
  btn.appendChild(emojiSpan);

  const labelSpan = document.createElement('span');
  labelSpan.className = 'btn-label';
  labelSpan.textContent = meta.label + (metricText ? ` ${metricText}` : '');
  btn.appendChild(labelSpan);

  const lpCleanup = setupLongPress(btn, { onTap, onLongPress }, timers);

  const cleanup = (): void => {
    lpCleanup();
  };

  return { element: btn, cleanup };
}
