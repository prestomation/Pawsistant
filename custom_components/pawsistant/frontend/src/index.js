/**
 * Pawsistant Card — Entry point
 *
 * Bundled by Rollup into pawsistant-card.js.
 * Pure functions are imported from sibling modules for testability.
 */

import { CARD_VERSION } from 'card-version';
import {
  FALLBACK_EVENT_META, EVENT_META, DEFAULT_SHOWN_TYPES,
  buildRegistry, getMeta, iconToEmoji
} from './registry.js';
import { METRIC_LABELS } from './metrics.js';
import { setupLongPress, withCooldown } from './interactions.js';
import { logEvent, deleteEvent, updateEvent, setShownTypes, addEventType, updateEventType, deleteEventType } from './services.js';
import { slugify, findEntitiesByDog, stateNum, stateStr, stateAttr, buildHash, _escapeHTML, toDisplayWeight } from './utils.js';

/* ── Card picker registration ───────────────────────────────────────────── */
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'pawsistant-card',
  name: 'Pawsistant',
  description: 'All-in-one pet activity tracker — log events, view timeline, track stats',
  preview: true,
});

class PawsistantCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  get _hass() { return this.__hass; }
  set hass(h) {
    this.__hass = h;
    // Re-render only if the available dog list changed (avoids thrashing).
    const names = this._dogNamesFromHass(h);
    const key = names.join(',');
    if (key !== this._lastDogNamesKey) {
      this._lastDogNamesKey = key;
      this._render();
    }
  }

  /** Extract unique sorted dog names from hass.states via the `dog` attribute. */
  _dogNamesFromHass(h) {
    if (!h) return [];
    const seen = new Set();
    for (const state of Object.values(h.states || {})) {
      const dog = state.attributes && state.attributes.dog;
      if (dog) seen.add(dog);
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



    this.shadowRoot.innerHTML = `
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
    this.shadowRoot.querySelectorAll('input[type="text"], input[type="number"], select').forEach(el => {
      el.addEventListener('change', () => this._valueChanged());
    });


  }

  _valueChanged() {
    const newConfig = { ...this._config };

    // Scalar inputs
    this.shadowRoot.querySelectorAll('input[type="text"], input[type="number"], select').forEach(el => {
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

customElements.define('pawsistant-card-editor', PawsistantCardEditor);

/* ── Main card element ──────────────────────────────────────────────────── */
class PawsistantCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass = null;
    this._lastHash = null;
    // Inline form state
    this._activeForm = null; // null | 'backdate' | 'weight'
    this._activeType = null; // event type for backdate form
    this._activeTriggerBtn = null; // U17 — return focus to trigger btn
    // U5 — track all setTimeout IDs for cleanup
    this._timers = [];
    // U9 — delete confirm state: eventId -> timeout id
    this._deleteConfirmState = new Map();
    // Event Types Manager state
    this._eventTypesPanel = false;      // true = showing manager panel
    this._editingEventType = null;      // null = list view; object = editing/adding
    // { event_type: string, name: string, icon: string, color: string, metric: string }
    this._eventTypeFormError = null;    // error message for form

  }

  static getConfigElement() {
    return document.createElement('pawsistant-card-editor');
  }

  static getStubConfig() {
    return { type: 'custom:pawsistant-card', dog: 'MyDog' };
  }

  setConfig(config) {
    if (!config.dog) throw new Error('Pawsistant card requires a "dog" config field');
    this._config = { ...config };
  }

  set hass(hass) {
    this._hass = hass;
    const hash = buildHash(hass, this._config);
    if (hash !== this._lastHash) {
      this._lastHash = hash;
      // Clear registry cache so buildRegistry runs fresh with new event_types
      this._registryCache = null;
      // Don't re-render if an edit form is open — would destroy in-progress edits
      // But DO re-render the gear panel so shown_types updates propagate
      if (!this._activeForm) {
        this._render();
      }
    }
  }

  /* U5 — disconnectedCallback clears all timers */
  disconnectedCallback() {
    for (const id of this._timers) {
      clearTimeout(id);
    }
    this._timers = [];
    for (const id of this._deleteConfirmState.values()) {
      clearTimeout(id);
    }
    this._deleteConfirmState.clear();
  }

  /** Schedule a timeout and track its ID for cleanup */
  _setTimeout(fn, delay) {
    const id = setTimeout(() => {
      this._timers = this._timers.filter(t => t !== id);
      fn();
    }, delay);
    this._timers.push(id);
    return id;
  }

  /* ── Entity resolution ─────────────────────────────────────────────── */
  _entities() {
    // findEntitiesByDog scans hass.states by attributes.dog — rename-safe.
    // Manual overrides in config (set via YAML) still win.
    const auto = findEntitiesByDog(this._hass, this._config.dog);
    return {
      timeline:      this._config.timeline_entity      || auto.timeline,
      pee_count:     this._config.pee_count_entity     || auto.pee_count,
      poop_count:    this._config.poop_count_entity    || auto.poop_count,
      medicine_days: this._config.medicine_days_entity || auto.medicine_days,
      weight:        this._config.weight_entity        || auto.weight,
    };
  }

  _weightUnit() {
    return this._config.weight_unit === 'kg' ? 'kg' : 'lbs';
  }

  _shownTypes() {
    // First, check if server-side shown_types exists for this dog
    const serverShown = this._getServerShownTypes();
    if (serverShown !== null && Array.isArray(serverShown) && serverShown.length > 0) {
      let types = serverShown;
      if (types.length > 12) {
        console.warn('[pawsistant-card] shown_types has more than 12 entries; trimming to 12. Maximum is 12 buttons.');
        types = types.slice(0, 12);
      }
      return types;
    }
    // Fallback to card config
    const t = this._config.shown_types;
    let types = (Array.isArray(t) && t.length > 0) ? t : DEFAULT_SHOWN_TYPES;
    // Maximum of 12 buttons total
    if (types.length > 12) {
      console.warn('[pawsistant-card] shown_types has more than 12 entries; trimming to 12. Maximum is 12 buttons.');
      types = types.slice(0, 12);
    }
    return types;
  }

  /** Get server-side shown_types from sensor attributes for this dog.
   *  Returns the array if found, null otherwise. */
  _getServerShownTypes() {
    if (!this._hass || !this._config.dog) return null;
    const dogNameLower = this._config.dog.toLowerCase();
    for (const state of Object.values(this._hass.states)) {
      const attrs = state.attributes || {};
      if (attrs.dog && attrs.dog.toLowerCase() === dogNameLower && Array.isArray(attrs.shown_types)) {
        return attrs.shown_types;
      }
    }
    return null;
  }

  /** Build event-type registry + button metrics from sensor attributes.
   *  Cached on this._registryCache, invalidated when hass changes. */
  _registry() {
    if (this._registryCache && typeof this._registryCache === 'object') {
      return this._registryCache;
    }
    const { registry, metrics } = buildRegistry(this._hass);
    this._registryCache = { registry, metrics };
    return this._registryCache;
  }

  /* ── Render ────────────────────────────────────────────────────────── */
  _render() {
    const hass = this._hass;
    if (!hass) return;

    const cfg = this._config;
    const ent = this._entities();
    const dogName = cfg.dog;
    const { registry, metrics } = this._registry();

    const peeCount = stateNum(hass, ent.pee_count);
    const poopCount = stateNum(hass, ent.poop_count);
    const medDays = stateNum(hass, ent.medicine_days);
    const events = stateAttr(hass, ent.timeline, 'events') || [];
    const weightUnit = this._weightUnit();

    const medDaysText = medDays === null ? '—' : Math.floor(medDays) + 'd';

    /* Build timeline HTML */
    let timelineHTML = '';
    if (events.length === 0) {
      timelineHTML = '<div class="empty">No events in the last 24 hours</div>';
    } else {
      let lastDate = null;
      for (const ev of events) {
        const meta = getMeta(ev.type, registry);
        const evDate = ev.date || '';
        if (evDate !== lastDate) {
          const label = evDate || ev.day || '';
          timelineHTML += `<div class="day-header">${_escapeHTML(label)}</div>`;
          lastDate = evDate;
        }
        /* U14 — add title attr to truncated notes */
        const noteHTML = ev.note
          ? `<span class="event-note" title="${_escapeHTML(ev.note)}">${_escapeHTML(ev.note)}</span>`
          : '';
        /* U2 — aria-label on delete button */
        const delAriaLabel = `Delete ${_escapeHTML(ev.type)} event at ${_escapeHTML(ev.time)}`;
        const editAriaLabel = `Edit ${_escapeHTML(ev.type)} event at ${_escapeHTML(ev.time)}`;
        timelineHTML += `
          <div class="event-row" data-id="${_escapeHTML(ev.event_id)}" data-type="${_escapeHTML(ev.type)}" data-timestamp="${_escapeHTML(ev.timestamp || '')}" data-note="${_escapeHTML(ev.note || '')}" data-value="${ev.value !== undefined && ev.value !== null ? ev.value : ''}"  >
            <span class="event-emoji">${meta.emoji}</span>
            <span class="event-time">${_escapeHTML(ev.time)}</span>
            <span class="event-type">${_escapeHTML(meta.label)}</span>
            ${noteHTML}
            <button class="edit-btn" data-id="${_escapeHTML(ev.event_id)}"
              aria-label="${editAriaLabel}" title="Edit event">✏️</button>
            <button class="delete-btn" data-id="${_escapeHTML(ev.event_id)}"
              aria-label="${delAriaLabel}" title="Delete event">🗑️</button>
          </div>
        `;
      }
    }

    /* Build quick-log buttons */
    const shownTypes = this._shownTypes();
    const buttonsPerRow = cfg.buttons_per_row && Number.isInteger(cfg.buttons_per_row)
      ? Math.min(6, Math.max(2, cfg.buttons_per_row))
      : null;
    let buttonsHTML = '';
    for (const type of shownTypes) {
      const meta = getMeta(type, registry);
      const isWeight = type === 'weight';

      /* Inline count/stat for supported types */
      let countSuffix = '';
      const metric = metrics[type] || 'daily_count';
      if (metric === 'daily_count') {
        if (type === 'pee' && peeCount !== null) countSuffix = ` (${peeCount})`;
        else if (type === 'poop' && poopCount !== null) countSuffix = ` (${poopCount})`;
        else if (type === 'medicine' && medDays !== null) countSuffix = ` (${medDaysText})`;
      } else if (metric === 'days_since' && medDays !== null) {
        countSuffix = ` (${Math.floor(medDays)}d)`;
      } else if (metric === 'last_value') {
        const w = toDisplayWeight(stateNum(hass, ent.weight), weightUnit);
        if (w !== null) countSuffix = ` (${w} ${weightUnit})`;
      } else if (metric === 'hours_since') {
        // Show hours since most recent of this type
        const lastTs = stateAttr(hass, ent.timeline, 'last_' + type + '_ts');
        if (lastTs) {
          const hrs = Math.floor((Date.now() - new Date(lastTs).getTime()) / 3600000);
          if (hrs >= 0) countSuffix = ` (${hrs}h)`;
        }
      }

      const ariaLabel = isWeight
        ? `Log weight`
        : `Log ${meta.label}. Hold to log now.`;
      const dataAttrs = isWeight
        ? `data-type="weight" data-weight="true"`
        : `data-type="${_escapeHTML(type)}" data-longpress="true"`;

      buttonsHTML += `
        <button class="log-btn" ${dataAttrs} aria-label="${_escapeHTML(ariaLabel)}">
          <span class="btn-emoji" aria-hidden="true">${meta.emoji}</span>
          <span class="btn-label">${_escapeHTML(meta.label)}${countSuffix}</span>
        </button>
      `;
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
        }
        .card {
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border-radius: var(--ha-card-border-radius, 12px);
          border: 1px solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
          box-shadow: var(--ha-card-box-shadow, none);
          overflow: hidden;
        }
        .card-header {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 14px 16px 10px;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
        }
        .card-title {
          font-size: 17px;
          font-weight: 600;
          color: var(--primary-text-color);
          flex: 1;
        }
        .event-types-gear-btn {
          background: none;
          border: none;
          cursor: pointer;
          font-size: 18px;
          padding: 6px 10px;
          border-radius: 6px;
          color: var(--secondary-text-color);
          min-width: 44px;
          min-height: 44px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background 0.15s;
          flex-shrink: 0;
        }
        .event-types-gear-btn:hover { background: var(--secondary-background-color, #f5f5f5); }
        /* ── Quick-log buttons ── */
        .quick-log {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          padding: 12px 16px 0;
          justify-content: center;
        }
        .quick-log.grid-layout {
          display: grid;
          justify-content: unset;
        }
        .log-btn {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 4px;
          padding: 12px 4px;
          border: none;
          border-radius: 10px;
          background: var(--secondary-background-color, #f5f5f5);
          cursor: pointer;
          font-size: 13px;
          color: var(--primary-text-color);
          transition: transform 0.1s, opacity 0.15s, box-shadow 0.1s, background 0.15s;
          -webkit-tap-highlight-color: transparent;
          user-select: none;
          touch-action: none;
          min-height: 64px;
          min-width: 60px;
          flex: 1 1 60px;
          max-width: 120px;
          position: relative;
        }
        .quick-log.grid-layout .log-btn {
          max-width: unset;
          flex: unset;
          width: 100%;
        }
        .log-btn:hover { background: var(--divider-color, #e0e0e0); }
        .log-btn:active { transform: scale(0.94); }
        .log-btn .btn-emoji { font-size: 26px; line-height: 1; }
        .log-btn .btn-label { font-size: 12px; font-weight: 500; }
        /* Dimmed state when a form is open */
        .log-btn.dimmed {
          opacity: 0.35;
          pointer-events: none;
        }
        /* Active/highlighted state */
        .log-btn.active-btn {
          background: var(--primary-color, #2196f3);
          color: var(--text-primary-color, #fff);
          box-shadow: 0 2px 8px rgba(33,150,243,0.35);
        }
        /* Flash animation on instant log — U19 use color-mix instead of --rgb-primary-color */
        .log-btn.flash {
          animation: flash-anim 0.5s ease;
        }
        @keyframes flash-anim {
          0%   { box-shadow: 0 0 0 0 color-mix(in srgb, var(--primary-color, #2196f3) 70%, transparent); transform: scale(1); }
          30%  { box-shadow: 0 0 0 8px color-mix(in srgb, var(--primary-color, #2196f3) 20%, transparent); transform: scale(0.93); }
          100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--primary-color, #2196f3) 0%, transparent); transform: scale(1); }
        }
        /* Success check flash */
        .log-btn.success-flash {
          animation: success-anim 0.6s ease forwards;
        }
        @keyframes success-anim {
          0%   { background: var(--success-color, #4caf50); transform: scale(1); }
          40%  { transform: scale(0.93); }
          100% { background: var(--success-color, #4caf50); transform: scale(1); }
        }
        /* Pending state (debounce) */
        .log-btn[data-pending] {
          opacity: 0.6;
          pointer-events: none;
        }
        /* U1 — long-press hint */
        .longpress-hint {
          text-align: center;
          font-size: 11px;
          color: var(--secondary-text-color);
          padding: 6px 16px 2px;
          opacity: 0.7;
        }

        /* ── Inline form panel ── */
        .inline-form-wrap {
          overflow: hidden;
          max-height: 0;
          transition: max-height 0.28s cubic-bezier(0.4, 0, 0.2, 1);
        }
        /* U8 — fix landscape overflow */
        .inline-form-wrap.open {
          max-height: min(400px, 60vh);
          overflow-y: auto;
        }
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
        .weight-unit {
          font-size: 13px;
          color: var(--secondary-text-color);
          align-self: center;
          margin-left: 6px;
          flex-shrink: 0;
        }
        .weight-input-row {
          display: flex;
          align-items: center;
          gap: 0;
        }
        .weight-input-row input {
          flex: 1;
        }
        /* U11 — error feedback */
        .form-error {
          color: var(--error-color, #EF5350);
          font-size: 12px;
          padding: 6px 10px;
          border-radius: 6px;
          background: color-mix(in srgb, var(--error-color, #EF5350) 10%, transparent);
          display: none;
        }
        .form-error.visible { display: block; }
        /* Spacer below button grid + form */
        .quick-log-section {
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
          padding-bottom: 12px;
        }

        .timeline-header {
          display: flex;
          align-items: center;
          padding: 10px 16px 6px;
          font-size: 13px;
          font-weight: 600;
          color: var(--secondary-text-color);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        /* U12 — overscroll-behavior: contain */
        .timeline-body {
          padding: 0 4px 8px;
          max-height: 380px;
          overflow-y: auto;
          overscroll-behavior: contain;
        }
        .day-header {
          font-size: 10px;
          font-weight: 700;
          color: var(--secondary-text-color);
          text-transform: uppercase;
          letter-spacing: 0.08em;
          padding: 4px 8px 2px;
          margin-top: 2px;
        }
        .event-row {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 4px 6px;
          border-radius: 6px;
          transition: background 0.15s;
        }
        .event-row:hover { background: var(--secondary-background-color, #f5f5f5); }
        .event-emoji { font-size: 15px; flex-shrink: 0; width: 20px; text-align: center; }
        .event-time { font-size: 11px; color: var(--secondary-text-color); white-space: nowrap; flex-shrink: 0; min-width: 58px; }
        .event-type { font-size: 12px; font-weight: 500; color: var(--primary-text-color); flex-shrink: 0; }
        /* U14 — truncated notes with title attr for tooltip */
        .event-note { font-size: 12px; color: var(--secondary-text-color); flex: 1; font-style: italic; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        /* U6 — 44px touch target for delete button */
        .edit-btn {
          background: none;
          border: none;
          cursor: pointer;
          opacity: 0;
          font-size: 12px;
          padding: 8px;
          border-radius: 4px;
          min-width: 36px;
          min-height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: opacity 0.15s, background 0.15s;
          flex-shrink: 0;
        }
        .event-row:hover .edit-btn, .event-row:focus-within .edit-btn { opacity: 0.5; }
        .edit-btn:hover { opacity: 1 !important; background: color-mix(in srgb, var(--primary-color, #03a9f4) 12%, transparent); }
        .delete-btn {
          background: none;
          border: none;
          cursor: pointer;
          opacity: 0.4;
          font-size: 14px;
          padding: 10px;
          border-radius: 4px;
          min-width: 44px;
          min-height: 44px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: opacity 0.15s, background 0.15s;
          flex-shrink: 0;
          margin-left: auto;
        }
        .delete-btn:hover { opacity: 1; background: color-mix(in srgb, var(--error-color, #ef5350) 12%, transparent); }
        /* U9 — confirm state */
        .delete-btn.confirm-pending {
          opacity: 1;
          color: var(--error-color, #ef5350);
          background: color-mix(in srgb, var(--error-color, #ef5350) 15%, transparent);
          font-size: 11px;
        }
        .empty {
          text-align: center;
          padding: 24px;
          color: var(--secondary-text-color);
          font-size: 14px;
        }
        @media (max-width: 420px) {
          .quick-log { gap: 5px; padding: 10px 10px 0; }
          .log-btn { padding: 8px 2px; min-height: 54px; min-width: 50px; }
          .log-btn .btn-emoji { font-size: 20px; }
          .log-btn .btn-label { font-size: 10px; }
        }

        /* ── Event Types Manager Panel ── */
        .event-types-panel {
          padding: 12px 0 0;
        }
        .event-types-panel-header {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 0 16px 10px;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
        }
        .event-types-panel-title {
          font-size: 16px;
          font-weight: 600;
          color: var(--primary-text-color);
          flex: 1;
        }
        .event-types-back-btn {
          background: none;
          border: none;
          cursor: pointer;
          font-size: 18px;
          padding: 6px 10px;
          border-radius: 6px;
          color: var(--secondary-text-color);
          min-width: 44px;
          min-height: 44px;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .event-types-back-btn:hover { background: var(--secondary-background-color, #f5f5f5); }

        .event-types-list {
          list-style: none;
          padding: 8px 12px;
          margin: 0;
        }
        .event-type-row {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 8px 4px;
          border-radius: 8px;
          transition: background 0.15s;
        }
        .event-type-row:hover { background: var(--secondary-background-color, #f5f5f5); }
        .event-type-row.et-dragging { opacity: 0.4; }
        .event-type-row.et-drag-over { background: var(--primary-color-light, #e3f2fd); outline: 2px dashed var(--primary-color, #2196f3); }
        .et-drag-handle {
          cursor: grab;
          font-size: 16px;
          color: var(--secondary-text-color);
          flex-shrink: 0;
          user-select: none;
          padding: 0 2px;
        }
        .et-drag-handle:active { cursor: grabbing; }
        .et-visibility-toggle {
          cursor: pointer;
          display: flex;
          align-items: center;
          flex-shrink: 0;
        }
        .et-visibility-toggle input[type="checkbox"] { display: none; }
        .et-visible-icon { font-size: 16px; line-height: 1; }
        .et-hint {
          font-size: 11px;
          color: var(--secondary-text-color);
          margin: 0 0 8px 0;
          padding: 0 4px;
        }
        .et-color-swatch {
          width: 20px;
          height: 20px;
          border-radius: 50%;
          flex-shrink: 0;
          border: 1px solid rgba(0,0,0,0.1);
        }
        .et-icon { font-size: 20px; flex-shrink: 0; width: 26px; text-align: center; }
        .et-name {
          flex: 1;
          font-size: 14px;
          font-weight: 500;
          color: var(--primary-text-color);
        }
        .et-badge {
          font-size: 10px;
          padding: 2px 7px;
          border-radius: 10px;
          background: var(--divider-color, #e0e0e0);
          color: var(--secondary-text-color);
          flex-shrink: 0;
        }
        .et-badge.custom { background: var(--primary-color, #2196f3); color: var(--text-primary-color, #fff); }
        .et-badge.builtin { background: var(--divider-color, #e0e0e0); color: var(--secondary-text-color); }
        .et-actions { display: flex; gap: 4px; flex-shrink: 0; }
        .et-btn {
          background: none;
          border: 1px solid var(--divider-color, #e0e0e0);
          cursor: pointer;
          font-size: 12px;
          padding: 5px 10px;
          border-radius: 6px;
          color: var(--secondary-text-color);
          min-width: 44px;
          min-height: 44px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background 0.15s;
        }
        .et-btn:hover { background: var(--secondary-background-color, #f5f5f5); }
        .et-btn.delete:hover { background: color-mix(in srgb, var(--error-color, #EF5350) 12%, transparent); color: var(--error-color, #EF5350); border-color: var(--error-color, #EF5350); }

        .add-event-type-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          width: calc(100% - 24px);
          margin: 8px 12px;
          padding: 10px;
          border: 2px dashed var(--divider-color, #e0e0e0);
          border-radius: 8px;
          background: transparent;
          color: var(--secondary-text-color);
          font-size: 13px;
          cursor: pointer;
          transition: border-color 0.15s, background 0.15s;
        }
        .add-event-type-btn:hover { border-color: var(--primary-color, #2196f3); background: color-mix(in srgb, var(--primary-color, #2196f3) 8%, transparent); color: var(--primary-color, #2196f3); }

        /* Event Type Edit Form */
        .et-form {
          padding: 12px 16px 8px;
          border-top: 1px solid var(--divider-color, #e0e0e0);
          display: flex;
          flex-direction: column;
          gap: 14px;
        }
        .et-form-title {
          font-size: 15px;
          font-weight: 600;
          color: var(--primary-text-color);
        }
        .et-form-field {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .et-form-label {
          font-size: 12px;
          font-weight: 500;
          color: var(--secondary-text-color);
        }
        .et-form-row {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .et-form-row input[type="text"] {
          flex: 1;
        }
        .et-browse-btn {
          padding: 8px 12px;
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 6px;
          background: var(--secondary-background-color, #f5f5f5);
          color: var(--primary-text-color);
          font-size: 12px;
          cursor: pointer;
          white-space: nowrap;
          flex-shrink: 0;
          min-height: 40px;
        }
        .et-browse-btn:hover { background: var(--divider-color, #e0e0e0); }
        .et-color-row {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .et-color-input {
          width: 44px;
          height: 44px;
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 8px;
          padding: 2px;
          cursor: pointer;
          background: none;
          flex-shrink: 0;
        }
        .et-color-hex {
          font-size: 13px;
          color: var(--secondary-text-color);
          font-family: monospace;
        }
        .et-form-error {
          color: var(--error-color, #EF5350);
          font-size: 12px;
          padding: 6px 10px;
          border-radius: 6px;
          background: color-mix(in srgb, var(--error-color, #EF5350) 10%, transparent);
          display: none;
        }
        .et-form-error.visible { display: block; }
        .et-form-actions {
          display: flex;
          gap: 8px;
          padding-bottom: 8px;
        }
        .et-btn-submit {
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
        }
        .et-btn-submit:active { opacity: 0.85; }
        .et-btn-cancel {
          padding: 12px 18px;
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 8px;
          background: transparent;
          color: var(--secondary-text-color);
          font-size: 14px;
          cursor: pointer;
          min-height: 44px;
        }
        .et-btn-cancel:active { background: var(--secondary-background-color, #f5f5f5); }
      </style>
      <ha-card class="card">
        ${this._eventTypesPanel
          ? this._renderEventTypesPanel(registry, metrics)
          : this._renderMainContent(dogName, buttonsHTML, buttonsPerRow, timelineHTML)
        }
      </ha-card>
    `;

    this._attachListeners();
  }

  /* ── Render main card content ──────────────────────────────────────── */
  _renderMainContent(dogName, buttonsHTML, buttonsPerRow, timelineHTML) {
    return `
        <div class="card-header">
          <span class="card-title">🐾 ${_escapeHTML(dogName)}</span>
          <button class="event-types-gear-btn" id="et-gear-btn" title="Configure event types" aria-label="Configure event types">⚙️</button>
        </div>

        <div class="quick-log-section">
          <div class="quick-log${buttonsPerRow ? ' grid-layout' : ''}" id="quick-log-grid"${buttonsPerRow ? ` style="grid-template-columns: repeat(${buttonsPerRow}, 1fr);"` : ''}>
            ${buttonsHTML}
          </div>
          <!-- U1 — long-press hint -->
          <div class="longpress-hint" aria-live="polite">Hold to log now</div>

          <!-- Inline form panel (hidden by default) -->
          <div class="inline-form-wrap" id="inline-form-wrap">
            <div class="inline-form" id="inline-form">
              <!-- content injected by _openBackdateForm / _openWeightForm -->
            </div>
          </div>
        </div>

        <div class="timeline-header">📋 Last 24 hours</div>
        <div class="timeline-body" id="timeline-body">${timelineHTML}</div>
      `;
  }

  /* ── Render Event Types Manager Panel ──────────────────────────────── */
  _renderEventTypesPanel(registry, metrics) {
    const esc = _escapeHTML;
    const { registry: allTypes, metrics: buttonMetrics } = this._registry();

    // If editing/adding a type, show the form
    if (this._editingEventType !== null) {
      return this._renderEventTypeForm(this._editingEventType);
    }

    // Determine order: shown_types first (in order), then remaining unchecked types
    const shownTypes = this._shownTypes();
    const allKeys = Object.keys(allTypes);
    const shownInOrder = shownTypes.filter(k => allKeys.includes(k));
    const hiddenKeys = allKeys.filter(k => !shownInOrder.includes(k));
    const orderedKeys = [...shownInOrder, ...hiddenKeys];

    // List view — drag handle + visibility checkbox + edit/delete
    const rows = orderedKeys.map(key => {
      const displayMeta = getMeta(key, allTypes);
      const metric = buttonMetrics[key] || 'daily_count';
      const metricBadge = METRIC_LABELS[metric] ? metric.replace(/_/g, ' ') : metric;
      const icon = displayMeta.icon ? iconToEmoji(displayMeta.icon) : displayMeta.emoji;
      const isVisible = shownInOrder.includes(key);
      return `
        <li class="event-type-row" data-et-key="${esc(key)}" draggable="true">
          <span class="et-drag-handle" title="Drag to reorder">☰</span>
          <span class="et-color-swatch" style="background:${esc(displayMeta.color)}" title="${esc(displayMeta.color)}"></span>
          <span class="et-icon" title="${esc(displayMeta.icon || '')}">${icon}</span>
          <span class="et-name">${esc(displayMeta.label)}</span>
          <span class="et-badge">${metricBadge}</span>
          <div class="et-actions">
            <label class="et-visibility-toggle" title="${isVisible ? 'Hide from card' : 'Show on card'}">
              <input type="checkbox" class="et-visible-cb" data-et-key="${esc(key)}" ${isVisible ? 'checked' : ''} />
              <span class="et-visible-icon">${isVisible ? '👁' : '🚫'}</span>
            </label>
            <button class="et-btn edit" data-et-key="${esc(key)}" title="Edit '${esc(key)}'">✎</button>
            <button class="et-btn delete" data-et-key="${esc(key)}" title="Delete '${esc(key)}'">✕</button>
          </div>
        </li>`;
    }).join('');

    return `
        <div class="event-types-panel">
          <div class="event-types-panel-header">
            <button class="event-types-back-btn" id="et-back-btn" title="Back">←</button>
            <span class="event-types-panel-title">⚙️ Event Types</span>
          </div>
          <p class="et-hint">Drag ☰ to reorder · 👁 toggles button visibility</p>
          <ul class="event-types-list" id="et-list">
            ${rows}
          </ul>
          <button class="add-event-type-btn" id="et-add-btn">
            <span>+</span> Add Event Type
          </button>
        </div>
      `;
  }

  /* ── Render Event Type Edit/Add Form ──────────────────────────────── */
  _renderEventTypeForm(editing) {
    // editing = null means ADD mode; otherwise it's {event_type, name, icon, color, metric}
    const isAdd = editing === '__ADD__';
    const isEdit = !isAdd && editing !== null;
    const esc = _escapeHTML;

    let keyVal = '', nameVal = '', iconVal = '', colorVal = '#4CAF50', metricVal = 'daily_count';
    let formTitle = 'Add Event Type';

    if (isEdit) {
      const meta = getMeta(editing.event_type, this._registry().registry) || {};
      const { metrics } = this._registry();
      keyVal = editing.event_type;
      nameVal = editing.name || meta.label || editing.event_type;
      iconVal = editing.icon || meta.icon || '';
      colorVal = editing.color || meta.color || '#4CAF50';
      metricVal = editing.metric || metrics[editing.event_type] || 'daily_count';
      formTitle = 'Edit Event Type';
    }

    const metricOptions = ['daily_count', 'days_since', 'last_value', 'hours_since']
      .map(m => `<option value="${m}"${metricVal === m ? ' selected' : ''}>${m.replace(/_/g, ' ')}</option>`)
      .join('');

    // Show key field only in ADD mode
    const keyField = isAdd
      ? `<div class="et-form-field">
           <label class="et-form-label" for="et-key-input">Event type key</label>
           <input type="text" id="et-key-input" value="${esc(keyVal)}"
             placeholder="e.g. outdoor_walk" maxlength="30"
             style="width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid var(--divider-color);border-radius:8px;background:var(--card-background-color);color:var(--primary-text-color);font-size:15px;" />
           <div class="hint" style="font-size:11px;color:var(--secondary-text-color);margin-top:3px;">
             Lowercase letters, numbers, underscores only. Max 30 chars.
           </div>
         </div>`
      : `<div class="et-form-field">
           <label class="et-form-label">Event type key</label>
           <div style="font-size:14px;color:var(--secondary-text-color);padding:4px 0;font-family:monospace;">${esc(keyVal)}</div>
         </div>`;

    const errorHTML = this._eventTypeFormError
      ? `<div class="et-form-error visible" role="alert">${_escapeHTML(this._eventTypeFormError)}</div>`
      : `<div class="et-form-error" role="alert"></div>`;

    return `
        <div class="event-types-panel">
          <div class="event-types-panel-header">
            <button class="event-types-back-btn" id="et-form-back-btn" title="Back to list">←</button>
            <span class="event-types-panel-title">${esc(formTitle)}</span>
          </div>
          <div class="et-form" id="et-form">
            ${isAdd ? keyField : ''}
            <div class="et-form-field">
              <label class="et-form-label" for="et-name-input">Display name</label>
              <input type="text" id="et-name-input" value="${esc(nameVal)}"
                placeholder="e.g. Morning Walk"
                style="width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid var(--divider-color);border-radius:8px;background:var(--card-background-color);color:var(--primary-text-color);font-size:15px;" />
            </div>
            <div class="et-form-field">
              <label class="et-form-label" for="et-icon-input">Icon (mdi: format)</label>
              <div class="et-form-row">
                <input type="text" id="et-icon-input" value="${esc(iconVal)}"
                  placeholder="mdi:walk"
                  style="flex:1;box-sizing:border-box;padding:10px 12px;border:1px solid var(--divider-color);border-radius:8px;background:var(--card-background-color);color:var(--primary-text-color);font-size:15px;" />
                <button class="et-browse-btn" id="et-browse-btn" type="button"
                  title="Pick icon from HA's built-in icon picker">
                  🎨 Pick
                </button>
              </div>
            </div>
            <div class="et-form-field">
              <label class="et-form-label" for="et-color-input">Color</label>
              <div class="et-color-row">
                <input type="color" id="et-color-input" class="et-color-input"
                  value="${esc(colorVal)}" />
                <span class="et-color-hex" id="et-color-hex">${esc(colorVal)}</span>
              </div>
            </div>
            <div class="et-form-field">
              <label class="et-form-label" for="et-metric-select">Button metric</label>
              <select id="et-metric-select"
                style="width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid var(--divider-color);border-radius:8px;background:var(--card-background-color);color:var(--primary-text-color);font-size:15px;">
                ${metricOptions}
              </select>
              <div style="font-size:11px;color:var(--secondary-text-color);margin-top:3px;">
                daily_count = "N today" · days_since = "N days" · last_value = "value" · hours_since = "N hours"
              </div>
            </div>
            ${errorHTML}
            <div class="et-form-actions">
              <button class="et-btn-cancel" id="et-form-cancel">Cancel</button>
              <button class="et-btn-submit" id="et-form-submit">${isAdd ? 'Add Event Type' : 'Save Changes'}</button>
            </div>
          </div>
        </div>
      `;
  }

  /* ── Open Event Types Manager Panel ──────────────────────────────── */
  _openEventTypesPanel() {
    this._eventTypesPanel = true;
    this._editingEventType = null;
    this._eventTypeFormError = null;
    this._render();
  }

  _closeEventTypesPanel() {
    this._eventTypesPanel = false;
    this._editingEventType = null;
    this._eventTypeFormError = null;
    this._render();
    // Refresh hash so normal render picks up any registry changes
    this._lastHash = null;
  }

  /* ── Open Edit/Add Form ───────────────────────────────────────────── */
  _openEventTypeForm(key) {
    // key = event_type key to edit, or '__ADD__' for new
    if (key === '__ADD__') {
      this._editingEventType = '__ADD__';
    } else {
      // Snapshot current state for this type
      const { registry, metrics } = this._registry();
      const meta = getMeta(key, registry) || {};
      this._editingEventType = {
        event_type: key,
        name: meta.label || key,
        icon: meta.icon || '',
        color: meta.color || '#4CAF50',
        metric: metrics[key] || 'daily_count',
      };
    }
    this._eventTypeFormError = null;
    this._render();
  }

  /* ── Save Event Type Form ─────────────────────────────────────────── */
  _saveEventTypeForm() {
    const isAdd = this._editingEventType === '__ADD__';
    const formEl = this.shadowRoot.getElementById('et-form');
    if (!formEl) return;

    // Collect values
    const name = (formEl.querySelector('#et-name-input') || {}).value || '';
    const icon = (formEl.querySelector('#et-icon-input') || {}).value || '';
    const color = (formEl.querySelector('#et-color-input') || {}).value || '';
    const metric = (formEl.querySelector('#et-metric-select') || {}).value || 'daily_count';

    let eventType;
    if (isAdd) {
      eventType = (formEl.querySelector('#et-key-input') || {}).value || '';
    } else {
      eventType = this._editingEventType.event_type;
    }

    // Basic client-side validation before calling service
    if (isAdd && !eventType.trim()) {
      this._eventTypeFormError = "Event type key is required.";
      this._render();
      return;
    }
    if (!name.trim()) {
      this._eventTypeFormError = "Display name is required.";
      this._render();
      return;
    }
    if (!icon.trim()) {
      this._eventTypeFormError = "Icon is required.";
      this._render();
      return;
    }

    // Auto-prepend mdi: if user typed just "walk"
    const normalizedIcon = icon.trim().startsWith('mdi:') || icon.trim().startsWith('hass:')
      ? icon.trim()
      : 'mdi:' + icon.trim();

    // Build service call
    const payload = {
      event_type: eventType,
      name: name.trim(),
      icon: normalizedIcon,
      color: color.trim(),
      metric: metric,
    };

    const callFn = isAdd ? addEventType : updateEventType;
    callFn(this._hass, payload)
      .then(() => {
        this._closeEventTypesPanel();
        // Force refresh the card to pick up new registry
        this._setTimeout(() => { this._lastHash = null; this._render(); }, 300);
      })
      .catch(err => {
        // Surface service validation error
        const msg = (err && err.message) ? String(err.message).replace(/^Error: /i, '') : 'Unknown error.';
        this._eventTypeFormError = msg;
        this._render();
      });
  }

  /* ── Save shown_types (order + visibility) ────────────────────────── */
  _saveShownTypes(orderedShownKeys) {
    // Call server-side service to persist shown_types per dog
    const dogName = this._config.dog;
    setShownTypes(this._hass, dogName, orderedShownKeys)
      .then(() => {
        // Force re-render after server updates sensor attribute
        this._setTimeout(() => { this._lastHash = null; this._render(); }, 300);
      })
      .catch(err => {
        console.error('[pawsistant-card] set_shown_types failed:', err);
      });
    // Optimistically update local state for immediate visual feedback
    this._lastHash = null;
    this._render();
  }

  /* ── Delete Event Type ─────────────────────────────────────────────── */
  _deleteEventType(key) {
    if (!confirm(`Delete event type '${key}'? Events logged with this type will be preserved.`)) return;
    deleteEventType(this._hass, key)
      .then(() => {
        // Optimistically remove the type from the cached registry immediately,
        // without waiting for HA to push updated sensor state.
        if (this._registryCache && this._registryCache.registry) {
          delete this._registryCache.registry[key];
        }
        this._lastHash = null;
        this._render();
      })
      .catch(err => {
        console.error('[pawsistant-card] delete_event_type failed:', err);
        this._eventTypeFormError = 'Delete failed: ' + ((err && err.message) || 'Unknown error');
        this._render();
      });
  }

  /* ── Icon picker helper ────────────────────────────────────────────── */
  async _pickIcon(currentIcon) {
    // Try HA's built-in ha-icon-picker
    const picker = document.createElement('ha-icon-picker');
    if (picker && (typeof picker.value !== 'undefined' || customElements.get('ha-icon-picker'))) {
      return new Promise((resolve) => {
        const dialog = document.createElement('ha-dialog');
        dialog.setAttribute('open', '');
        dialog.heading = 'Pick an icon';
        picker.value = currentIcon || '';
        picker.addEventListener('value-changed', (e) => {
          resolve(e.detail.value);
          dialog.remove();
        });
        dialog.appendChild(picker);
        document.body.appendChild(dialog);
      });
    }
    // Fallback
    const val = window.prompt('Enter MDI icon name (e.g. mdi:dog):', currentIcon || '');
    return val || currentIcon;
  }

  /* ── Attach listeners ──────────────────────────────────────────────── */
  _attachListeners() {
    const root = this.shadowRoot;

    root.querySelectorAll('.log-btn').forEach(btn => {
      const isWeight = btn.dataset.weight === 'true';
      const hasLongPress = btn.dataset.longpress === 'true';

      if (isWeight) {
        btn.addEventListener('pointerdown', (e) => { e.preventDefault(); });
        btn.addEventListener('pointerup', (e) => {
          e.preventDefault();
          if (this._activeForm === 'weight') {
            this._closeForm();
          } else {
            this._openWeightForm(btn);
          }
        });
        /* U3 — keyboard: Enter opens form, Space = instant log (weight just opens form) */
        btn.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            if (this._activeForm === 'weight') {
              this._closeForm();
            } else {
              this._openWeightForm(btn);
            }
          }
        });
        return;
      }

      if (hasLongPress) {
        const cleanup = setupLongPress(btn, {
          onLongPress: (btn) => {
            const type = btn.dataset.type;
            this._instantLog(btn, type);
          },
          onTap: (btn) => {
            const type = btn.dataset.type;
            if (this._activeForm === 'backdate' && this._activeType === type) {
              this._closeForm();
            } else {
              this._openBackdateForm(btn, type);
            }
          },
        }, this._timers);
        // Store cleanup for future use if needed
        btn._longPressCleanup = cleanup;
        return;
      }

      // Fallback: simple click = backdate form
      btn.addEventListener('click', () => {
        this._openBackdateForm(btn, btn.dataset.type);
      });
    });

    /* U9 — two-tap delete confirmation */
    root.querySelectorAll('.delete-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const eventId = btn.dataset.id;
        if (!eventId) return;

        if (this._deleteConfirmState.has(eventId)) {
          // Second tap — confirm and delete
          clearTimeout(this._deleteConfirmState.get(eventId));
          this._deleteConfirmState.delete(eventId);
          btn.classList.remove('confirm-pending');
          btn.textContent = '🗑️';
          this._deleteEvent(eventId, btn);
        } else {
          // First tap — show confirm state
          btn.classList.add('confirm-pending');
          btn.textContent = 'Delete?';
          const revertId = this._setTimeout(() => {
            this._deleteConfirmState.delete(eventId);
            btn.classList.remove('confirm-pending');
            btn.textContent = '🗑️';
          }, 3000);
          this._deleteConfirmState.set(eventId, revertId);
        }
      });
    });

    /* Edit button on event rows */
    root.querySelectorAll('.edit-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const row = btn.closest('.event-row');
        if (!row) return;
        const eventType = row.dataset.type;
        const timestamp = row.dataset.timestamp;
        const note = row.dataset.note;
        const value = row.dataset.value;
        const eventId = row.dataset.id;
        this._openEditForm(eventType, timestamp, note, value, eventId);
      });
    });

    /* ── Event Types Manager Panel listeners ── */

    // Gear button to open panel
    const gearBtn = root.querySelector('#et-gear-btn');
    if (gearBtn) {
      gearBtn.addEventListener('click', () => this._openEventTypesPanel());
    }

    // Back button in panel header
    const backBtn = root.querySelector('#et-back-btn');
    if (backBtn) {
      backBtn.addEventListener('click', () => this._closeEventTypesPanel());
    }

    // Back button in form header (return to list)
    const formBackBtn = root.querySelector('#et-form-back-btn');
    if (formBackBtn) {
      formBackBtn.addEventListener('click', () => {
        this._editingEventType = null;
        this._eventTypeFormError = null;
        this._render();
      });
    }

    // Add button
    const addBtn = root.querySelector('#et-add-btn');
    if (addBtn) {
      addBtn.addEventListener('click', () => this._openEventTypeForm('__ADD__'));
    }

    // Edit buttons on event type rows
    root.querySelectorAll('.et-btn.edit').forEach(btn => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.etKey;
        if (key) this._openEventTypeForm(key);
      });
    });

    // Delete buttons on event type rows
    root.querySelectorAll('.et-btn.delete').forEach(btn => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.etKey;
        if (key) this._deleteEventType(key);
      });
    });

    // Visibility checkboxes — toggle shown_types
    root.querySelectorAll('.et-visible-cb').forEach(cb => {
      cb.addEventListener('change', () => {
        const shownTypes = [...this._shownTypes()];
        const key = cb.dataset.etKey;
        if (cb.checked) {
          if (!shownTypes.includes(key)) shownTypes.push(key);
        } else {
          const idx = shownTypes.indexOf(key);
          if (idx !== -1) shownTypes.splice(idx, 1);
        }
        this._saveShownTypes(shownTypes);
      });
    });

    // Drag-to-reorder on event type rows
    let _dragKey = null;
    root.querySelectorAll('.event-type-row[draggable]').forEach(row => {
      row.addEventListener('dragstart', (e) => {
        _dragKey = row.dataset.etKey;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', _dragKey);
        row.classList.add('et-dragging');
      });
      row.addEventListener('dragend', () => {
        row.classList.remove('et-dragging');
        root.querySelectorAll('.event-type-row').forEach(r => r.classList.remove('et-drag-over'));
        _dragKey = null;
      });
      row.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        root.querySelectorAll('.event-type-row').forEach(r => r.classList.remove('et-drag-over'));
        row.classList.add('et-drag-over');
      });
      row.addEventListener('drop', (e) => {
        e.preventDefault();
        const fromKey = _dragKey;
        const toKey = row.dataset.etKey;
        if (!fromKey || fromKey === toKey) return;

        // Get current full ordered list from DOM
        const allRows = [...root.querySelectorAll('.event-type-row')];
        const orderedAll = allRows.map(r => r.dataset.etKey);

        // Reorder: move fromKey to toKey's position
        const fromIdx = orderedAll.indexOf(fromKey);
        const toIdx = orderedAll.indexOf(toKey);
        orderedAll.splice(fromIdx, 1);
        orderedAll.splice(toIdx, 0, fromKey);

        // Only keep keys that were in shown_types (preserve visibility state)
        const shownTypes = this._shownTypes();
        const newShown = orderedAll.filter(k => shownTypes.includes(k));
        this._saveShownTypes(newShown);
      });
    });

    // Pick icon button — use the icon picker helper
    const browseBtn = root.querySelector('#et-browse-btn');
    if (browseBtn) {
      browseBtn.addEventListener('click', async () => {
        const iconInput = root.querySelector('#et-icon-input');
        const currentIcon = iconInput ? iconInput.value.trim() : '';
        const picked = await this._pickIcon(currentIcon);
        if (picked && iconInput) {
          iconInput.value = picked;
        }
      });
    }

    // Color input — update hex display
    const colorInput = root.querySelector('#et-color-input');
    const colorHex = root.querySelector('#et-color-hex');
    if (colorInput && colorHex) {
      colorInput.addEventListener('input', () => {
        colorHex.textContent = colorInput.value;
      });
    }

    // Submit form
    const submitBtn = root.querySelector('#et-form-submit');
    if (submitBtn) {
      submitBtn.addEventListener('click', () => this._saveEventTypeForm());
    }

    // Cancel form
    const cancelBtn = root.querySelector('#et-form-cancel');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => {
        this._editingEventType = null;
        this._eventTypeFormError = null;
        this._render();
      });
    }
  }
  _instantLog = withCooldown(function(btn, type) {
    /* U7 — debounce: set pending, re-enable after service call */
    if (btn && btn.dataset && btn.dataset.pending) return;
    if (btn) btn.dataset.pending = '1';
    this._logEvent(type)
      .then(() => {
        if (btn) {
          delete btn.dataset.pending;
          btn.classList.remove('flash');
          void btn.offsetWidth;
          btn.classList.add('flash');
          btn.addEventListener('animationend', () => btn.classList.remove('flash'), { once: true });
        }
      })
      .catch(() => {
        if (btn) delete btn.dataset.pending;
      });
  }, 500);

  /* ── Backdate form ─────────────────────────────────────────────────── */
  _openBackdateForm(activeBtn, type) {
    this._activeForm = 'backdate';
    this._activeType = type;
    this._activeTriggerBtn = activeBtn;

    const { registry } = this._registry();
    const meta = getMeta(type, registry);
    const formEl = this.shadowRoot.getElementById('inline-form');
    /* U10 — proper <label for> on all inputs */
    formEl.innerHTML = `
      <div class="form-title">${meta.emoji} Log ${_escapeHTML(meta.label)}</div>
      <div class="form-field">
        <div class="form-label-row">
          <label class="form-label" for="minutes-slider">Minutes ago</label>
          <span class="slider-value" id="slider-display">Now</span>
        </div>
        <input type="range" id="minutes-slider" min="0" max="480" step="1" value="0" aria-label="Minutes ago" />
      </div>
      <div class="form-field">
        <label class="form-label" for="backdate-note">Note (optional)</label>
        <input type="text" id="backdate-note" placeholder="Add a note…" />
      </div>
      <div class="form-error" id="form-error" role="alert"></div>
      <div class="form-actions">
        <button class="btn-cancel" id="form-cancel">Cancel</button>
        <button class="btn-submit" id="form-submit">Log Event</button>
      </div>
    `;

    const slider = formEl.querySelector('#minutes-slider');
    const display = formEl.querySelector('#slider-display');
    const _updateSliderDisplay = () => {
      const v = parseInt(slider.value, 10);
      const t = new Date(Date.now() - v * 60000);
      const timeStr = t.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
      display.textContent = (v === 0 ? 'Now' : v === 1 ? '1 min ago' : `${v} min ago`) + ` · ${timeStr}`;
    };
    slider.addEventListener('input', _updateSliderDisplay);
    _updateSliderDisplay();

    formEl.querySelector('#form-cancel').addEventListener('click', () => this._closeForm());
    formEl.querySelector('#form-submit').addEventListener('click', () => {
      const minutesAgo = parseInt(slider.value, 10);
      const note = formEl.querySelector('#backdate-note').value.trim();
      const timestamp = new Date(Date.now() - minutesAgo * 60000).toISOString();
      this._submitBackdate(activeBtn, type, timestamp, note || undefined);
    });

    this._applyFormOpenState(activeBtn);
  }

  /* ── Weight form ───────────────────────────────────────────────────── */
  _openWeightForm(activeBtn) {
    this._activeForm = 'weight';
    this._activeType = 'weight';
    this._activeTriggerBtn = activeBtn;

    const ent = this._entities();
    const unit = this._weightUnit();
    const currentWeight = toDisplayWeight(stateNum(this._hass, ent.weight), unit);

    const formEl = this.shadowRoot.getElementById('inline-form');
    /* U10 — <label for>, U21 — inputmode="decimal", U22 — configurable unit */
    formEl.innerHTML = `
      <div class="form-title">⚖️ Log Weight</div>
      <div class="form-field">
        <label class="form-label" for="weight-input">Weight (${_escapeHTML(unit)})</label>
        <div class="weight-input-row">
          <input type="number" id="weight-input" min="1" max="999" step="0.1"
            inputmode="decimal"
            value="${currentWeight !== null ? currentWeight : ''}"
            placeholder="0.0" />
          <span class="weight-unit">${_escapeHTML(unit)}</span>
        </div>
      </div>
      <div class="form-error" id="form-error" role="alert"></div>
      <div class="form-actions">
        <button class="btn-cancel" id="form-cancel">Cancel</button>
        <button class="btn-submit" id="form-submit">Log Weight</button>
      </div>
    `;

    formEl.querySelector('#form-cancel').addEventListener('click', () => this._closeForm());
    formEl.querySelector('#form-submit').addEventListener('click', () => {
      const weightInput = formEl.querySelector('#weight-input');
      const value = parseFloat(weightInput.value);
      if (isNaN(value) || value < 1 || value > 999) {
        weightInput.style.outline = '2px solid var(--error-color, #ef5350)';
        weightInput.focus();
        return;
      }
      /* If unit is kg, convert to lbs before storing (store is always lbs) */
      const valueLbs = unit === 'kg' ? Math.round(value * 2.20462 * 10) / 10 : value;
      this._submitWeight(activeBtn, valueLbs);
    });

    this._applyFormOpenState(activeBtn);
  }

  /* ── Edit form for existing event ───────────────────────────────────── */
  _openEditForm(eventType, timestamp, note, value, eventId) {
    this._activeForm = 'edit';
    this._activeType = eventType;
    this._editEventId = eventId;

    const { registry } = this._registry();
    const meta = getMeta(eventType, registry);
    const isWeight = eventType === 'weight';
    const unit = this._weightUnit();

    // Calculate minutes ago from timestamp
    let minutesAgo = 0;
    if (timestamp) {
      const diff = Date.now() - new Date(timestamp).getTime();
      minutesAgo = Math.max(0, Math.round(diff / 60000));
    }

    const formEl = this.shadowRoot.getElementById('inline-form');

    if (isWeight) {
      const displayVal = value ? (unit === 'kg' ? Math.round(value / 2.20462 * 10) / 10 : value) : '';
      formEl.innerHTML = `
        <div class="form-title">⚖️ Edit Weight</div>
        <div class="form-field">
          <label class="form-label" for="weight-input">Weight (${_escapeHTML(unit)})</label>
          <div class="weight-input-row">
            <input type="number" id="weight-input" min="1" max="999" step="0.1"
              inputmode="decimal"
              value="${displayVal}"
              placeholder="0.0" />
            <span class="weight-unit">${_escapeHTML(unit)}</span>
          </div>
        </div>
        <div class="form-error" id="form-error" role="alert"></div>
        <div class="form-actions">
          <button class="btn-cancel" id="form-cancel">Cancel</button>
          <button class="btn-submit" id="form-submit">Update Weight</button>
        </div>
      `;
      formEl.querySelector('#form-cancel').addEventListener('click', () => this._closeForm());
      formEl.querySelector('#form-submit').addEventListener('click', () => {
        const wInput = formEl.querySelector('#weight-input');
        const w = parseFloat(wInput.value);
        if (isNaN(w) || w < 1 || w > 999) {
          wInput.style.outline = '2px solid var(--error-color, #ef5350)';
          wInput.focus();
          return;
        }
        const valueLbs = unit === 'kg' ? Math.round(w * 2.20462 * 10) / 10 : w;
        this._submitEdit({ value: valueLbs });
      });
    } else {
      formEl.innerHTML = `
        <div class="form-title">${meta.emoji} Edit ${_escapeHTML(meta.label)}</div>
        <div class="form-field">
          <div class="form-label-row">
            <label class="form-label" for="minutes-slider">Minutes ago</label>
            <span class="slider-value" id="slider-display">Now</span>
          </div>
          <input type="range" id="minutes-slider" min="0" max="480" step="1" value="${minutesAgo}" aria-label="Minutes ago" />
        </div>
        <div class="form-field">
          <label class="form-label" for="backdate-note">Note (optional)</label>
          <input type="text" id="backdate-note" placeholder="Add a note…" value="${_escapeHTML(note || '')}" />
        </div>
        <div class="form-error" id="form-error" role="alert"></div>
        <div class="form-actions">
          <button class="btn-cancel" id="form-cancel">Cancel</button>
          <button class="btn-submit" id="form-submit">Update Event</button>
        </div>
      `;

      const slider = formEl.querySelector('#minutes-slider');
      const display = formEl.querySelector('#slider-display');
      const _updateSliderDisplay = () => {
        const v = parseInt(slider.value, 10);
        const t = new Date(Date.now() - v * 60000);
        const timeStr = t.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
        display.textContent = (v === 0 ? 'Now' : v === 1 ? '1 min ago' : `${v} min ago`) + ` · ${timeStr}`;
      };
      slider.addEventListener('input', _updateSliderDisplay);
      _updateSliderDisplay();

      formEl.querySelector('#form-cancel').addEventListener('click', () => this._closeForm());
      formEl.querySelector('#form-submit').addEventListener('click', () => {
        const minutesAgoVal = parseInt(slider.value, 10);
        const noteVal = formEl.querySelector('#backdate-note').value.trim();
        const ts = new Date(Date.now() - minutesAgoVal * 60000).toISOString();
        const updates = { timestamp: ts };
        if (noteVal) updates.note = noteVal;
        else updates.note = '';  // clear note if empty
        this._submitEdit(updates);
      });
    }

    this._applyFormOpenState(null);
  }

  _submitEdit(updates) {
    const eventId = this._editEventId;
    if (!eventId) return;

    updateEvent(this._hass, eventId, updates)
      .then(() => {
        this._setTimeout(() => {
          this._closeForm();
          this._setTimeout(() => { this._lastHash = null; }, 1500);
        }, 600);
      })
      .catch(err => {
        console.error('[pawsistant-card] update_event failed:', err);
        this._showFormError('Failed to update event. Please try again.');
      });
  }

  /* ── Apply visual state when form opens ───────────────────────────── */
  _applyFormOpenState(activeBtn) {
    this.shadowRoot.querySelectorAll('.log-btn').forEach(b => {
      if (b === activeBtn) {
        b.classList.add('active-btn');
        b.classList.remove('dimmed');
      } else {
        b.classList.add('dimmed');
        b.classList.remove('active-btn');
      }
    });

    const wrap = this.shadowRoot.getElementById('inline-form-wrap');
    void wrap.offsetWidth;
    wrap.classList.add('open');

    // Focus first input after animation
    this._setTimeout(() => {
      const first = this.shadowRoot.querySelector('#inline-form input');
      if (first) first.focus();
    }, 300);
  }

  /* ── Close form ────────────────────────────────────────────────────── */
  _closeForm() {
    const triggerBtn = this._activeTriggerBtn;
    this._activeForm = null;
    this._activeType = null;
    this._activeTriggerBtn = null;
    this._editEventId = null;

    const wrap = this.shadowRoot.getElementById('inline-form-wrap');
    if (wrap) wrap.classList.remove('open');

    this.shadowRoot.querySelectorAll('.log-btn').forEach(b => {
      b.classList.remove('dimmed', 'active-btn');
    });

    /* U17 — return focus to trigger button */
    if (triggerBtn) {
      this._setTimeout(() => triggerBtn.focus(), 50);
    }
  }

  /* ── Show form error ───────────────────────────────────────────────── */
  _showFormError(msg) {
    const el = this.shadowRoot.querySelector('#form-error');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('visible');
  }

  /* ── Submit backdate ───────────────────────────────────────────────── */
  _submitBackdate(btn, type, timestamp, note) {
    const extra = { timestamp };
    if (note) extra.note = note;

    logEvent(this._hass, this._config.dog, type, extra)
      .then(() => {
        this._showSuccessFlash(btn);
        this._setTimeout(() => {
          this._closeForm();
          this._setTimeout(() => { this._lastHash = null; }, 1500);
        }, 600);
      })
      .catch(err => {
        /* U11 — show error in form instead of just console.error */
        console.error('[pawsistant-card] log_event (backdate) failed:', err);
        this._showFormError('Failed to log event. Please try again.');
      });
  }

  /* ── Submit weight ─────────────────────────────────────────────────── */
  _submitWeight(btn, value) {
    logEvent(this._hass, this._config.dog, 'weight', { value })
      .then(() => {
        this._showSuccessFlash(btn);
        this._setTimeout(() => {
          this._closeForm();
          this._setTimeout(() => { this._lastHash = null; }, 1500);
        }, 600);
      })
      .catch(err => {
        /* U11 — show error in form */
        console.error('[pawsistant-card] log_event (weight) failed:', err);
        this._showFormError('Failed to log weight. Please try again.');
      });
  }

  /* ── Success flash ─────────────────────────────────────────────────── */
  _showSuccessFlash(btn) {
    const originalHTML = btn.innerHTML;
    btn.innerHTML = `<span class="btn-emoji" aria-hidden="true">✓</span>`;
    btn.classList.add('success-flash');
    this._setTimeout(() => {
      btn.innerHTML = originalHTML;
      btn.classList.remove('success-flash');
    }, 600);
  }

  /* ── Service calls ─────────────────────────────────────────────────── */
  _logEvent(eventType, extra = {}) {
    return logEvent(this._hass, this._config.dog, eventType, extra);
  }

  _deleteEvent(eventId, btn) {
    /* U7 — debounce via pending attr */
    if (btn) btn.dataset.pending = '1';
    deleteEvent(this._hass, eventId).then(() => {
      if (btn) delete btn.dataset.pending;
    }).catch(err => {
      console.error('[pawsistant-card] delete_event failed:', err);
      if (btn) {
        delete btn.dataset.pending;
        /* U11 — flash error on delete failure */
        const row = btn.closest('.event-row');
        if (row) {
          row.style.background = 'color-mix(in srgb, var(--error-color, #ef5350) 15%, transparent)';
          this._setTimeout(() => { row.style.background = ''; }, 2000);
        }
      }
    });
  }

  getCardSize() { return 6; }
}

customElements.define('pawsistant-card', PawsistantCard);
