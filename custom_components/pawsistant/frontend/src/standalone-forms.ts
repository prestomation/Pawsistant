/**
 * Pawsistant Card — Standalone form dialogs
 *
 * Promise-based form dialogs that work with any container element.
 * NOT tied to PawsistantCard instance — used by PawsistantButtonCard.
 */

import type { HomeAssistant, EventMeta, BackdateFormResult, WeightFormResult, EditFormResult } from './types';
import { logEvent, updateEvent } from './services';
import { _escapeHTML, toDisplayWeight } from './utils';
import { T, TP } from './i18n';

/* ── Form CSS (injected once per shadow root) ───────────────────────── */

const FORM_STYLES = `
  .inline-form {
    margin: 8px 16px 0;
    padding: 14px;
    background: var(--secondary-background-color, #f5f5f5);
    border-radius: 10px;
    border: 1px solid var(--divider-color, #e0e0e0);
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .form-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--primary-text-color);
  }
  .form-field {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .form-label {
    font-size: 12px;
    color: var(--secondary-text-color);
    font-weight: 500;
  }
  .form-label-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .slider-value {
    font-size: 13px;
    font-weight: 700;
    color: var(--primary-color, #2196f3);
  }
  input[type="range"] {
    width: 100%;
    height: 36px;
    accent-color: var(--primary-color, #2196f3);
    cursor: pointer;
  }
  input[type="text"], input[type="number"] {
    width: 100%;
    box-sizing: border-box;
    padding: 10px 12px;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 8px;
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color);
    font-size: 15px;
    font-family: inherit;
    min-height: 44px;
  }
  input[type="text"]:focus, input[type="number"]:focus {
    outline: 2px solid var(--primary-color, #2196f3);
    border-color: transparent;
  }
  .form-actions {
    display: flex;
    gap: 8px;
  }
  .btn-submit {
    flex: 1;
    padding: 12px;
    border: none;
    border-radius: 8px;
    background: var(--primary-color, #2196f3);
    color: var(--text-primary-color, #fff);
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    min-height: 44px;
    transition: opacity 0.15s;
  }
  .btn-submit:active { opacity: 0.8; }
  .btn-cancel {
    padding: 12px 18px;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 8px;
    background: transparent;
    color: var(--secondary-text-color);
    font-size: 14px;
    cursor: pointer;
    min-height: 44px;
    transition: background 0.15s;
  }
  .btn-cancel:active { background: var(--divider-color, #e0e0e0); }
  .form-error {
    color: var(--error-color, #EF5350);
    font-size: 12px;
    padding: 6px 10px;
    border-radius: 6px;
    background: color-mix(in srgb, var(--error-color, #EF5350) 10%, transparent);
    display: none;
  }
  .form-error.visible { display: block; }
  .weight-input-row {
    display: flex;
    align-items: center;
    gap: 0;
  }
  .weight-input-row input {
    flex: 1;
  }
  .weight-unit {
    font-size: 13px;
    color: var(--secondary-text-color);
    align-self: center;
    margin-left: 6px;
    flex-shrink: 0;
  }
`;

/** Inject form CSS into a root (ShadowRoot or document.head), deduplicated. */
export function _ensureFormStyles(root: ShadowRoot | HTMLElement): void {
  if (root.querySelector('[data-pawsistant-forms]')) return;
  const style = document.createElement('style');
  style.setAttribute('data-pawsistant-forms', '');
  style.textContent = FORM_STYLES;
  if (root instanceof ShadowRoot) {
    root.appendChild(style);
  } else {
    root.appendChild(style);
  }
}

/* ── Backdate form ─────────────────────────────────────────────────── */

interface BackdateFormOptions {
  container: HTMLElement;
  meta: EventMeta;
  hass: HomeAssistant;
  dog: string;
  eventType: string;
}

