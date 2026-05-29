/**
 * Pawsistant Button Card — Editor element (card picker / lovelace editor)
 *
 * Supports configuring multiple buttons per card with add/remove/reorder.
 */

import type { HomeAssistant, PawsistantButtonCardConfig, ButtonConfig } from './types';
import { _escapeHTML, dogNamesFromHass } from './utils';
import { buildRegistry, getMeta, FALLBACK_EVENT_META } from './registry';

export class PawsistantButtonCardEditor extends HTMLElement {
  _config: PawsistantButtonCardConfig = { type: 'custom:pawsistant-button-card', dog: '', buttons: [] };
  __hass: HomeAssistant | null = null;
  _lastDogNamesKey: string = '';

  setConfig(config: PawsistantButtonCardConfig): void {
    // Backward compatibility: migrate single event_type → buttons[]
    const migrated = { ...config };
    if (!migrated.buttons && migrated.event_type) {
      migrated.buttons = [{ event_type: migrated.event_type }];
      delete migrated.event_type;
    }
    if (!migrated.buttons) migrated.buttons = [];
    this._config = migrated;
    this._render();
  }

  get _hass(): HomeAssistant | null { return this.__hass; }
  set hass(h: HomeAssistant | null) {
    this.__hass = h;
    const names = dogNamesFromHass(h);
    const key = names.join(',');
    if (key !== this._lastDogNamesKey) {
      this._lastDogNamesKey = key;
      this._render();
    }
  }

