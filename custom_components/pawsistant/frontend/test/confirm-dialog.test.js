import { afterEach, describe, expect, it, vi } from 'vitest';
import { closeConfirm, confirmDestructive, mountConfirm } from '../src/confirm-dialog.ts';

const content = { title: 'Delete "x"?', body: 'Line 1\nLine 2', confirmLabel: 'Delete entry' };

function mount(over = {}, handlers = {}) {
  const calls = { cancel: 0, confirm: 0 };
  const handle = mountConfirm(
    { ...content, ...over },
    { onCancel: () => (calls.cancel += 1), onConfirm: () => (calls.confirm += 1), ...handlers },
  );
  return { handle, calls };
}
const scrim = () => document.querySelector('.pw-confirm-scrim');
const buttons = () => [...document.querySelectorAll('.pw-confirm-scrim button')];

afterEach(() => {
  closeConfirm();
  document.body.innerHTML = '';
  document.head.querySelector('#pw-confirm-style')?.remove();
});

describe('mountConfirm', () => {
  it('is an alertdialog that names itself and reads its body', () => {
    mount();
    const modal = document.querySelector('.pw-confirm-modal');
    expect(modal.getAttribute('role')).toBe('alertdialog');
    expect(modal.getAttribute('aria-modal')).toBe('true');
    expect(document.getElementById(modal.getAttribute('aria-labelledby')).textContent).toBe(content.title);
    expect(document.getElementById(modal.getAttribute('aria-describedby')).textContent).toBe(content.body);
  });

  it('puts the action word on the red button, and Cancel first', () => {
    mount();
    const [cancel, confirm] = buttons();
    expect(cancel.textContent).toBe('Cancel');
    expect(confirm.textContent).toBe('Delete entry');
    expect(confirm.classList.contains('pw-confirm-danger')).toBe(true);
  });

  it('gives Cancel the keyboard', () => {
    mount();
    expect(document.activeElement).toBe(buttons()[0]);
  });

  it('cancels on Cancel, on Escape and on a tap outside, and never confirms', () => {
    const { calls } = mount();
    buttons()[0].click();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    scrim().click();
    expect(calls).toEqual({ cancel: 3, confirm: 0 });
  });

  it('does not cancel on a tap inside the dialog', () => {
    const { calls } = mount();
    document.querySelector('.pw-confirm-modal').click();
    expect(calls.cancel).toBe(0);
  });

  it('confirms only from the confirm button', () => {
    const { calls } = mount();
    buttons()[1].click();
    expect(calls).toEqual({ cancel: 0, confirm: 1 });
  });

  it('keeps Tab inside the 2 buttons', () => {
    mount();
    const [cancel, confirm] = buttons();
    cancel.focus();
    const tab = new KeyboardEvent('keydown', { key: 'Tab', cancelable: true });
    document.dispatchEvent(tab);
    expect(tab.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(confirm);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', cancelable: true }));
    expect(document.activeElement).toBe(cancel);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, cancelable: true }));
    expect(document.activeElement).toBe(confirm);
  });

  it('takes the scrim and the key listener down on close, and close twice is safe', () => {
    const { handle, calls } = mount();
    handle.close();
    handle.close();
    expect(scrim()).toBeNull();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(calls.cancel).toBe(0);
  });

  it('shows 1 dialog at a time', () => {
    mount();
    mount({ title: 'Second?' });
    expect(document.querySelectorAll('.pw-confirm-scrim')).toHaveLength(1);
    expect(document.querySelector('.pw-confirm-title').textContent).toBe('Second?');
  });

  it('removes itself when the page goes away', () => {
    mount();
    window.dispatchEvent(new Event('pagehide'));
    expect(scrim()).toBeNull();
  });

  it('stops an Escape from reaching a listener below it', () => {
    mount();
    const below = vi.fn();
    document.addEventListener('keydown', below);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    document.removeEventListener('keydown', below);
    expect(below).not.toHaveBeenCalled();
  });

  it('adds its stylesheet once, with every color on a token and no inline style', () => {
    mount();
    mount();
    const sheets = document.head.querySelectorAll('#pw-confirm-style');
    expect(sheets).toHaveLength(1);
    expect(scrim().getAttribute('style')).toBeNull();
    const literal = sheets[0].textContent
      .split('\n')
      .filter((l) => /#[0-9a-f]{3,6}\b|rgba?\(/i.test(l) && !/^\s*--pw-confirm-/.test(l));
    expect(literal).toEqual([]);
  });
});

describe('confirmDestructive', () => {
  it('runs the action only after the confirm button, then closes', () => {
    const run = vi.fn();
    confirmDestructive(content, run);
    expect(run).not.toHaveBeenCalled();
    buttons()[1].click();
    expect(run).toHaveBeenCalledTimes(1);
    expect(scrim()).toBeNull();
  });

  it('never runs the action on Cancel', () => {
    const run = vi.fn();
    confirmDestructive(content, run);
    buttons()[0].click();
    expect(run).not.toHaveBeenCalled();
    expect(scrim()).toBeNull();
  });
});
