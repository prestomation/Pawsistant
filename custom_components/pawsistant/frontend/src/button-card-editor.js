/**
 * Pawsistant Button Card — Visual editor
 */
import { buildRegistry, FALLBACK_EVENT_META, getMeta } from './registry.js';
import { _escapeHTML } from './utils.js';

class PawsistantButtonCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(h) {
    this.__hass = h;
    const names = this._dogNames(h).join(',');
    if (names !== this._lastDogNames) {
      this._lastDogNames = names;
      this._render();
    }
  }

  _dogNames(h) {
    if (!h || !h.states) return [];
    const seen = new Set();
    for (const s of Object.values(h.states)) {
      const d = s.attributes && s.attributes.dog;
      if (d) seen.add(d);
    }
    return [...seen].sort();
  }

  _eventTypes(h) {
    const { registry } = buildRegistry(h);
    const merged = { ...FALLBACK_EVENT_META, ...(registry || {}) };
    return Object.keys(merged).sort().map(key => ({ key, meta: getMeta(key, registry) }));
  }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    const cfg = this._config;
    const esc = _escapeHTML;
    const dogs = this._dogNames(this.__hass);
    const types = this._eventTypes(this.__hass);

    const markup = `
      <style>
        .form { display: flex; flex-direction: column; gap: 14px; padding: 8px 0; }
        .field-label { font-size: 12px; color: var(--secondary-text-color); display: block; margin-bottom: 4px; font-weight: 500; }
        input[type="text"], select {
          width: 100%; box-sizing: border-box; padding: 8px 10px;
          border: 1px solid var(--divider-color); border-radius: 6px;
          background: var(--card-background-color); color: var(--primary-text-color); font-size: 14px; }
        .hint { font-size: 11px; color: var(--secondary-text-color); margin-top: 3px; }
        .check { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--primary-text-color); }
      </style>
      <div class="form">
        <div>
          <label class="field-label" for="bc-dog">Pet *</label>
          ${dogs.length > 0
            ? `<select id="bc-dog" name="dog">
                <option value="">— select a pet —</option>
                ${dogs.map(n => `<option value="${esc(n)}"${cfg.dog === n ? ' selected' : ''}>${esc(n)}</option>`).join('')}
              </select>`
            : `<input id="bc-dog" name="dog" value="${esc(cfg.dog || '')}" placeholder="Sharky" />
               <div class="hint">No pets registered — enter a name manually.</div>`
          }
        </div>
        <div>
          <label class="field-label" for="bc-type">Event type *</label>
          <select id="bc-type" name="event_type">
            <option value="">— select an event type —</option>
            ${types.map(t => {
              const label = t.meta.label || t.key;
              const display = t.meta.emoji ? `${t.meta.emoji} ${label}` : label;
              return `<option value="${esc(t.key)}"${cfg.event_type === t.key ? ' selected' : ''}>${esc(display)}</option>`;
            }).join('')}
          </select>
        </div>
        <label class="check">
          <input type="checkbox" name="show_title" ${cfg.show_title !== false ? 'checked' : ''} />
          <span>Show pet name as title</span>
        </label>
        <div>
          <label class="check">
            <input type="checkbox" name="haptics" aria-describedby="bc-haptics-hint" ${cfg.haptics ? 'checked' : ''} />
            <span>Enable haptic feedback on long-press</span>
          </label>
          <div class="hint" id="bc-haptics-hint">Vibrates briefly when a button is held. Silent on devices that do not support vibration.</div>
        </div>
      </div>
    `;
    // Trusted template: static HTML with all interpolated values run through _escapeHTML.
    this.shadowRoot.innerHTML = markup; // safe: all interpolated values are _escapeHTML'd

    this.shadowRoot.querySelectorAll('input, select').forEach(el => {
      el.addEventListener('change', () => this._valueChanged());
    });
  }

  _valueChanged() {
    const n = { ...this._config };
    this.shadowRoot.querySelectorAll('input[type="text"], select').forEach(el => {
      const v = el.value.trim();
      if (v) n[el.name] = v; else delete n[el.name];
    });
    this.shadowRoot.querySelectorAll('input[type="checkbox"]').forEach(el => {
      if (el.name === 'show_title') {
        // show_title defaults to true — only persist when user unchecks
        if (!el.checked) n.show_title = false; else delete n.show_title;
      } else {
        if (el.checked) n[el.name] = true; else delete n[el.name];
      }
    });
    this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: n }, bubbles: true, composed: true }));
  }
}

if (!customElements.get('pawsistant-button-card-editor')) {
  customElements.define('pawsistant-button-card-editor', PawsistantButtonCardEditor);
}