  _render(): void {
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    const cfg = this._config;
    const esc = _escapeHTML;
    const weightUnit = cfg.weight_unit || 'lbs';
    const showTitle = cfg.show_title !== false;
    const buttonsPerRow = cfg.buttons_per_row || 3;

    const dogNames = dogNamesFromHass(this.__hass);

    // Build event type options from registry + fallback
    const { registry } = this.__hass ? buildRegistry(this.__hass) : { registry: {} };
    const allTypes: Record<string, { label: string; emoji: string }> = {};
    for (const [k, v] of Object.entries(FALLBACK_EVENT_META)) {
      allTypes[k] = { label: v.label, emoji: v.emoji };
    }
    for (const [k, v] of Object.entries(registry) as [string, { label: string; emoji: string }][]) {
      allTypes[k] = { label: v.label, emoji: v.emoji };
    }

    // Build button rows HTML
    const buttonRows = (cfg.buttons || []).map((btn, i) => {
      const meta = allTypes[btn.event_type] || { label: btn.event_type, emoji: '?' };
      const isFirst = i === 0;
      const isLast = i === (cfg.buttons.length - 1);
      return `
        <div class="btn-row" data-index="${i}">
          <span class="btn-info">${esc(meta.emoji)} ${esc(meta.label)}</span>
          <span class="btn-actions">
            <button class="icon-btn btn-up" data-index="${i}" ${isFirst ? 'disabled' : ''} title="Move up">&uarr;</button>
            <button class="icon-btn btn-down" data-index="${i}" ${isLast ? 'disabled' : ''} title="Move down">&darr;</button>
            <button class="icon-btn btn-remove" data-index="${i}" title="Remove">&times;</button>
          </span>
        </div>
      `;
    }).join('');

    // Event type dropdown options for adding
    const addOptions = Object.entries(allTypes)
      .sort(([, a], [, b]) => a.label.localeCompare(b.label))
      .map(([k, v]) => `<option value="${esc(k)}">${esc(v.emoji)} ${esc(v.label)} (${esc(k)})</option>`)
      .join('');

    this.shadowRoot!.innerHTML = `
      <style>
        .form { display: flex; flex-direction: column; gap: 14px; padding: 8px 0; }
        .field-label { font-size: 12px; color: var(--secondary-text-color); margin-bottom: 4px; display: block; font-weight: 500; }
        input[type="text"], select {
          width: 100%;
          box-sizing: border-box;
          padding: 8px 10px;
          border: 1px solid var(--divider-color);
          border-radius: 6px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font-size: 14px;
        }
        input:focus, select:focus { outline: 2px solid var(--primary-color); border-color: transparent; }
        .hint { font-size: 11px; color: var(--secondary-text-color); margin-top: 3px; }
        .checkbox-row {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .checkbox-row input[type="checkbox"] {
          width: 18px;
          height: 18px;
          accent-color: var(--primary-color);
        }
        .buttons-section {
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          padding: 8px;
        }
        .btn-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 6px 4px;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
        }
        .btn-row:last-child { border-bottom: none; }
        .btn-info {
          font-size: 14px;
          color: var(--primary-text-color);
        }
        .btn-actions {
          display: flex;
          gap: 4px;
        }
        .icon-btn {
          border: none;
          background: none;
          cursor: pointer;
          font-size: 16px;
          padding: 4px 6px;
          border-radius: 4px;
          color: var(--secondary-text-color);
          line-height: 1;
        }
        .icon-btn:hover:not(:disabled) { background: var(--divider-color); color: var(--primary-text-color); }
        .icon-btn:disabled { opacity: 0.3; cursor: default; }
        .btn-remove:hover:not(:disabled) { color: var(--error-color, #EF5350); }
        .add-row {
          display: flex;
          gap: 8px;
          margin-top: 8px;
        }
        .add-row select { flex: 1; }
        .add-btn {
          padding: 6px 14px;
          border: none;
          border-radius: 6px;
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
          font-weight: 600;
          font-size: 14px;
          cursor: pointer;
        }
        .add-btn:hover { opacity: 0.85; }
        .empty-msg {
          font-size: 13px;
          color: var(--secondary-text-color);
          text-align: center;
          padding: 12px;
        }
        .range-row {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .range-row input[type="range"] {
          flex: 1;
          accent-color: var(--primary-color);
        }
        .range-val {
          font-size: 14px;
          font-weight: 600;
          min-width: 18px;
          text-align: center;
          color: var(--primary-text-color);
        }
      </style>
      <div class="form">
        <div>
          <label class="field-label" for="ed-dog">Pet *</label>
          ${dogNames.length > 0
            ? `<select id="ed-dog" name="dog">
                <option value="">— select a pet —</option>
                ${dogNames.map(n => `<option value="${esc(n)}"${cfg.dog === n ? ' selected' : ''}>${esc(n)}</option>`).join('')}
              </select>`
            : `<input id="ed-dog" name="dog" type="text" value="${esc(cfg.dog || '')}" placeholder="Sharky" />
               <div class="hint">No dogs found — enter a name manually.</div>`
          }
        </div>

        <div>
          <label class="field-label">Buttons</label>
          <div class="buttons-section">
            ${buttonRows || '<div class="empty-msg">No buttons added yet.</div>'}
            <div class="add-row">
              <select id="ed-add-type">
                <option value="">— add event type —</option>
                ${addOptions}
              </select>
              <button class="add-btn" id="ed-add-btn">+</button>
            </div>
          </div>
        </div>

        <div class="checkbox-row">
          <input type="checkbox" id="ed-show-title" name="show_title" ${showTitle ? 'checked' : ''} />
          <label class="field-label" for="ed-show-title" style="margin-bottom:0">Show pet name</label>
        </div>
        <div>
          <label class="field-label" for="ed-weight-unit">Weight unit</label>
          <select id="ed-weight-unit" name="weight_unit">
            <option value="lbs" ${weightUnit === 'lbs' ? 'selected' : ''}>lbs</option>
            <option value="kg" ${weightUnit === 'kg' ? 'selected' : ''}>kg</option>
          </select>
        </div>
        <div>
          <label class="field-label">Buttons per row</label>
          <div class="range-row">
            <input type="range" id="ed-bpr" min="2" max="6" value="${buttonsPerRow}" />
            <span class="range-val" id="ed-bpr-val">${buttonsPerRow}</span>
          </div>
        </div>
      </div>
    `;

    // Attach listeners
    // Dog & weight_unit changes
    this.shadowRoot!.querySelectorAll<HTMLInputElement | HTMLSelectElement>('#ed-dog, #ed-weight-unit').forEach(el => {
      el.addEventListener('change', () => this._scalarChanged());
    });

    // Show title checkbox
    const showTitleCb = this.shadowRoot!.querySelector<HTMLInputElement>('#ed-show-title');
    if (showTitleCb) {
      showTitleCb.addEventListener('change', () => this._scalarChanged());
    }

    // Buttons per row slider
    const bprSlider = this.shadowRoot!.querySelector<HTMLInputElement>('#ed-bpr');
    const bprVal = this.shadowRoot!.querySelector<HTMLSpanElement>('#ed-bpr-val');
    if (bprSlider) {
      bprSlider.addEventListener('input', () => {
        if (bprVal) bprVal.textContent = bprSlider.value;
      });
      bprSlider.addEventListener('change', () => {
        this._scalarChanged();
      });
    }

    // Add button
    const addBtn = this.shadowRoot!.querySelector<HTMLButtonElement>('#ed-add-btn');
    const addSelect = this.shadowRoot!.querySelector<HTMLSelectElement>('#ed-add-type');
    if (addBtn && addSelect) {
      addBtn.addEventListener('click', () => {
        const val = addSelect.value;
        if (!val) return;
        const buttons = [...(this._config.buttons || []), { event_type: val }];
        this._fireConfigChanged({ ...this._config, buttons });
      });
    }

    // Remove buttons
    this.shadowRoot!.querySelectorAll<HTMLButtonElement>('.btn-remove').forEach(el => {
      el.addEventListener('click', () => {
        const idx = parseInt(el.dataset.index!, 10);
        const buttons = [...this._config.buttons];
        buttons.splice(idx, 1);
        this._fireConfigChanged({ ...this._config, buttons });
      });
    });

    // Move up
    this.shadowRoot!.querySelectorAll<HTMLButtonElement>('.btn-up').forEach(el => {
      el.addEventListener('click', () => {
        const idx = parseInt(el.dataset.index!, 10);
        if (idx <= 0) return;
        const buttons = [...this._config.buttons];
        [buttons[idx - 1], buttons[idx]] = [buttons[idx], buttons[idx - 1]];
        this._fireConfigChanged({ ...this._config, buttons });
      });
    });

    // Move down
    this.shadowRoot!.querySelectorAll<HTMLButtonElement>('.btn-down').forEach(el => {
      el.addEventListener('click', () => {
        const idx = parseInt(el.dataset.index!, 10);
        if (idx >= this._config.buttons.length - 1) return;
        const buttons = [...this._config.buttons];
        [buttons[idx], buttons[idx + 1]] = [buttons[idx + 1], buttons[idx]];
        this._fireConfigChanged({ ...this._config, buttons });
      });
    });
  }

