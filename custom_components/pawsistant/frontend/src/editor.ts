/**
 * Pawsistant Card — Editor element (card picker / lovelace editor)
 */

import type { HomeAssistant, PawsistantCardConfig } from './types';
import { _escapeHTML } from './utils';

export class PawsistantCardEditor extends HTMLElement {
  _config: PawsistantCardConfig = { type: 'custom:pawsistant-card', dog: '' };
  __hass: HomeAssistant | null = null;
  _lastDogNamesKey: string = '';

  setConfig(config: PawsistantCardConfig) {
    this._config = { ...config };
    this._render();
  }

  get _hass() { return this.__hass; }
  set hass(h: HomeAssistant | null) {
    this.__hass = h;
    // Re-render only if the available dog list changed (avoids thrashing).
    const names = this._dogNamesFromHass(h);
    const key = names.join(',');
    if (key !== this._lastDogNamesKey) {
      this._lastDogNamesKey = key;
      this._render();
    }
  }

  _dogNamesFromHass(h: HomeAssistant | null): string[] {
    if (!h) return [];
    const seen = new Set<string>();
    for (const state of Object.values(h.states || {})) {
      const dog = state.attributes && state.attributes.dog;
      if (dog) seen.add(dog as string);
    }
    return [...seen].sort();
  }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    const cfg = this._config;
    const esc = _escapeHTML;
    const weightUnit = cfg.weight_unit || 'lbs';

    // Discover registered dog names from any sensor's `dog` attribute.
    // This is rename-safe: doesn't depend on entity ID patterns.
    const dogNames = this._dogNamesFromHass(this.__hass);



    this.shadowRoot!.innerHTML = `
      <style>
        .form { display: flex; flex-direction: column; gap: 14px; padding: 8px 0; }
        .field-label { font-size: 12px; color: var(--secondary-text-color); margin-bottom: 4px; display: block; font-weight: 500; }
        input[type="text"], input[type="number"], select {
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

      </style>
      <div class="form">
        <div>
          <label class="field-label" for="ed-dog">Pet *</label>
          ${dogNames.length > 0
            ? `<select id="ed-dog" name="dog">
                <option value="">— select a pet —</option>
                ${dogNames.map(n => `<option value="${esc(n)}"${cfg.dog === n ? ' selected' : ''}>${esc(n)}</option>`).join('')}
              </select>`
            : `<input id="ed-dog" name="dog" value="${esc(cfg.dog || '')}" placeholder="Sharky" />
               <div class="hint">No dogs found — enter a name manually or set up dogs via the integration options.</div>`
          }
        </div>
        <div>
          <label class="field-label" for="ed-weight-unit">Weight unit</label>
          <select id="ed-weight-unit" name="weight_unit">
            <option value="lbs" ${weightUnit === 'lbs' ? 'selected' : ''}>lbs</option>
            <option value="kg" ${weightUnit === 'kg' ? 'selected' : ''}>kg</option>
          </select>
        </div>

      </div>
    `;

    // Attach listeners on text/select inputs
    this.shadowRoot!.querySelectorAll<HTMLInputElement>('input[type="text"], input[type="number"], select').forEach(el => {
      el.addEventListener('change', () => this._valueChanged());
    });


  }

  _valueChanged() {
    const newConfig = { ...this._config } as Record<string, unknown>;

    // Scalar inputs
    this.shadowRoot!.querySelectorAll<HTMLInputElement>('input[type="text"], input[type="number"], select').forEach(el => {
      const key = el.name;
      const val = el.value.trim();
      if (val) {
        newConfig[key] = val;
      } else {
        delete newConfig[key];
      }
    });

    this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: newConfig }, bubbles: true, composed: true }));
  }
}
