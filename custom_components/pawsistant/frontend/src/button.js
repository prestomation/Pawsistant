/**
 * Pawsistant Card — Single-button renderer
 *
 * Renders a single Pawsistant action button into a container and wires up
 * tap/long-press handlers via setupLongPress.
 *
 * Returned cleanup removes event listeners only; callers remove the element.
 */
import { setupLongPress } from './interactions.js';

export function renderPawsistantButton({
  container,
  meta,
  metricText = '',
  disabled = false,
  onTap,
  onLongPress,
  timers,
  haptics = false,
}) {
  const btn = document.createElement('button');
  btn.className = 'log-btn';
  btn.type = 'button';
  btn.setAttribute('aria-label', `Log ${meta.label || ''}. Hold to log now.`);

  const emojiSpan = document.createElement('span');
  emojiSpan.className = 'btn-emoji';
  emojiSpan.setAttribute('aria-hidden', 'true');
  emojiSpan.textContent = meta.emoji || '';

  const labelSpan = document.createElement('span');
  labelSpan.className = 'btn-label';
  labelSpan.textContent = (meta.label || '') + (metricText ? ` (${metricText})` : '');

  btn.appendChild(emojiSpan);
  btn.appendChild(labelSpan);

  if (meta.color) {
    btn.style.setProperty('--pawsistant-btn-color', meta.color);
  }

  container.appendChild(btn);

  if (disabled) {
    btn.disabled = true;
    btn.setAttribute('aria-disabled', 'true');
    return { element: btn, cleanup: () => {} };
  }

  const cleanup = setupLongPress(btn, {
    onTap: () => { if (onTap) onTap(btn); },
    onLongPress: () => { if (onLongPress) onLongPress(btn); },
    haptics,
  }, timers);

  return { element: btn, cleanup };
}