  _scalarChanged(): void {
    const newConfig: Record<string, unknown> = { ...this._config };

    // Dog
    const dogEl = this.shadowRoot!.querySelector<HTMLInputElement | HTMLSelectElement>('#ed-dog');
    if (dogEl) {
      const val = dogEl.value.trim();
      if (val) newConfig['dog'] = val;
      else delete newConfig['dog'];
    }

    // Weight unit
    const wuEl = this.shadowRoot!.querySelector<HTMLSelectElement>('#ed-weight-unit');
    if (wuEl) {
      const val = wuEl.value.trim();
      if (val) newConfig['weight_unit'] = val;
      else delete newConfig['weight_unit'];
    }

    // Show title — only persist when false
    const showTitleCb = this.shadowRoot!.querySelector<HTMLInputElement>('#ed-show-title');
    if (showTitleCb) {
      if (showTitleCb.checked) {
        delete newConfig['show_title'];
      } else {
        newConfig['show_title'] = false;
      }
    }

    // Buttons per row
    const bprSlider = this.shadowRoot!.querySelector<HTMLInputElement>('#ed-bpr');
    if (bprSlider) {
      const val = parseInt(bprSlider.value, 10);
      if (val && val !== 3) {
        newConfig['buttons_per_row'] = val;
      } else {
        delete newConfig['buttons_per_row'];
      }
    }

    this._fireConfigChanged(newConfig as unknown as PawsistantButtonCardConfig);
  }

  _fireConfigChanged(config: PawsistantButtonCardConfig): void {
    // Clean up deprecated field
    const clean = { ...config };
    delete clean.event_type;

    this._config = clean;
    this._render();
    this.dispatchEvent(new CustomEvent('config-changed', {
      detail: { config: clean },
      bubbles: true,
      composed: true,
    }));
  }
}

customElements.define('pawsistant-button-card-editor', PawsistantButtonCardEditor);
