/**
 * Pawsistant Button Card — single-button Lovelace card
 *
 * Config:
 *   dog: <required string>
 *   event_type: <required string>
 *   show_title: <optional bool, default true>
 *   haptics: <optional bool, default false>
 */
import { buildRegistry, getMeta, FALLBACK_EVENT_META } from './registry.js';
import { findEntitiesByDog, stateNum, stateAttr, toDisplayWeight } from './utils.js';
import { logEvent } from './services.js';
import { renderPawsistantButton } from './button.js';
import { openBackdateForm, openWeightForm } from './forms.js';
import './button-card-editor.js';

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'pawsistant-button-card',
  name: 'Pawsistant Button',
  description: 'Single-button card for a specific Pawsistant action',
  preview: true,
});

class PawsistantButtonCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass = null;
    this._timers = [];
    this._buttonCleanup = null;
    this._lastHash = null;
    this._activeForm = null;
  }

  setConfig(config) {
    this._config = { ...config };
    this._lastHash = null;
    this._render();
  }

  set hass(h) {
    this._hass = h;
    if (this._activeForm) return;
    const hash = this._computeHash(h, this._config);
    if (hash === this._lastHash) return;
    this._lastHash = hash;
    this._render();
  }
  get hass() { return this._hass; }

  _computeHash(hass, cfg) {
    if (!hass || !hass.states) return 'no-hass';
    const ent = findEntitiesByDog(hass, cfg.dog || '');
    const parts = [
      cfg.dog || '',
      cfg.event_type || '',
      cfg.show_title === false ? '0' : '1',
      cfg.haptics ? '1' : '0',
      cfg.weight_unit || 'lbs',
      this._resolveDogExists(hass, cfg.dog || '') ? '1' : '0',
      stateAttr(hass, ent.timeline, 'event_types') ? JSON.stringify(stateAttr(hass, ent.timeline, 'event_types')) : '',
      stateAttr(hass, ent.timeline, 'button_metrics') ? JSON.stringify(stateAttr(hass, ent.timeline, 'button_metrics')) : '',
      (hass.states[ent.poop_count] || {}).state || '',
      (hass.states[ent.pee_count] || {}).state || '',
      (hass.states[ent.medicine_days] || {}).state || '',
      (hass.states[ent.weight] || {}).state || '',
      stateAttr(hass, ent.timeline, 'last_' + (cfg.event_type || '') + '_ts') || '',
    ];
    return parts.join('|');
  }

  static getConfigElement() {
    return document.createElement('pawsistant-button-card-editor');
  }

  static getStubConfig(hass) {
    const dogs = PawsistantButtonCard._listDogs(hass);
    return {
      type: 'custom:pawsistant-button-card',
      dog: dogs[0] || 'MyDog',
      event_type: 'poop',
    };
  }

  static _listDogs(hass) {
    if (!hass || !hass.states) return [];
    const seen = new Set();
    for (const s of Object.values(hass.states)) {
      const d = s.attributes && s.attributes.dog;
      if (d) seen.add(d);
    }
    return [...seen].sort();
  }

  getCardSize() { return 2; }

  disconnectedCallback() {
    if (this._buttonCleanup) this._buttonCleanup();
    this._timers.forEach(t => clearTimeout(t));
    this._timers.length = 0;
  }

  _renderError(message) {
    const style = document.createElement('style');
    style.textContent = `.err { padding: 14px; background: var(--error-color, #ef5350);
      color: #fff; border-radius: 8px; font-size: 13px; }`;
    const card = document.createElement('ha-card');
    const err = document.createElement('div');
    err.className = 'err';
    err.textContent = `Pawsistant: ${message}`;
    card.appendChild(err);
    while (this.shadowRoot.firstChild) this.shadowRoot.removeChild(this.shadowRoot.firstChild);
    this.shadowRoot.appendChild(style);
    this.shadowRoot.appendChild(card);
  }

  _resolveDogExists(hass, dog) {
    if (!hass || !hass.states) return false;
    const needle = dog.toLowerCase();
    for (const s of Object.values(hass.states)) {
      const d = s.attributes && s.attributes.dog;
      if (d && d.toLowerCase() === needle) return true;
    }
    return false;
  }

  _metricText(hass, cfg, type) {
    const ent = findEntitiesByDog(hass, cfg.dog);
    const metrics = stateAttr(hass, ent.timeline, 'button_metrics') || {};
    const metric = metrics[type] || 'daily_count';
    const weightUnit = cfg.weight_unit || 'lbs';

    if (metric === 'daily_count') {
      const key = type === 'poop' ? 'poop_count' : type === 'pee' ? 'pee_count' : null;
      const entity = key ? ent[key] : null;
      const n = entity ? stateNum(hass, entity) : null;
      if (n !== null) return `${n} today`;
    } else if (metric === 'days_since') {
      const entity = type === 'medicine' ? ent.medicine_days : null;
      const d = entity ? stateNum(hass, entity) : null;
      if (d !== null) return `${Math.floor(d)}d`;
    } else if (metric === 'last_value') {
      const w = toDisplayWeight(stateNum(hass, ent.weight), weightUnit);
      if (w !== null) return `${w} ${weightUnit}`;
    } else if (metric === 'hours_since') {
      const lastTs = stateAttr(hass, ent.timeline, 'last_' + type + '_ts');
      if (lastTs) {
        const hrs = Math.floor((Date.now() - new Date(lastTs).getTime()) / 3600000);
        if (hrs >= 0) return `${hrs}h`;
      }
    }
    return '';
  }

  _buildShell(cfg) {
    const style = document.createElement('style');
    style.textContent = `
      :host { display: block; }
      .card-title { font-size: 15px; font-weight: 600; padding: 10px 16px 0;
        color: var(--primary-text-color); }
      .btn-wrap { padding: 12px 16px 14px; }
      .log-btn {
        width: 100%; min-height: 110px; display: flex; flex-direction: column;
        align-items: center; justify-content: center; gap: 6px;
        border: none; border-radius: 12px;
        background: var(--secondary-background-color, #f5f5f5);
        color: var(--primary-text-color); cursor: pointer;
        transition: transform 0.1s, background 0.15s;
        -webkit-tap-highlight-color: transparent; touch-action: none; user-select: none;
      }
      .log-btn:hover { background: var(--divider-color, #e0e0e0); }
      .log-btn:active { transform: scale(0.98); }
      .btn-emoji { font-size: 36px; line-height: 1; }
      .btn-label { font-size: 14px; font-weight: 500; }
      .a11y-hint { text-align: center; font-size: 11px;
        color: var(--secondary-text-color); padding-bottom: 8px; }
      .form-slot:empty { display: none; }
      .form-slot { padding: 0 12px 12px; }
    `;
    const haCard = document.createElement('ha-card');
    if (cfg.show_title !== false) {
      const title = document.createElement('div');
      title.className = 'card-title';
      title.textContent = cfg.dog;
      haCard.appendChild(title);
    }
    const btnWrap = document.createElement('div');
    btnWrap.className = 'btn-wrap';
    haCard.appendChild(btnWrap);

    const hint = document.createElement('div');
    hint.className = 'a11y-hint';
    hint.textContent = 'Hold to log now';
    haCard.appendChild(hint);

    const formSlot = document.createElement('div');
    formSlot.className = 'form-slot';
    formSlot.id = 'form-slot';
    haCard.appendChild(formSlot);

    while (this.shadowRoot.firstChild) this.shadowRoot.removeChild(this.shadowRoot.firstChild);
    this.shadowRoot.appendChild(style);
    this.shadowRoot.appendChild(haCard);
    return { btnWrap, formSlot };
  }

  _render() {
    const cfg = this._config;
    const hass = this._hass;

    if (!cfg.dog) return this._renderError("Missing 'dog' config");
    if (!cfg.event_type) return this._renderError("Missing 'event_type' config");
    if (!hass) {
      while (this.shadowRoot.firstChild) this.shadowRoot.removeChild(this.shadowRoot.firstChild);
      this.shadowRoot.appendChild(document.createElement('ha-card'));
      return;
    }
    if (!this._resolveDogExists(hass, cfg.dog)) {
      return this._renderError(`Dog '${cfg.dog}' not found`);
    }

    const { registry } = buildRegistry(hass);
    const knownTypes = new Set([...Object.keys(registry || {}), ...Object.keys(FALLBACK_EVENT_META)]);
    if (!knownTypes.has(cfg.event_type)) {
      return this._renderError(`Event type '${cfg.event_type}' unavailable`);
    }

    const meta = getMeta(cfg.event_type, registry);
    const metricText = this._metricText(hass, cfg, cfg.event_type);

    if (this._buttonCleanup) { this._buttonCleanup(); this._buttonCleanup = null; }

    const { btnWrap, formSlot } = this._buildShell(cfg);
    const isWeight = cfg.event_type === 'weight';

    const { cleanup } = renderPawsistantButton({
      container: btnWrap,
      meta,
      metricText,
      disabled: false,
      timers: this._timers,
      haptics: !!cfg.haptics,
      onTap: (btn) => {
        if (isWeight) this._openWeight(formSlot, meta);
        else this._openBackdate(cfg.event_type, formSlot, meta);
      },
      onLongPress: (btn) => {
        if (isWeight) this._openWeight(formSlot, meta);
        else this._instantLog(cfg.event_type);
      },
    });
    this._buttonCleanup = cleanup;
  }

  _openBackdate(type, slot, meta) {
    while (slot.firstChild) slot.removeChild(slot.firstChild);
    this._activeForm = 'backdate';
    openBackdateForm({ container: slot, meta, defaults: {} }).then((r) => {
      if (r === null) {
        this._activeForm = null;
        return;
      }
      const extra = { timestamp: r.timestamp };
      if (r.note) extra.note = r.note;
      const done = () => {
        if (r.cleanup) r.cleanup();
        this._activeForm = null;
      };
      logEvent(this._hass, this._config.dog, type, extra)
        .then(done)
        .catch(err => {
          done();
          console.error('[pawsistant-button-card] log_event failed:', err);
        });
    });
  }

  _openWeight(slot, meta) {
    while (slot.firstChild) slot.removeChild(slot.firstChild);
    const ent = findEntitiesByDog(this._hass, this._config.dog);
    const unit = this._config.weight_unit || 'lbs';
    const currentWeight = toDisplayWeight(stateNum(this._hass, ent.weight), unit);
    this._activeForm = 'weight';
    openWeightForm({ container: slot, meta, currentWeight, displayUnit: unit }).then((r) => {
      if (r === null) {
        this._activeForm = null;
        return;
      }
      const done = () => {
        if (r.cleanup) r.cleanup();
        this._activeForm = null;
      };
      logEvent(this._hass, this._config.dog, 'weight', { value: r.value })
        .then(done)
        .catch(err => {
          done();
          console.error('[pawsistant-button-card] log_event weight failed:', err);
        });
    });
  }

  _instantLog(type) {
    logEvent(this._hass, this._config.dog, type, {}).catch(err => {
      console.error('[pawsistant-button-card] instant log_event failed:', err);
    });
  }
}

if (!customElements.get('pawsistant-button-card')) {
  customElements.define('pawsistant-button-card', PawsistantButtonCard);
}
