/**
 * Pawsistant Card — Supplies: the stock badge, the stock line, the toast and the
 * Supplies popup.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  stockOf, formatCount, stockLine, badgeHTML, toastText, showToast,
  supplyRows, suppliesDialogHTML, openSuppliesDialog, setStock, addStockLine,
} from '../src/supply.js';
import { buildRegistry, getMeta } from '../src/registry.js';
import { logEventWithId, updateSupply } from '../src/services.js';

const ENTITY = 'number.pet_supplies_poop_bag_rolls_spares';

function hassWith(state, attributes = {}) {
  return {
    states: {
      [ENTITY]: {
        state,
        attributes: { unit_of_measurement: 'roll', status: 'ok', reorder_at: 1, restock_quantity: 8, ...attributes },
      },
    },
    callService: vi.fn().mockResolvedValue(undefined),
  };
}

const SUPPLY = { entity_id: ENTITY, amount: 1, name: 'Poop bag rolls' };

describe('stockOf', () => {
  it('reads the count, unit, status, reorder point and pack size', () => {
    expect(stockOf(hassWith('3'), SUPPLY)).toEqual({
      count: 3, unit: 'roll', status: 'ok', reorderAt: 1, pack: 8, entityId: ENTITY,
    });
  });

  it('is null without a counted part', () => {
    expect(stockOf(null, SUPPLY)).toBeNull();
    expect(stockOf(hassWith('3'), undefined)).toBeNull();
    expect(stockOf(hassWith('3'), { amount: 1 })).toBeNull();
    expect(stockOf(hassWith('3'), { entity_id: 'number.gone' })).toBeNull();
    expect(stockOf(hassWith('unavailable'), SUPPLY)).toBeNull();
    expect(stockOf(hassWith('3', { status: 'untracked' }), SUPPLY)).toBeNull();
  });

  it('treats an unknown status as ok and missing numbers as null', () => {
    const s = stockOf(hassWith('2', { status: 'weird', reorder_at: null, restock_quantity: '' }), SUPPLY);
    expect(s.status).toBe('ok');
    expect(s.reorderAt).toBeNull();
    expect(s.pack).toBeNull();
  });

  it('keeps the low and out statuses', () => {
    expect(stockOf(hassWith('1', { status: 'low' }), SUPPLY).status).toBe('low');
    expect(stockOf(hassWith('0', { status: 'out' }), SUPPLY).status).toBe('out');
  });

  it('has no unit for plain spares', () => {
    expect(stockOf(hassWith('3', { unit_of_measurement: undefined }), SUPPLY).unit).toBe('');
  });
});

describe('formatCount', () => {
  it('drops trailing zeros and keeps two decimals', () => {
    expect(formatCount(3)).toBe('3');
    expect(formatCount(2.5)).toBe('2.5');
    expect(formatCount(1 / 3)).toBe('0.33');
  });
});

describe('stockLine', () => {
  it('says what the log takes and what stays', () => {
    const s = stockOf(hassWith('3'), SUPPLY);
    expect(stockLine(s, 1)).toBe('Takes 1 roll · 3 → 2 left');
    expect(stockLine(s, 0.5)).toBe('Takes 0.5 roll · 3 → 2.5 left');
  });

  it('stops at zero', () => {
    const s = stockOf(hassWith('1'), SUPPLY);
    expect(stockLine(s, 2)).toBe('Takes 2 roll · 1 → 0 left');
  });

  it('has no unit for plain spares', () => {
    const s = stockOf(hassWith('3', { unit_of_measurement: '' }), SUPPLY);
    expect(stockLine(s, 1)).toBe('Takes 1 · 3 → 2 left');
  });
});

describe('badgeHTML', () => {
  it('is empty without a counted supply', () => {
    expect(badgeHTML(null)).toBe('');
  });

  it('shows the count, coloured by status', () => {
    expect(badgeHTML(stockOf(hassWith('9'), SUPPLY))).toBe(
      '<span class="stock-badge" aria-label="9 left in stock">9</span>',
    );
    expect(badgeHTML(stockOf(hassWith('1', { status: 'low' }), SUPPLY))).toContain('class="stock-badge low"');
    expect(badgeHTML(stockOf(hassWith('0', { status: 'out' }), SUPPLY))).toContain('class="stock-badge out"');
  });
});

describe('toastText', () => {
  it('names what is left', () => {
    const s = stockOf(hassWith('3'), SUPPLY);
    expect(toastText('Roll', s, 1)).toEqual({ text: 'Roll logged · 2 left', sub: '' });
  });

  it('says a Buy task was added when the log crosses the reorder point', () => {
    const s = stockOf(hassWith('2'), SUPPLY);
    expect(toastText('Roll', s, 1).sub).toBe('Low stock: Home Keeper added a Buy task');
  });

  it('says nothing more when it was already low', () => {
    const s = stockOf(hassWith('1', { status: 'low' }), SUPPLY);
    expect(toastText('Roll', s, 1).sub).toBe('');
  });

  it('says nothing more without a reorder point', () => {
    const s = stockOf(hassWith('2', { reorder_at: null }), SUPPLY);
    expect(toastText('Roll', s, 1).sub).toBe('');
  });
});

describe('showToast', () => {
  afterEach(() => vi.useRealTimers());

  it('shows the text and goes after its time', () => {
    vi.useFakeTimers();
    const box = document.createElement('div');
    showToast(box, { text: 'Roll logged · 2 roll left', sub: 'Low', timeoutMs: 1000 });
    const toast = box.querySelector('.pw-toast');
    expect(toast.getAttribute('role')).toBe('status');
    expect(toast.querySelector('.pw-toast-text').textContent).toBe('Roll logged · 2 roll leftLow');
    expect(toast.querySelector('button')).toBeNull();
    vi.advanceTimersByTime(1001);
    expect(box.querySelector('.pw-toast')).toBeNull();
  });

  it('replaces an earlier toast', () => {
    const box = document.createElement('div');
    showToast(box, { text: 'one' });
    showToast(box, { text: 'two' });
    expect(box.querySelectorAll('.pw-toast')).toHaveLength(1);
    expect(box.textContent).toBe('two');
  });

  it('runs Undo once and then goes', async () => {
    const box = document.createElement('div');
    const onUndo = vi.fn().mockResolvedValue(undefined);
    showToast(box, { text: 'Roll logged', onUndo });
    const undo = box.querySelector('.pw-toast button');
    expect(undo.textContent).toBe('Undo');
    undo.click();
    expect(undo.disabled).toBe(true);
    await Promise.resolve();
    await Promise.resolve();
    expect(onUndo).toHaveBeenCalledTimes(1);
    expect(box.querySelector('.pw-toast')).toBeNull();
  });

  it('can be removed at once', () => {
    const box = document.createElement('div');
    const remove = showToast(box, { text: 'x' });
    remove();
    expect(box.querySelector('.pw-toast')).toBeNull();
  });
});

describe('addStockLine', () => {
  it('adds nothing without a stock or an amount', () => {
    const form = document.createElement('div');
    addStockLine(form, null, 1);
    addStockLine(form, stockOf(hassWith('3'), SUPPLY), undefined);
    expect(form.children).toHaveLength(0);
  });

  it('goes at the end of a form with no note field', () => {
    const form = document.createElement('div');
    addStockLine(form, stockOf(hassWith('3'), SUPPLY), 1);
    expect(form.lastElementChild.className).toBe('stock-line');
  });
});

describe('supplyRows', () => {
  it('lists each counted supply once', () => {
    const hass = hassWith('3');
    const roll = { emoji: '🧻', label: 'Roll', color: '', supply: SUPPLY };
    const walk = { emoji: '🦮', label: 'Walk', color: '', supply: SUPPLY };
    const poop = { emoji: '💩', label: 'Poop', color: '' };
    const rows = supplyRows(hass, [
      { meta: roll, label: 'Roll' },
      { meta: walk, label: 'Walk' },
      { meta: poop, label: 'Poop' },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].label).toBe('Poop bag rolls');
    expect(rows[0].emoji).toBe('🧻');
  });

  it('falls back to the type label when the supply has no name', () => {
    const hass = hassWith('3');
    const meta = { emoji: '💊', label: 'Carprofen', color: '', supply: { entity_id: ENTITY, amount: 1 } };
    expect(supplyRows(hass, [{ meta, label: 'Carprofen' }])[0].label).toBe('Carprofen');
  });
});

describe('the Supplies popup', () => {
  it('draws one row per supply with its count and pack', () => {
    const rows = [{ label: 'Poop bag rolls', emoji: '🧻', stock: stockOf(hassWith('1', { status: 'low' }), SUPPLY) }];
    const html = suppliesDialogHTML(rows);
    expect(html).toContain('role="dialog"');
    expect(html).toContain('Poop bag rolls');
    expect(html).toContain('Reorder at 1');
    expect(html).toContain('class="pw-sup-n low">1 roll<');
    expect(html).toContain('+ pack of 8 roll');
  });

  it('has no pack button without a pack size', () => {
    const rows = [{ label: 'Rolls', emoji: '🧻', stock: stockOf(hassWith('3', { restock_quantity: null }), SUPPLY) }];
    expect(suppliesDialogHTML(rows)).not.toContain('data-act="pack"');
  });

  it('escapes the supply name', () => {
    const rows = [{ label: '<b>x</b>', emoji: '🧻', stock: stockOf(hassWith('3'), SUPPLY) }];
    expect(suppliesDialogHTML(rows)).toContain('&lt;b&gt;x&lt;/b&gt;');
  });

  it('writes the count through the spares number', () => {
    const host = document.createElement('div');
    const root = host.attachShadow({ mode: 'open' });
    const hass = hassWith('3');
    const onClose = vi.fn();
    const rows = [{ label: 'Rolls', emoji: '🧻', stock: stockOf(hass, SUPPLY) }];
    openSuppliesDialog(root, hass, rows, onClose);
    const click = (act) => root.querySelector(`button[data-act="${act}"]`).click();

    click('minus');
    expect(hass.callService).toHaveBeenLastCalledWith('number', 'set_value', { entity_id: ENTITY, value: 2 });
    expect(root.querySelector('.pw-sup-n').textContent).toBe('2 roll');
    click('plus');
    click('plus');
    expect(hass.callService).toHaveBeenLastCalledWith('number', 'set_value', { entity_id: ENTITY, value: 4 });
    click('pack');
    expect(hass.callService).toHaveBeenLastCalledWith('number', 'set_value', { entity_id: ENTITY, value: 12 });

    root.querySelector('.pw-sup-close').click();
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(root.querySelector('.pw-sup-overlay')).toBeNull();
  });

  it('never sets a count below zero', () => {
    const host = document.createElement('div');
    const root = host.attachShadow({ mode: 'open' });
    const hass = hassWith('0', { status: 'out' });
    openSuppliesDialog(root, hass, [{ label: 'Rolls', emoji: '🧻', stock: stockOf(hass, SUPPLY) }], () => {});
    root.querySelector('button[data-act="minus"]').click();
    expect(hass.callService).toHaveBeenLastCalledWith('number', 'set_value', { entity_id: ENTITY, value: 0 });
  });

  it('closes on Escape and on the backdrop', () => {
    const host = document.createElement('div');
    const root = host.attachShadow({ mode: 'open' });
    const hass = hassWith('3');
    const onClose = vi.fn();
    openSuppliesDialog(root, hass, [{ label: 'Rolls', emoji: '🧻', stock: stockOf(hass, SUPPLY) }], onClose);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(onClose).toHaveBeenCalledTimes(1);

    openSuppliesDialog(root, hass, [{ label: 'Rolls', emoji: '🧻', stock: stockOf(hass, SUPPLY) }], onClose);
    root.querySelector('.pw-sup-overlay').click();
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('rounds the value it sends', () => {
    const hass = hassWith('3');
    setStock(hass, ENTITY, 1 / 3);
    expect(hass.callService).toHaveBeenLastCalledWith('number', 'set_value', { entity_id: ENTITY, value: 0.333 });
  });
});

describe('the registry carries the supply', () => {
  it('copies supply from the sensor to the button meta', () => {
    const hass = {
      states: {
        'sensor.buddy_timeline': {
          state: '0',
          attributes: {
            dog: 'Buddy',
            event_types: { roll: { name: 'Roll', icon: 'mdi:paper-roll', color: '#888', supply: SUPPLY } },
          },
        },
      },
    };
    const { registry } = buildRegistry(hass);
    expect(registry.roll.supply).toEqual(SUPPLY);
    expect(getMeta('roll', registry).supply).toEqual(SUPPLY);
  });

  it('has no supply for a type without one', () => {
    const hass = {
      states: {
        'sensor.buddy_timeline': {
          state: '0',
          attributes: { dog: 'Buddy', event_types: { poop: { name: 'Poop', icon: 'mdi:emoticon-poop', color: '#888' } } },
        },
      },
    };
    expect(getMeta('poop', buildRegistry(hass).registry).supply).toBeUndefined();
  });
});

describe('service helpers', () => {
  it('logEventWithId asks for the response and returns the id', async () => {
    const hass = { callService: vi.fn().mockResolvedValue({ response: { event_id: 'ev-9' } }) };
    await expect(logEventWithId(hass, 'Buddy', 'roll', { note: 'x' })).resolves.toBe('ev-9');
    expect(hass.callService).toHaveBeenCalledWith(
      'pawsistant', 'log_event', { dog: 'Buddy', event_type: 'roll', note: 'x' }, undefined, true, true,
    );
  });

  it('logEventWithId returns null from an older backend', async () => {
    const hass = { callService: vi.fn().mockResolvedValue(undefined) };
    await expect(logEventWithId(hass, 'Buddy', 'roll')).resolves.toBeNull();
  });

  it('updateSupply calls pawsistant.update_supply', () => {
    const hass = { callService: vi.fn() };
    updateSupply(hass, { event_type: 'roll', stock: 3 });
    expect(hass.callService).toHaveBeenCalledWith('pawsistant', 'update_supply', { event_type: 'roll', stock: 3 });
  });
});
