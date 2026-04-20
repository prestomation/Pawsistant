/**
 * Pawsistant Card — Form module
 *
 * Promise-based dialogs for backdate and weight entry. Appends the form to the
 * provided container (inline) or creates a floating dialog on document.body.
 *
 * Lifecycle: on cancel the form DOM is removed internally and the promise
 * resolves to `null`. On submit the promise resolves with the form values plus
 * a `cleanup` function — the caller owns teardown so the form stays mounted
 * long enough to display validation/service errors via `#form-error`.
 */
import { _escapeHTML } from './utils.js';

const FORM_STYLE = `
  .pawsistant-form { display: flex; flex-direction: column; gap: 12px; padding: 12px;
    background: var(--card-background-color, #fff); border-radius: 10px; }
  .pawsistant-form .form-title { font-size: 15px; font-weight: 600; color: var(--primary-text-color); }
  .pawsistant-form .form-field { display: flex; flex-direction: column; gap: 4px; }
  .pawsistant-form .form-label-row { display: flex; justify-content: space-between; align-items: baseline; }
  .pawsistant-form .form-label { font-size: 12px; color: var(--secondary-text-color); }
  .pawsistant-form .slider-value { font-size: 12px; color: var(--primary-text-color); font-weight: 500; }
  .pawsistant-form input[type="range"] { width: 100%; }
  .pawsistant-form input[type="text"], .pawsistant-form input[type="number"] {
    width: 100%; box-sizing: border-box; padding: 8px 10px;
    border: 1px solid var(--divider-color, #e0e0e0); border-radius: 6px;
    background: var(--card-background-color); color: var(--primary-text-color); font-size: 14px; }
  .pawsistant-form .weight-input-row { display: flex; align-items: center; gap: 6px; }
  .pawsistant-form .weight-unit { color: var(--secondary-text-color); font-size: 13px; }
  .pawsistant-form .form-error { color: var(--error-color, #ef5350); font-size: 12px; min-height: 14px; }
  .pawsistant-form .form-actions { display: flex; gap: 8px; justify-content: flex-end; }
  .pawsistant-form .btn-cancel, .pawsistant-form .btn-submit {
    padding: 8px 14px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; }
  .pawsistant-form .btn-cancel { background: var(--secondary-background-color, #f5f5f5);
    color: var(--primary-text-color); }
  .pawsistant-form .btn-submit { background: var(--primary-color, #1976d2); color: #fff; }
  .pawsistant-form-dialog { position: fixed; inset: 0; display: flex;
    align-items: center; justify-content: center; background: rgba(0,0,0,0.35);
    z-index: 9999; padding: 16px; box-sizing: border-box; }
  .pawsistant-form-dialog .pawsistant-form { max-width: 360px; width: 100%;
    box-shadow: 0 8px 24px rgba(0,0,0,0.2); }
`;

function _hasInjectedStyle(root) {
  // Works for both ShadowRoot and Document.
  return !!(root && typeof root.querySelector === 'function'
    && root.querySelector('style[data-pawsistant-forms]'));
}

function _ensureStyles(container) {
  if (typeof document === 'undefined') return;
  // Determine where the form will live so styles cross the shadow boundary.
  const root = container && typeof container.getRootNode === 'function'
    ? container.getRootNode()
    : document;
  const hasShadowRoot = typeof ShadowRoot !== 'undefined';
  if (hasShadowRoot && root instanceof ShadowRoot) {
    if (_hasInjectedStyle(root)) return;
    const style = document.createElement('style');
    style.setAttribute('data-pawsistant-forms', '');
    style.textContent = FORM_STYLE;
    root.appendChild(style);
    return;
  }
  if (_hasInjectedStyle(document)) return;
  const style = document.createElement('style');
  style.setAttribute('data-pawsistant-forms', '');
  style.textContent = FORM_STYLE;
  document.head.appendChild(style);
}

function _mountForm(container, htmlContent) {
  _ensureStyles(container);
  const formEl = document.createElement('div');
  formEl.className = 'pawsistant-form';
  // Trusted template: markup + _escapeHTML'd user values only
  formEl.innerHTML = htmlContent; // safe: all interpolated values are _escapeHTML'd
  if (container) {
    container.appendChild(formEl);
    return { formEl, cleanup: () => formEl.remove() };
  }

  const dialog = document.createElement('div');
  dialog.className = 'pawsistant-form-dialog';
  dialog.appendChild(formEl);
  document.body.appendChild(dialog);
  return { formEl, cleanup: () => dialog.remove() };
}

