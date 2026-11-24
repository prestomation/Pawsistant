/**
 * The confirmation dialog. One dialog serves every delete in the cards.
 *
 * The scrim goes on `document.body`, so `position: fixed` resolves against the
 * viewport and not against a shadow root. A shadow root's styles do not reach it, so
 * the scrim defines its own `--pw-confirm-*` tokens from the theme variables of Home
 * Assistant, and every rule below reads those tokens.
 *
 * Cancel has the keyboard. Escape and a tap outside cancel. Tab stays inside. There is
 * no undo: the dialog is the only check, so it names the item and the button names the
 * action. At most 1 dialog is open. It removes itself when the page goes away.
 */

import { T } from './i18n';

export interface ConfirmContent {
  title: string;
  body: string;
  confirmLabel: string;
}

export interface ConfirmHandlers {
  /** Cancel, Escape or a tap outside. */
  onCancel: () => void;
  /** The confirm button. */
  onConfirm: () => void;
}

export interface ConfirmHandle {
  /** Remove the scrim and the listeners. Safe to call twice. */
  close: () => void;
}

const STYLE_ID = 'pw-confirm-style';

// A literal color may appear only on a `--pw-confirm-*` line: the tokens.
const CSS = `
.pw-confirm-scrim {
  --pw-confirm-dim: rgba(0, 0, 0, 0.4);
  --pw-confirm-shadow: rgba(0, 0, 0, 0.24);
  --pw-confirm-surface: var(--ha-card-background, var(--card-background-color, #fff));
  --pw-confirm-ink: var(--primary-text-color, #212121);
  --pw-confirm-ink-soft: var(--secondary-text-color, #727272);
  --pw-confirm-line: var(--divider-color, #e0e0e0);
  --pw-confirm-danger: var(--error-color, #db4437);
  --pw-confirm-on-danger: #fff;
  --pw-confirm-focus: var(--primary-color, #03a9f4);
  --pw-confirm-radius: 16px;
  --pw-confirm-pad: 20px;
  --pw-confirm-edge: 32px;
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--pw-confirm-dim);
}
.pw-confirm-modal {
  box-sizing: border-box;
  min-width: 280px;
  max-width: min(400px, calc(100vw - var(--pw-confirm-edge)));
  padding: var(--pw-confirm-pad);
  border-radius: var(--pw-confirm-radius);
  background: var(--pw-confirm-surface);
  color: var(--pw-confirm-ink);
  box-shadow: 0 8px 32px var(--pw-confirm-shadow);
  font-family: var(--paper-font-body1_-_font-family, inherit);
}
.pw-confirm-title {
  margin: 0 0 12px;
  font-size: 1.125rem;
  font-weight: 500;
  overflow-wrap: anywhere;
}
.pw-confirm-body {
  margin: 0 0 20px;
  color: var(--pw-confirm-ink-soft);
  font-size: 0.875rem;
  white-space: pre-line;
  overflow-wrap: anywhere;
}
.pw-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.pw-confirm-btn {
  min-height: 44px;
  padding: 0 16px;
  border: 1px solid var(--pw-confirm-line);
  border-radius: 8px;
  background: none;
  color: var(--pw-confirm-ink);
  font: inherit;
  font-weight: 500;
  cursor: pointer;
}
.pw-confirm-btn:focus-visible {
  outline: 2px solid var(--pw-confirm-focus);
  outline-offset: 2px;
}
.pw-confirm-danger {
  border-color: var(--pw-confirm-danger);
  background: var(--pw-confirm-danger);
  color: var(--pw-confirm-on-danger);
}
`;

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = CSS;
  document.head.appendChild(style);
}

let current: ConfirmHandle | null = null;

/** Close the open dialog, if there is one. Cards call this when they leave the page. */
export function closeConfirm(): void {
  current?.close();
}

/** Show the dialog. The caller decides what Cancel and the confirm button do. */
export function mountConfirm(content: ConfirmContent, handlers: ConfirmHandlers): ConfirmHandle {
  closeConfirm();
  ensureStyle();
  const scrim = document.createElement('div');
  scrim.className = 'pw-confirm-scrim';

  const modal = document.createElement('div');
  modal.className = 'pw-confirm-modal';
  modal.setAttribute('role', 'alertdialog');
  modal.setAttribute('aria-modal', 'true');
  modal.setAttribute('aria-labelledby', 'pw-confirm-title');
  modal.setAttribute('aria-describedby', 'pw-confirm-body');

  const h2 = document.createElement('h2');
  h2.id = 'pw-confirm-title';
  h2.className = 'pw-confirm-title';
  h2.textContent = content.title;

  const para = document.createElement('p');
  para.id = 'pw-confirm-body';
  para.className = 'pw-confirm-body';
  para.textContent = content.body;

  const row = document.createElement('div');
  row.className = 'pw-confirm-actions';

  const cancel = document.createElement('button');
  cancel.type = 'button';
  cancel.className = 'pw-confirm-btn';
  cancel.textContent = T('form.cancel');
  cancel.addEventListener('click', () => handlers.onCancel());

  const confirm = document.createElement('button');
  confirm.type = 'button';
  confirm.className = 'pw-confirm-btn pw-confirm-danger';
  confirm.textContent = content.confirmLabel;
  confirm.addEventListener('click', () => handlers.onConfirm());

  row.append(cancel, confirm);
  modal.append(h2, para, row);
  scrim.appendChild(modal);
  scrim.addEventListener('click', (e) => {
    if (e.target === scrim) handlers.onCancel();
  });

  const buttons = [cancel, confirm];
  const onKey = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') {
      // 1 press closes 1 overlay: a handler of an overlay below does not run.
      e.stopImmediatePropagation();
      handlers.onCancel();
      return;
    }
    if (e.key !== 'Tab') return;
    e.preventDefault();
    const at = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const step = e.shiftKey ? -1 : 1;
    const next = at < 0 ? (e.shiftKey ? buttons.length - 1 : 0) : at + step;
    buttons[(next + buttons.length) % buttons.length].focus();
  };
  const onHide = (): void => handle.close();
  document.addEventListener('keydown', onKey, true);
  window.addEventListener('pagehide', onHide);
  document.body.appendChild(scrim);

  let open = true;
  const handle: ConfirmHandle = {
    close: () => {
      if (!open) return;
      open = false;
      document.removeEventListener('keydown', onKey, true);
      window.removeEventListener('pagehide', onHide);
      scrim.remove();
      if (current === handle) current = null;
    },
  };
  current = handle;

  // Cancel takes the keyboard: the safe choice.
  cancel.focus();
  return handle;
}

/** Ask first, then run `action`. This is the only way a card deletes. */
export function confirmDestructive(content: ConfirmContent, action: () => void): void {
  mountConfirm(content, {
    onCancel: () => closeConfirm(),
    onConfirm: () => {
      closeConfirm();
      action();
    },
  });
}