export function openBackdateForm(opts: BackdateFormOptions): Promise<BackdateFormResult | null> {
  const { container, meta, hass, dog, eventType } = opts;
  const root = container.shadowRoot || container;

  _ensureFormStyles(root as ShadowRoot);

  const formWrap = document.createElement('div');
  formWrap.className = 'inline-form';
  formWrap.innerHTML = `
    <div class="form-title">${meta.emoji} ${T('form.log_title', { label: _escapeHTML(meta.label) })}</div>
    <div class="form-field">
      <div class="form-label-row">
        <label class="form-label" for="pbc-minutes-slider">${T('form.minutes_ago')}</label>
        <span class="slider-value" id="pbc-slider-display">${T('time.now')}</span>
      </div>
      <input type="range" id="pbc-minutes-slider" min="0" max="480" step="1" value="0" aria-label="${T('form.minutes_ago')}" />
    </div>
    <div class="form-field">
      <label class="form-label" for="pbc-backdate-note">${T('form.note_optional')}</label>
      <input type="text" id="pbc-backdate-note" placeholder="${T('form.note_placeholder')}" />
    </div>
    <div class="form-error" id="pbc-form-error" role="alert"></div>
    <div class="form-actions">
      <button class="btn-cancel" id="pbc-form-cancel">${T('form.cancel')}</button>
      <button class="btn-submit" id="pbc-form-submit">${T('form.log_event')}</button>
    </div>
  `;
  root.appendChild(formWrap);

  const slider = formWrap.querySelector<HTMLInputElement>('#pbc-minutes-slider')!;
  const display = formWrap.querySelector<HTMLElement>('#pbc-slider-display')!;

  const updateDisplay = (): void => {
    const v = parseInt(slider.value, 10);
    const t = new Date(Date.now() - v * 60000);
    const timeStr = t.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    display.textContent = (v === 0 ? T('time.now') : TP('time.min_ago', v)) + ` \u00b7 ${timeStr}`;
  };
  slider.addEventListener('input', updateDisplay);
  updateDisplay();

  const cleanup = (): void => {
    formWrap.remove();
  };

  return new Promise<BackdateFormResult | null>((resolve) => {
    formWrap.querySelector('#pbc-form-cancel')!.addEventListener('click', () => {
      cleanup();
      resolve(null);
    });

    formWrap.querySelector('#pbc-form-submit')!.addEventListener('click', () => {
      const minutesAgo = parseInt(slider.value, 10);
      const note = formWrap.querySelector<HTMLInputElement>('#pbc-backdate-note')!.value.trim();
      const timestamp = new Date(Date.now() - minutesAgo * 60000).toISOString();

      const extra: Record<string, unknown> = { timestamp };
      if (note) extra['note'] = note;

      logEvent(hass, dog, eventType, extra)
        .then(() => {
          resolve({ timestamp, note: note || undefined, cleanup });
        })
        .catch((err) => {
          const errEl = formWrap.querySelector<HTMLElement>('#pbc-form-error');
          if (errEl) {
            errEl.textContent = T('form.error.log_event');
            errEl.classList.add('visible');
          }
          console.error('[pawsistant-button-card] backdate failed:', err);
        });
    });

    // Focus first input after brief delay
    setTimeout(() => {
      const first = formWrap.querySelector<HTMLElement>('input');
      if (first) first.focus();
    }, 100);
  });
}

/* ── Weight form ───────────────────────────────────────────────────── */

interface WeightFormOptions {
  container: HTMLElement;
  meta: EventMeta;
  hass: HomeAssistant;
  dog: string;
  currentWeight?: number | null;
  displayUnit?: string;
}

