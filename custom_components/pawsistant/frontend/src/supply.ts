/**
 * Pawsistant Card — Supplies
 *
 * An event type can use a supply that Home Keeper counts, such as poop bag rolls or
 * medicine tablets. Each log takes a set amount off the count. This module reads the
 * count from Home Keeper's spares `number` entity and draws the parts of the card
 * that show it: the corner badge, the stock line in the log form, the toast after a
 * log, and the Supplies popup.
 *
 * The pure helpers (`stockOf`, `formatCount`, `stockLine`, `badgeHTML`) are kept
 * apart from the DOM code so they are tested on their own.
 */

import type { HomeAssistant, EventMeta, SupplyMeta } from './types';
import { T } from './i18n';
import { _escapeHTML } from './utils';

export type StockStatus = 'ok' | 'low' | 'out' | 'untracked';

export interface Stock {
  count: number;
  unit: string;
  status: StockStatus;
  reorderAt: number | null;
  pack: number | null;
  entityId: string;
}

const STATUSES: StockStatus[] = ['ok', 'low', 'out', 'untracked'];

function num(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/** The count of a supply now, or null when Home Keeper does not count it (yet). */
export function stockOf(hass: HomeAssistant | null, supply: SupplyMeta | undefined): Stock | null {
  if (!hass || !supply || !supply.entity_id) return null;
  const state = hass.states[supply.entity_id];
  if (!state) return null;
  const count = num(state.state);
  if (count === null) return null;
  const attrs = state.attributes || {};
  const status = STATUSES.includes(attrs.status) ? (attrs.status as StockStatus) : 'ok';
  if (status === 'untracked') return null;
  return {
    count,
    unit: String(attrs.unit_of_measurement || ''),
    status,
    reorderAt: num(attrs.reorder_at),
    pack: num(attrs.restock_quantity),
    entityId: supply.entity_id,
  };
}

/** A count for a small space: no trailing zeros, at most 2 decimals. */
export function formatCount(n: number): string {
  return String(Math.round(n * 100) / 100);
}

/** "Takes 1 roll · 3 → 2 left" for the log form. The count stops at zero. */
export function stockLine(stock: Stock, amount: number): string {
  const after = Math.max(0, stock.count - amount);
  const unit = stock.unit ? ` ${stock.unit}` : '';
  return T('supply.line', {
    amount: `${formatCount(amount)}${unit}`,
    before: formatCount(stock.count),
    after: formatCount(after),
  });
}

/** The corner badge on a button, or '' when the type uses no counted supply. */
export function badgeHTML(stock: Stock | null): string {
  if (!stock) return '';
  const cls = stock.status === 'ok' ? '' : ` ${stock.status}`;
  const label = T('supply.badge_aria', { n: formatCount(stock.count) });
  return `<span class="stock-badge${cls}" aria-label="${_escapeHTML(label)}">${formatCount(stock.count)}</span>`;
}

/** CSS for the badge, the stock line and the toast. Both cards add it. */
export const SUPPLY_CSS = `
  .log-btn { position: relative; }
  .stock-badge {
    position: absolute; top: 4px; right: 4px;
    min-width: 18px; padding: 1px 5px; box-sizing: border-box;
    border-radius: 9px; font-size: 10px; font-weight: 700; line-height: 14px;
    text-align: center; font-variant-numeric: tabular-nums;
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color);
    border: 1px solid var(--divider-color, #e0e0e0);
    pointer-events: none;
  }
  .stock-badge.low { background: var(--warning-color, #ffa600); border-color: var(--warning-color, #ffa600); color: #fff; }
  .stock-badge.out { background: var(--error-color, #db4437); border-color: var(--error-color, #db4437); color: #fff; }
  .stock-line {
    display: flex; justify-content: space-between; gap: 8px;
    font-size: 12px; padding: 6px 8px; border-radius: 6px;
    background: var(--secondary-background-color, #f5f5f5);
    color: var(--primary-text-color); font-variant-numeric: tabular-nums;
  }
  .pw-toast {
    display: flex; align-items: center; gap: 10px;
    margin-top: 8px; padding: 9px 12px; border-radius: 10px;
    background: #323232; color: #fff; font-size: 13px; line-height: 1.35;
  }
  .pw-toast .pw-toast-text { flex: 1; }
  .pw-toast .pw-toast-sub { display: block; color: #c7c7c7; font-size: 11.5px; }
  .pw-toast button {
    background: none; border: none; cursor: pointer; padding: 6px 4px;
    color: #80d8ff; font-weight: 600; font-size: 12.5px; min-height: 36px;
  }
  .pw-toast button:focus-visible { outline: 2px solid #80d8ff; }
`;

/** Add a stock line to a log form, before its note field. */
export function addStockLine(form: HTMLElement, stock: Stock | null, amount: number | undefined): void {
  if (!stock || !amount) return;
  const line = document.createElement('div');
  line.className = 'stock-line';
  line.textContent = stockLine(stock, amount);
  const anchor = form.querySelector('.form-field');
  if (anchor) anchor.before(line);
  else form.appendChild(line);
}

/** What the toast says after a log that used a supply. */
export function toastText(label: string, before: Stock, amount: number): { text: string; sub: string } {
  const after = Math.max(0, before.count - amount);
  // The count alone: a unit the user typed ("roll") does not follow a plural.
  const text = T('supply.toast_left', { label, n: formatCount(after) });
  const crossed = before.reorderAt !== null && before.count > before.reorderAt && after <= before.reorderAt;
  return { text, sub: crossed ? T('supply.toast_low') : '' };
}

interface ToastOptions {
  text: string;
  sub?: string;
  onUndo?: () => Promise<unknown> | void;
  timeoutMs?: number;
}

/**
 * Show a toast at the end of *container*. It replaces an earlier one, and it goes
 * after a few seconds. Returns a function that removes it at once.
 */
export function showToast(container: HTMLElement, opts: ToastOptions): () => void {
  container.querySelector('.pw-toast')?.remove();
  const toast = document.createElement('div');
  toast.className = 'pw-toast';
  toast.setAttribute('role', 'status');
  const textEl = document.createElement('span');
  textEl.className = 'pw-toast-text';
  textEl.textContent = opts.text;
  if (opts.sub) {
    const sub = document.createElement('span');
    sub.className = 'pw-toast-sub';
    sub.textContent = opts.sub;
    textEl.appendChild(sub);
  }
  toast.appendChild(textEl);
  const remove = (): void => {
    clearTimeout(timer);
    toast.remove();
  };
  if (opts.onUndo) {
    const undo = document.createElement('button');
    undo.type = 'button';
    undo.textContent = T('supply.undo');
    undo.addEventListener('click', () => {
      undo.disabled = true;
      Promise.resolve(opts.onUndo!()).finally(remove);
    });
    toast.appendChild(undo);
  }
  container.appendChild(toast);
  const timer = setTimeout(remove, opts.timeoutMs ?? 6000);
  return remove;
}

/* ── Supplies popup ───────────────────────────────────────────────── */

export interface SupplyRow {
  label: string;
  emoji: string;
  stock: Stock;
}

/** One row per counted supply that the shown event types use, without repeats. */
export function supplyRows(
  hass: HomeAssistant | null,
  types: { meta: EventMeta; label: string }[],
): SupplyRow[] {
  const seen = new Set<string>();
  const rows: SupplyRow[] = [];
  for (const { meta, label } of types) {
    const stock = stockOf(hass, meta.supply);
    if (!stock || seen.has(stock.entityId)) continue;
    seen.add(stock.entityId);
    rows.push({ label: meta.supply?.name || label, emoji: meta.emoji, stock });
  }
  return rows;
}

/** Set a supply's count through Home Keeper's spares number. */
export function setStock(hass: HomeAssistant, entityId: string, value: number): Promise<unknown> {
  return hass.callService('number', 'set_value', {
    entity_id: entityId,
    value: Math.max(0, Math.round(value * 1000) / 1000),
  });
}

export const SUPPLIES_DIALOG_CSS = `
  .pw-sup-overlay {
    position: fixed; inset: 0; z-index: 999; background: rgba(0,0,0,.45);
    display: flex; align-items: center; justify-content: center;
    padding: 16px; box-sizing: border-box;
  }
  .pw-sup-dialog {
    background: var(--ha-card-background, var(--card-background-color, #fff));
    border-radius: var(--ha-card-border-radius, 12px);
    box-shadow: 0 8px 32px rgba(0,0,0,.3);
    width: min(420px, 100%); max-height: min(80vh, 640px); overflow: auto;
    color: var(--primary-text-color);
  }
  .pw-sup-head {
    display: flex; align-items: center; gap: 8px;
    padding: 10px 10px 8px 16px; border-bottom: 1px solid var(--divider-color, #e0e0e0);
  }
  .pw-sup-title { flex: 1; font-size: 14px; font-weight: 600; }
  .pw-sup-close, .pw-sup-step {
    background: none; border: none; cursor: pointer; color: var(--primary-text-color);
    min-width: 36px; min-height: 36px; border-radius: 50%; font-size: 18px;
  }
  .pw-sup-step { background: var(--secondary-background-color, #f5f5f5); }
  .pw-sup-close:focus-visible, .pw-sup-step:focus-visible, .pw-sup-pack:focus-visible {
    outline: 2px solid var(--primary-color, #03a9f4);
  }
  .pw-sup-row {
    display: grid; grid-template-columns: auto 1fr auto; gap: 4px 10px; align-items: center;
    padding: 10px 16px; border-bottom: 1px solid var(--divider-color, #e0e0e0);
  }
  .pw-sup-row:last-child { border-bottom: none; }
  .pw-sup-name { font-size: 13.5px; }
  .pw-sup-meta { display: block; font-size: 11px; color: var(--secondary-text-color); }
  .pw-sup-count { display: flex; align-items: center; gap: 6px; font-variant-numeric: tabular-nums; }
  .pw-sup-n { min-width: 2.5ch; text-align: center; font-weight: 600; font-size: 15px; }
  .pw-sup-n.low { color: var(--warning-color, #ffa600); }
  .pw-sup-n.out { color: var(--error-color, #db4437); }
  .pw-sup-pack {
    grid-column: 2 / 4; justify-self: end; background: none; border: none; cursor: pointer;
    color: var(--primary-color, #03a9f4); font-weight: 600; font-size: 12px; padding: 6px 0;
  }
`;

/** The popup's markup. Pure, so tests can read it without a DOM round trip. */
export function suppliesDialogHTML(rows: SupplyRow[]): string {
  const body = rows
    .map((row, i) => {
      const s = row.stock;
      const unit = s.unit ? ` ${_escapeHTML(s.unit)}` : '';
      const meta: string[] = [];
      if (s.reorderAt !== null) meta.push(T('supply.reorder_at', { n: formatCount(s.reorderAt) }));
      const cls = s.status === 'ok' ? '' : ` ${s.status}`;
      const pack = s.pack
        ? `<button type="button" class="pw-sup-pack" data-i="${i}" data-act="pack">${_escapeHTML(
            T('supply.add_pack', { n: `${formatCount(s.pack)}${s.unit ? ' ' + s.unit : ''}` }),
          )}</button>`
        : '';
      return `
        <div class="pw-sup-row">
          <span aria-hidden="true">${row.emoji}</span>
          <span class="pw-sup-name">${_escapeHTML(row.label)}
            <span class="pw-sup-meta">${_escapeHTML(meta.join(' · '))}</span></span>
          <span class="pw-sup-count">
            <button type="button" class="pw-sup-step" data-i="${i}" data-act="minus" aria-label="${_escapeHTML(T('supply.remove_one'))}">−</button>
            <span class="pw-sup-n${cls}">${formatCount(s.count)}${unit}</span>
            <button type="button" class="pw-sup-step" data-i="${i}" data-act="plus" aria-label="${_escapeHTML(T('supply.add_one'))}">+</button>
          </span>
          ${pack}
        </div>`;
    })
    .join('');
  return `
    <div class="pw-sup-overlay">
      <div class="pw-sup-dialog" role="dialog" aria-modal="true" aria-label="${_escapeHTML(T('supply.title'))}">
        <div class="pw-sup-head">
          <span class="pw-sup-title">📦 ${_escapeHTML(T('supply.title'))}</span>
          <button type="button" class="pw-sup-close" aria-label="${_escapeHTML(T('supply.close'))}">✕</button>
        </div>
        ${body}
      </div>
    </div>`;
}

/**
 * Open the Supplies popup in *root*. − and + move a count by 1, and "+ pack" adds the
 * pack size. Each press writes through Home Keeper's spares number, so the badge and
 * the Buy task follow. Returns a function that closes the popup.
 */
export function openSuppliesDialog(
  root: ShadowRoot,
  hass: HomeAssistant,
  rows: SupplyRow[],
  onClose: () => void,
): () => void {
  if (!root.querySelector('style[data-pw-supplies]')) {
    const style = document.createElement('style');
    style.setAttribute('data-pw-supplies', '');
    style.textContent = SUPPLIES_DIALOG_CSS;
    root.appendChild(style);
  }
  const holder = document.createElement('div');
  holder.innerHTML = suppliesDialogHTML(rows);
  const overlay = holder.firstElementChild as HTMLElement;
  root.appendChild(overlay);
  const counts = rows.map(r => r.stock.count);

  const close = (): void => {
    overlay.remove();
    document.removeEventListener('keydown', onKey);
    onClose();
  };
  const onKey = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') close();
  };
  document.addEventListener('keydown', onKey);

  overlay.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    if (target === overlay || target.closest('.pw-sup-close')) {
      close();
      return;
    }
    const btn = target.closest<HTMLButtonElement>('button[data-act]');
    if (!btn) return;
    const i = Number(btn.dataset.i);
    const row = rows[i];
    if (!row) return;
    const act = btn.dataset.act;
    const step = act === 'pack' ? row.stock.pack || 0 : act === 'plus' ? 1 : -1;
    const next = Math.max(0, counts[i] + step);
    counts[i] = next;
    const n = overlay.querySelectorAll<HTMLElement>('.pw-sup-n')[i];
    if (n) n.textContent = `${formatCount(next)}${row.stock.unit ? ' ' + row.stock.unit : ''}`;
    setStock(hass, row.stock.entityId, next).catch((err) => {
      console.error('[pawsistant] supply update failed:', err);
    });
  });

  overlay.querySelector<HTMLElement>('.pw-sup-close')?.focus();
  return close;
}