export function openBackdateForm({ container = null, meta, defaults = {} }) {
  return new Promise((resolve) => {
    const noteDefault = defaults.note || '';
    const template = `
      <div class="form-title">${_escapeHTML(meta.emoji || '')} Log ${_escapeHTML(meta.label || '')}</div>
      <div class="form-field">
        <div class="form-label-row">
          <label class="form-label" for="minutes-slider">Minutes ago</label>
          <span class="slider-value" id="slider-display">Now</span>
        </div>
        <input type="range" id="minutes-slider" min="0" max="480" step="1" value="0" aria-label="Minutes ago" />
      </div>
      <div class="form-field">
        <label class="form-label" for="backdate-note">Note (optional)</label>
        <input type="text" id="backdate-note" placeholder="Add a note" value="${_escapeHTML(noteDefault)}" />
      </div>
      <div class="form-error" id="form-error" role="alert"></div>
      <div class="form-actions">
        <button class="btn-cancel" id="form-cancel">Cancel</button>
        <button class="btn-submit" id="form-submit">Log Event</button>
      </div>
    `;
    const { formEl, cleanup } = _mountForm(container, template);

    const slider = formEl.querySelector('#minutes-slider');
    const display = formEl.querySelector('#slider-display');
    const updateDisplay = () => {
      const v = parseInt(slider.value, 10);
      const t = new Date(Date.now() - v * 60000);
      const timeStr = t.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
      display.textContent = (v === 0 ? 'Now' : v === 1 ? '1 min ago' : `${v} min ago`) + ` · ${timeStr}`;
    };
    slider.addEventListener('input', updateDisplay);
    updateDisplay();

    formEl.querySelector('#form-cancel').addEventListener('click', () => {
      cleanup();
      resolve(null);
    });
    formEl.querySelector('#form-submit').addEventListener('click', () => {
      const minutesAgo = parseInt(slider.value, 10);
      const note = formEl.querySelector('#backdate-note').value.trim();
      const timestamp = new Date(Date.now() - minutesAgo * 60000).toISOString();
      // Leave form mounted so the caller can surface errors via #form-error.
      // The caller is responsible for invoking cleanup() when done.
      resolve({ timestamp, note: note || undefined, cleanup });
    });
  });
}

export function openWeightForm({ container = null, meta, currentWeight = null, displayUnit = 'lbs' }) {
  return new Promise((resolve) => {
    const unitSafe = displayUnit === 'kg' ? 'kg' : 'lbs';
    const prefill = currentWeight !== null && currentWeight !== undefined ? currentWeight : '';
    const template = `
      <div class="form-title">${_escapeHTML(meta.emoji || '')} Log ${_escapeHTML(meta.label || 'Weight')}</div>
      <div class="form-field">
        <label class="form-label" for="weight-input">Weight (${_escapeHTML(unitSafe)})</label>
        <div class="weight-input-row">
          <input type="number" id="weight-input" min="1" max="999" step="0.1"
            inputmode="decimal" value="${_escapeHTML(String(prefill))}" placeholder="0.0" />
          <span class="weight-unit">${_escapeHTML(unitSafe)}</span>
        </div>
      </div>
      <div class="form-error" id="form-error" role="alert"></div>
      <div class="form-actions">
        <button class="btn-cancel" id="form-cancel">Cancel</button>
        <button class="btn-submit" id="form-submit">Log Weight</button>
      </div>
    `;
    const { formEl, cleanup } = _mountForm(container, template);

    formEl.querySelector('#form-cancel').addEventListener('click', () => {
      cleanup();
      resolve(null);
    });

    formEl.querySelector('#form-submit').addEventListener('click', () => {
      const input = formEl.querySelector('#weight-input');
      const value = parseFloat(input.value);
      if (isNaN(value) || value < 1 || value > 999) {
        input.style.outline = '2px solid var(--error-color, #ef5350)';
        input.focus();
        return;
      }
      const valueLbs = unitSafe === 'kg' ? Math.round(value * 2.20462 * 10) / 10 : value;
      // Leave form mounted so the caller can surface errors via #form-error.
      // The caller is responsible for invoking cleanup() when done.
      resolve({ value: valueLbs, timestamp: new Date().toISOString(), note: undefined, cleanup });
    });
  });
}