export function openWeightForm(opts: WeightFormOptions): Promise<WeightFormResult | null> {
  const { container, meta, hass, dog } = opts;
  const displayUnit = opts.displayUnit || 'lbs';
  const currentWeight = opts.currentWeight ?? null;
  const root = container.shadowRoot || container;

  _ensureFormStyles(root as ShadowRoot);

  const formWrap = document.createElement('div');
  formWrap.className = 'inline-form';
  formWrap.innerHTML = `
    <div class="form-title">\u2696\uFE0F ${T('form.log_weight_title')}</div>
    <div class="form-field">
      <label class="form-label" for="pbc-weight-input">${T('form.weight_label', { unit: _escapeHTML(displayUnit) })}</label>
      <div class="weight-input-row">
        <input type="number" id="pbc-weight-input" min="1" max="999" step="0.1"
          inputmode="decimal"
          value="${currentWeight !== null ? currentWeight : ''}"
          placeholder="0.0" />
        <span class="weight-unit">${_escapeHTML(displayUnit)}</span>
      </div>
    </div>
    <div class="form-error" id="pbc-form-error" role="alert"></div>
    <div class="form-actions">
      <button class="btn-cancel" id="pbc-form-cancel">${T('form.cancel')}</button>
      <button class="btn-submit" id="pbc-form-submit">${T('form.log_weight_title')}</button>
    </div>
  `;
  root.appendChild(formWrap);

  const cleanup = (): void => {
    formWrap.remove();
  };

  return new Promise<WeightFormResult | null>((resolve) => {
    formWrap.querySelector('#pbc-form-cancel')!.addEventListener('click', () => {
      cleanup();
      resolve(null);
    });

    formWrap.querySelector('#pbc-form-submit')!.addEventListener('click', () => {
      const weightInput = formWrap.querySelector<HTMLInputElement>('#pbc-weight-input')!;
      const value = parseFloat(weightInput.value);
      if (isNaN(value) || value < 1 || value > 999) {
        weightInput.style.outline = '2px solid var(--error-color, #ef5350)';
        weightInput.focus();
        return;
      }
      // Convert kg to lbs for storage if needed
      const valueLbs = displayUnit === 'kg' ? Math.round(value * 2.20462 * 10) / 10 : value;

      logEvent(hass, dog, 'weight', { value: valueLbs })
        .then(() => {
          resolve({ value: valueLbs, cleanup });
        })
        .catch((err) => {
          const errEl = formWrap.querySelector<HTMLElement>('#pbc-form-error');
          if (errEl) {
            errEl.textContent = T('form.error.log_weight');
            errEl.classList.add('visible');
          }
          console.error('[pawsistant-button-card] weight failed:', err);
        });
    });

    setTimeout(() => {
      const first = formWrap.querySelector<HTMLElement>('input');
      if (first) first.focus();
    }, 100);
  });
}

/* ── Edit form ─────────────────────────────────────────────────────── */

interface EditFormOptions {
  container: HTMLElement;
  hass: HomeAssistant;
  meta: EventMeta;
  eventType: string;
  eventId: string;
  timestamp?: string;
  note?: string;
  value?: string;
  displayUnit?: string;
}

export function openEditForm(opts: EditFormOptions): Promise<EditFormResult | null> {
  const { container, hass, meta, eventType, eventId } = opts;
  const displayUnit = opts.displayUnit || 'lbs';
  const isWeight = eventType === 'weight';
  const root = container.shadowRoot || container;

  _ensureFormStyles(root as ShadowRoot);

  // Calculate minutes ago from timestamp
  let minutesAgo = 0;
  if (opts.timestamp) {
    const diff = Date.now() - new Date(opts.timestamp).getTime();
    minutesAgo = Math.max(0, Math.round(diff / 60000));
  }

  const formWrap = document.createElement('div');
  formWrap.className = 'inline-form';

  if (isWeight) {
    const displayVal = opts.value
      ? (displayUnit === 'kg' ? Math.round(Number(opts.value) / 2.20462 * 10) / 10 : opts.value)
      : '';
    formWrap.innerHTML = `
      <div class="form-title">⚖️ ${T('form.edit_weight_title')}</div>
      <div class="form-field">
        <label class="form-label" for="pbc-edit-weight-input">${T('form.weight_label', { unit: _escapeHTML(displayUnit) })}</label>
        <div class="weight-input-row">
          <input type="number" id="pbc-edit-weight-input" min="1" max="999" step="0.1"
            inputmode="decimal"
            value="${displayVal}"
            placeholder="0.0" />
          <span class="weight-unit">${_escapeHTML(displayUnit)}</span>
        </div>
      </div>
      <div class="form-error" id="pbc-edit-form-error" role="alert"></div>
      <div class="form-actions">
        <button class="btn-cancel" id="pbc-edit-form-cancel">${T('form.cancel')}</button>
        <button class="btn-submit" id="pbc-edit-form-submit">${T('form.update_weight')}</button>
      </div>
    `;
  } else {
    formWrap.innerHTML = `
      <div class="form-title">${meta.emoji} ${T('form.edit_title', { label: _escapeHTML(meta.label) })}</div>
      <div class="form-field">
        <div class="form-label-row">
          <label class="form-label" for="pbc-edit-minutes-slider">${T('form.minutes_ago')}</label>
          <span class="slider-value" id="pbc-edit-slider-display">${T('time.now')}</span>
        </div>
        <input type="range" id="pbc-edit-minutes-slider" min="0" max="480" step="1" value="${minutesAgo}" aria-label="${T('form.minutes_ago')}" />
      </div>
      <div class="form-field">
        <label class="form-label" for="pbc-edit-note">${T('form.note_optional')}</label>
        <input type="text" id="pbc-edit-note" placeholder="${_escapeHTML(T('form.note_placeholder'))}" value="${_escapeHTML(opts.note || '')}" />
      </div>
      <div class="form-error" id="pbc-edit-form-error" role="alert"></div>
      <div class="form-actions">
        <button class="btn-cancel" id="pbc-edit-form-cancel">${T('form.cancel')}</button>
        <button class="btn-submit" id="pbc-edit-form-submit">${T('form.update_event')}</button>
      </div>
    `;
  }
  root.appendChild(formWrap);

  const cleanup = (): void => {
    formWrap.remove();
  };

  const showError = (): void => {
    const errEl = formWrap.querySelector<HTMLElement>('#pbc-edit-form-error');
    if (errEl) {
      errEl.textContent = T('form.error.update_event');
      errEl.classList.add('visible');
    }
  };

  if (!isWeight) {
    const slider = formWrap.querySelector<HTMLInputElement>('#pbc-edit-minutes-slider')!;
    const display = formWrap.querySelector<HTMLElement>('#pbc-edit-slider-display')!;
    const updateDisplay = (): void => {
      const v = parseInt(slider.value, 10);
      const t = new Date(Date.now() - v * 60000);
      const timeStr = t.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
      display.textContent = (v === 0 ? T('time.now') : TP('time.min_ago', v)) + ` · ${timeStr}`;
    };
    slider.addEventListener('input', updateDisplay);
    updateDisplay();
  }

  return new Promise<EditFormResult | null>((resolve) => {
    formWrap.querySelector('#pbc-edit-form-cancel')!.addEventListener('click', () => {
      cleanup();
      resolve(null);
    });

    formWrap.querySelector('#pbc-edit-form-submit')!.addEventListener('click', () => {
      if (isWeight) {
        const weightInput = formWrap.querySelector<HTMLInputElement>('#pbc-edit-weight-input')!;
        const value = parseFloat(weightInput.value);
        if (isNaN(value) || value < 1 || value > 999) {
          weightInput.style.outline = '2px solid var(--error-color, #ef5350)';
          weightInput.focus();
          return;
        }
        // Convert kg to lbs for storage if needed
        const valueLbs = displayUnit === 'kg' ? Math.round(value * 2.20462 * 10) / 10 : value;
        updateEvent(hass, eventId, { value: valueLbs })
          .then(() => resolve({ cleanup }))
          .catch((err) => {
            showError();
            console.error('[pawsistant-button-card] update weight failed:', err);
          });
      } else {
        const slider = formWrap.querySelector<HTMLInputElement>('#pbc-edit-minutes-slider')!;
        const minutes = parseInt(slider.value, 10);
        const note = formWrap.querySelector<HTMLInputElement>('#pbc-edit-note')!.value.trim();
        const timestamp = new Date(Date.now() - minutes * 60000).toISOString();
        // note is always sent — empty string clears an existing note
        updateEvent(hass, eventId, { timestamp, note })
          .then(() => resolve({ cleanup }))
          .catch((err) => {
            showError();
            console.error('[pawsistant-button-card] update event failed:', err);
          });
      }
    });

    setTimeout(() => {
      const first = formWrap.querySelector<HTMLElement>('input');
      if (first) first.focus();
    }, 100);
  });
}
