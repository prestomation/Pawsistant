/**
 * Pawsistant Card — All-in-one dog activity dashboard for Home Assistant
 * Bundled with the ha-doglog (Pawsistant) integration — no manual setup required.
 * Version: 2.1.0
 */

/* ── Card picker registration ───────────────────────────────────────────── */
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'pawsistant-card',
  name: 'Pawsistant',
  description: 'All-in-one dog activity tracker — log events, view timeline, track stats',
  preview: true,
});

/* ── Event-type metadata ────────────────────────────────────────────────── */
const EVENT_META = {
  poop:     { emoji: '💩', label: 'Poop',     color: '#8B4513' },
  pee:      { emoji: '💧', label: 'Pee',      color: '#4FC3F7' },
  medicine: { emoji: '💊', label: 'Medicine', color: '#AB47BC' },
  sick:     { emoji: '🤒', label: 'Sick',     color: '#EF5350' },
  food:     { emoji: '🍖', label: 'Food',     color: '#FF8A65' },
  treat:    { emoji: '🍪', label: 'Treat',    color: '#FFCA28' },
  walk:     { emoji: '🦮', label: 'Walk',     color: '#66BB6A' },
  water:    { emoji: '🥤', label: 'Water',    color: '#29B6F6' },
  sleep:    { emoji: '😴', label: 'Sleep',    color: '#7E57C2' },
  vaccine:  { emoji: '💉', label: 'Vaccine',  color: '#26A69A' },
  training: { emoji: '🎓', label: 'Training', color: '#5C6BC0' },
  weight:   { emoji: '⚖️',  label: 'Weight',   color: '#78909C' },
  teeth_brushing: { emoji: '🦷', label: 'Teeth', color: '#B0BEC5' },
  grooming: { emoji: '✂️',  label: 'Grooming', color: '#EC407A' },
};

function getMeta(type) {
  return EVENT_META[type] || { emoji: '📝', label: type, color: '#888' };
}

/* ── Utilities ──────────────────────────────────────────────────────────── */
function slugify(name) {
  return name.toLowerCase().replace(/\s+/g, '_');
}

function deriveEntities(dog) {
  const s = slugify(dog);
  return {
    timeline:         `sensor.${s}_recent_timeline`,
    pee_count:        `sensor.${s}_daily_pee_count`,
    poop_count:       `sensor.${s}_poop_count_today`,
    medicine_days:    `sensor.${s}_days_since_medicine`,
    weight:           `sensor.${s}_weight`,
  };
}

function stateNum(hass, entity) {
  if (!entity || !hass.states[entity]) return null;
  const val = parseFloat(hass.states[entity].state);
  return isNaN(val) ? null : val;
}

function stateStr(hass, entity) {
  if (!entity || !hass.states[entity]) return null;
  const s = hass.states[entity].state;
  if (s === 'unavailable' || s === 'unknown') return null;
  return s;
}

function stateAttr(hass, entity, attr) {
  if (!entity || !hass.states[entity]) return null;
  return hass.states[entity].attributes[attr] ?? null;
}

/** Simple hash of the relevant state for render diffing */
function buildHash(hass, cfg) {
  const entities = deriveEntities(cfg.dog || '');
  const tEnt = cfg.timeline_entity || entities.timeline;
  const peeEnt = cfg.pee_count_entity || entities.pee_count;
  const poopEnt = cfg.poop_count_entity || entities.poop_count;
  const medEnt = cfg.medicine_days_entity || entities.medicine_days;
  const parts = [
    stateStr(hass, tEnt) || '',
    stateStr(hass, peeEnt) || '',
    stateStr(hass, poopEnt) || '',
    stateStr(hass, medEnt) || '',
    JSON.stringify(stateAttr(hass, tEnt, 'events') || []),
  ];
  return parts.join('|');
}

/* ── Shared escape helper (XSS prevention) ──────────────────────────────── */
// C7 — Extracted from PawsistantCard so PawsistantCardEditor can use it too
function _escapeHTML(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ── Editor element ─────────────────────────────────────────────────────── */
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
  set hass(h) { this.__hass = h; }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    const cfg = this._config;
    // C7 — Escape all config values before injecting into innerHTML
    const esc = _escapeHTML;
    this.shadowRoot.innerHTML = `
      <style>
        .form { display: flex; flex-direction: column; gap: 12px; padding: 8px 0; }
        label { font-size: 12px; color: var(--secondary-text-color); margin-bottom: 2px; display: block; }
        input {
          width: 100%;
          box-sizing: border-box;
          padding: 8px 10px;
          border: 1px solid var(--divider-color);
          border-radius: 6px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font-size: 14px;
        }
        input:focus { outline: 2px solid var(--primary-color); border-color: transparent; }
        .hint { font-size: 11px; color: var(--secondary-text-color); margin-top: 2px; }
      </style>
      <div class="form">
        <div>
          <label>Dog name *</label>
          <input name="dog" value="${esc(cfg.dog || '')}" placeholder="Sharky" />
        </div>
        <div>
          <label>Timeline entity (auto-detected from dog name)</label>
          <input name="timeline_entity" value="${esc(cfg.timeline_entity || '')}" placeholder="sensor.sharky_recent_timeline" />
          <div class="hint">Leave blank to auto-detect</div>
        </div>
        <div>
          <label>Pee count entity</label>
          <input name="pee_count_entity" value="${esc(cfg.pee_count_entity || '')}" placeholder="sensor.sharky_daily_pee_count" />
          <div class="hint">Leave blank to auto-detect</div>
        </div>
        <div>
          <label>Poop count entity</label>
          <input name="poop_count_entity" value="${esc(cfg.poop_count_entity || '')}" placeholder="sensor.sharky_poop_count_today" />
          <div class="hint">Leave blank to auto-detect</div>
        </div>
        <div>
          <label>Days since medicine entity</label>
          <input name="medicine_days_entity" value="${esc(cfg.medicine_days_entity || '')}" placeholder="sensor.sharky_days_since_medicine" />
          <div class="hint">Leave blank to auto-detect</div>
        </div>
        <div>
          <label>Weight entity (optional)</label>
          <input name="weight_entity" value="${esc(cfg.weight_entity || '')}" placeholder="sensor.sharky_weight" />
          <div class="hint">Leave blank to auto-detect</div>
        </div>
      </div>
    `;

    this.shadowRoot.querySelectorAll('input').forEach(input => {
      input.addEventListener('change', () => this._valueChanged());
    });
  }

  _valueChanged() {
    const newConfig = { ...this._config };
    this.shadowRoot.querySelectorAll('input').forEach(input => {
      const key = input.name;
      const val = input.value.trim();
      if (val) newConfig[key] = val;
      else delete newConfig[key];
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
    this._loggedTypes = new Set();
    // Inline form state
    this._activeForm = null; // null | 'backdate' | 'weight'
    this._activeType = null; // event type for backdate form
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
      // Don't re-render if a form is open — would destroy it
      if (!this._activeForm) {
        this._render();
      }
    }
  }

  /* ── Entity resolution ─────────────────────────────────────────────── */
  _entities() {
    const auto = deriveEntities(this._config.dog);
    return {
      timeline:      this._config.timeline_entity      || auto.timeline,
      pee_count:     this._config.pee_count_entity     || auto.pee_count,
      poop_count:    this._config.poop_count_entity    || auto.poop_count,
      medicine_days: this._config.medicine_days_entity || auto.medicine_days,
      weight:        this._config.weight_entity        || auto.weight,
    };
  }

  /* ── Render ────────────────────────────────────────────────────────── */
  _render() {
    const hass = this._hass;
    if (!hass) return;

    const cfg = this._config;
    const ent = this._entities();
    const dogName = cfg.dog;

    const peeCount = stateNum(hass, ent.pee_count);
    const poopCount = stateNum(hass, ent.poop_count);
    const medDays = stateNum(hass, ent.medicine_days);
    const events = stateAttr(hass, ent.timeline, 'events') || [];

    const medColor = medDays === null ? '#888' :
                     medDays > 30 ? '#EF5350' :
                     medDays > 14 ? '#FFA726' : '#66BB6A';

    const medLabel = medDays === null ? 'unknown' : `${Math.floor(medDays)}d`;

    /* Build timeline HTML */
    let timelineHTML = '';
    if (events.length === 0) {
      timelineHTML = '<div class="empty">No events in the last 24 hours</div>';
    } else {
      let lastDate = null;
      for (const ev of events) {
        const meta = getMeta(ev.type);
        const evDate = ev.date || '';
        if (evDate !== lastDate) {
          const label = evDate || ev.day || '';
          timelineHTML += `<div class="day-header">${label}</div>`;
          lastDate = evDate;
        }
        const noteHTML = ev.note ? `<span class="event-note">${this._escape(ev.note)}</span>` : '';
        timelineHTML += `
          <div class="event-row" data-id="${ev.event_id}">
            <span class="event-emoji">${meta.emoji}</span>
            <span class="event-time">${ev.time}</span>
            <span class="event-type">${meta.label}</span>
            ${noteHTML}
            <button class="delete-btn" data-id="${ev.event_id}" title="Delete event">🗑️</button>
          </div>
        `;
      }
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
        .stats-row {
          display: flex;
          gap: 6px;
          padding: 12px 16px;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
          justify-content: space-between;
        }
        .stat-pill {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 4px;
          padding: 5px 8px;
          border-radius: 20px;
          font-size: 12px;
          font-weight: 600;
          color: #fff;
          white-space: nowrap;
          flex: 1;
          min-width: 0;
        }
        .stat-pill .pill-val {
          font-size: 15px;
          font-weight: 700;
        }

        /* ── Quick-log grid ── */
        .quick-log {
          display: grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 8px;
          padding: 12px 16px 0;
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
          position: relative;
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
          color: #fff;
          box-shadow: 0 2px 8px rgba(33,150,243,0.35);
        }
        /* Flash animation on instant log */
        .log-btn.flash {
          animation: flash-anim 0.5s ease;
        }
        @keyframes flash-anim {
          0%   { box-shadow: 0 0 0 0 rgba(var(--rgb-primary-color, 33,150,243), 0.7); transform: scale(1); }
          30%  { box-shadow: 0 0 0 8px rgba(var(--rgb-primary-color, 33,150,243), 0.2); transform: scale(0.93); }
          100% { box-shadow: 0 0 0 0 rgba(var(--rgb-primary-color, 33,150,243), 0); transform: scale(1); }
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

        /* ── Inline form panel ── */
        .inline-form-wrap {
          overflow: hidden;
          max-height: 0;
          transition: max-height 0.28s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .inline-form-wrap.open {
          max-height: 400px;
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
          color: #fff;
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
        .timeline-body {
          padding: 0 8px 12px;
          max-height: 380px;
          overflow-y: auto;
        }
        .day-header {
          font-size: 11px;
          font-weight: 700;
          color: var(--secondary-text-color);
          text-transform: uppercase;
          letter-spacing: 0.08em;
          padding: 8px 8px 4px;
        }
        .event-row {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 7px 8px;
          border-radius: 8px;
          transition: background 0.15s;
        }
        .event-row:hover { background: var(--secondary-background-color, #f5f5f5); }
        .event-emoji { font-size: 18px; flex-shrink: 0; width: 24px; text-align: center; }
        .event-time { font-size: 12px; color: var(--secondary-text-color); white-space: nowrap; flex-shrink: 0; min-width: 65px; }
        .event-type { font-size: 13px; font-weight: 500; color: var(--primary-text-color); flex-shrink: 0; }
        .event-note { font-size: 12px; color: var(--secondary-text-color); flex: 1; font-style: italic; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .delete-btn {
          background: none;
          border: none;
          cursor: pointer;
          opacity: 0.4;
          font-size: 14px;
          padding: 4px;
          border-radius: 4px;
          transition: opacity 0.15s, background 0.15s;
          flex-shrink: 0;
          margin-left: auto;
        }
        .delete-btn:hover { opacity: 1; background: rgba(239,83,80,0.12); }
        .empty {
          text-align: center;
          padding: 24px;
          color: var(--secondary-text-color);
          font-size: 14px;
        }
        @media (max-width: 420px) {
          .quick-log { grid-template-columns: repeat(5, 1fr); gap: 5px; padding: 10px 10px 0; }
          .log-btn { padding: 8px 2px; min-height: 54px; }
          .log-btn .btn-emoji { font-size: 20px; }
          .log-btn .btn-label { font-size: 10px; }
        }
      </style>
      <ha-card class="card">
        <div class="card-header">
          <span class="card-title">🐾 ${this._escape(dogName)}</span>
        </div>

        <div class="stats-row">
          <div class="stat-pill" style="background:#4FC3F7;">
            <span>💧</span>
            <span class="pill-val">${peeCount !== null ? peeCount : '—'}</span>
            <span>pee</span>
          </div>
          <div class="stat-pill" style="background:#8B6914;">
            <span>💩</span>
            <span class="pill-val">${poopCount !== null ? poopCount : '—'}</span>
            <span>poop</span>
          </div>
          <div class="stat-pill" style="background:${medColor};">
            <span>💊</span>
            <span class="pill-val">${medLabel}</span>
            <span>meds</span>
          </div>
        </div>

        <div class="quick-log-section">
          <div class="quick-log">
            <button class="log-btn" data-type="poop" data-longpress="true">
              <span class="btn-emoji">💩</span>
              <span class="btn-label">Poop</span>
            </button>
            <button class="log-btn" data-type="pee" data-longpress="true">
              <span class="btn-emoji">💧</span>
              <span class="btn-label">Pee</span>
            </button>
            <button class="log-btn" data-type="medicine" data-longpress="true">
              <span class="btn-emoji">💊</span>
              <span class="btn-label">Medicine</span>
            </button>
            <button class="log-btn" data-type="sick" data-longpress="true">
              <span class="btn-emoji">🤒</span>
              <span class="btn-label">Sick</span>
            </button>
            <button class="log-btn" data-type="weight" data-weight="true">
              <span class="btn-emoji">⚖️</span>
              <span class="btn-label">Weight</span>
            </button>
          </div>

          <!-- Inline form panel (hidden by default) -->
          <div class="inline-form-wrap" id="inline-form-wrap">
            <div class="inline-form" id="inline-form">
              <!-- content injected by _openBackdateForm / _openWeightForm -->
            </div>
          </div>
        </div>

        <div class="timeline-header">📋 Last 24 hours</div>
        <div class="timeline-body">${timelineHTML}</div>
      </ha-card>
    `;

    this._attachListeners();
  }

  /* ── Attach listeners ──────────────────────────────────────────────── */
  _attachListeners() {
    const root = this.shadowRoot;

    root.querySelectorAll('.log-btn').forEach(btn => {
      const isWeight = btn.dataset.weight === 'true';
      const hasLongPress = btn.dataset.longpress === 'true';

      if (isWeight) {
        // Weight: tap always opens form
        btn.addEventListener('pointerdown', (e) => {
          e.preventDefault();
        });
        btn.addEventListener('pointerup', (e) => {
          e.preventDefault();
          if (this._activeForm === 'weight') {
            this._closeForm();
          } else {
            this._openWeightForm(btn);
          }
        });
        return;
      }

      if (hasLongPress) {
        let pressTimer = null;
        let didLongPress = false;

        const startPress = (e) => {
          e.preventDefault();
          didLongPress = false;
          pressTimer = setTimeout(() => {
            didLongPress = true;
            const type = btn.dataset.type;
            if (this._activeForm === 'backdate' && this._activeType === type) {
              this._closeForm();
            } else {
              this._openBackdateForm(btn, type);
            }
          }, 500);
        };

        const endPress = (e) => {
          if (pressTimer) {
            clearTimeout(pressTimer);
            pressTimer = null;
          }
          if (!didLongPress && e.type !== 'pointerleave' && e.type !== 'pointercancel') {
            // Normal tap — instant log (only if no form open for this button)
            const type = btn.dataset.type;
            this._instantLog(btn, type);
          }
          didLongPress = false;
        };

        btn.addEventListener('pointerdown', startPress);
        btn.addEventListener('pointerup', endPress);
        btn.addEventListener('pointerleave', endPress);
        btn.addEventListener('pointercancel', endPress);
        return;
      }

      // Fallback: simple click log
      btn.addEventListener('click', () => {
        this._instantLog(btn, btn.dataset.type);
      });
    });

    root.querySelectorAll('.delete-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const eventId = btn.dataset.id;
        if (!eventId) return;
        if (window.confirm('Delete this event?')) {
          this._deleteEvent(eventId);
        }
      });
    });
  }

  /* ── Instant log (tap) ─────────────────────────────────────────────── */
  _instantLog(btn, type) {
    this._logEvent(type);
    btn.classList.remove('flash');
    void btn.offsetWidth;
    btn.classList.add('flash');
    btn.addEventListener('animationend', () => btn.classList.remove('flash'), { once: true });
  }

  /* ── Backdate form ─────────────────────────────────────────────────── */
  _openBackdateForm(activeBtn, type) {
    this._activeForm = 'backdate';
    this._activeType = type;

    const meta = getMeta(type);
    const formEl = this.shadowRoot.getElementById('inline-form');
    formEl.innerHTML = `
      <div class="form-title">${meta.emoji} Log ${meta.label}</div>
      <div class="form-field">
        <div class="form-label-row">
          <span class="form-label">Minutes ago</span>
          <span class="slider-value" id="slider-display">10 min ago</span>
        </div>
        <input type="range" id="minutes-slider" min="10" max="180" step="5" value="10" />
      </div>
      <div class="form-field">
        <span class="form-label">Note (optional)</span>
        <input type="text" id="backdate-note" placeholder="Add a note…" />
      </div>
      <div class="form-actions">
        <button class="btn-cancel" id="form-cancel">Cancel</button>
        <button class="btn-submit" id="form-submit">Log Event</button>
      </div>
    `;

    // Update slider display
    const slider = formEl.querySelector('#minutes-slider');
    const display = formEl.querySelector('#slider-display');
    slider.addEventListener('input', () => {
      display.textContent = `${slider.value} min ago`;
    });

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

    const ent = this._entities();
    const currentWeight = stateNum(this._hass, ent.weight);

    const formEl = this.shadowRoot.getElementById('inline-form');
    formEl.innerHTML = `
      <div class="form-title">⚖️ Log Weight</div>
      <div class="form-field">
        <span class="form-label">Weight</span>
        <div class="weight-input-row">
          <input type="number" id="weight-input" min="1" max="300" step="0.1"
            value="${currentWeight !== null ? currentWeight : ''}"
            placeholder="0.0" />
          <span class="weight-unit">lbs</span>
        </div>
      </div>
      <div class="form-actions">
        <button class="btn-cancel" id="form-cancel">Cancel</button>
        <button class="btn-submit" id="form-submit">Log Weight</button>
      </div>
    `;

    formEl.querySelector('#form-cancel').addEventListener('click', () => this._closeForm());
    formEl.querySelector('#form-submit').addEventListener('click', () => {
      const weightInput = formEl.querySelector('#weight-input');
      const value = parseFloat(weightInput.value);
      // I6 — Updated validation range from [20, 150] to [1, 300]
      if (isNaN(value) || value < 1 || value > 300) {
        weightInput.style.outline = '2px solid #ef5350';
        weightInput.focus();
        return;
      }
      this._submitWeight(activeBtn, value);
    });

    this._applyFormOpenState(activeBtn);
  }

  /* ── Apply visual state when form opens ───────────────────────────── */
  _applyFormOpenState(activeBtn) {
    // Dim all other buttons, highlight active
    this.shadowRoot.querySelectorAll('.log-btn').forEach(b => {
      if (b === activeBtn) {
        b.classList.add('active-btn');
        b.classList.remove('dimmed');
      } else {
        b.classList.add('dimmed');
        b.classList.remove('active-btn');
      }
    });

    // Slide open
    const wrap = this.shadowRoot.getElementById('inline-form-wrap');
    // Force reflow before adding 'open' so transition fires
    void wrap.offsetWidth;
    wrap.classList.add('open');

    // Focus first input after animation
    setTimeout(() => {
      const first = this.shadowRoot.querySelector('#inline-form input');
      if (first) first.focus();
    }, 300);
  }

  /* ── Close form ────────────────────────────────────────────────────── */
  _closeForm() {
    this._activeForm = null;
    this._activeType = null;

    const wrap = this.shadowRoot.getElementById('inline-form-wrap');
    if (wrap) wrap.classList.remove('open');

    this.shadowRoot.querySelectorAll('.log-btn').forEach(b => {
      b.classList.remove('dimmed', 'active-btn');
    });
  }

  /* ── Submit backdate ───────────────────────────────────────────────── */
  _submitBackdate(btn, type, timestamp, note) {
    const payload = {
      dog: this._config.dog,
      event_type: type,
      timestamp: timestamp,
    };
    if (note) payload.note = note;

    this._hass.callService('doglog', 'log_event', payload)
      .then(() => {
        this._showSuccessFlash(btn);
        setTimeout(() => {
          this._closeForm();
          // Force re-render after state propagates
          setTimeout(() => {
            this._lastHash = null;
          }, 1500);
        }, 600);
      })
      .catch(err => {
        console.error('[pawsistant-card] log_event (backdate) failed:', err);
      });
  }

  /* ── Submit weight ─────────────────────────────────────────────────── */
  _submitWeight(btn, value) {
    this._hass.callService('doglog', 'log_event', {
      dog: this._config.dog,
      event_type: 'weight',
      value: value,
    })
      .then(() => {
        this._showSuccessFlash(btn);
        setTimeout(() => {
          this._closeForm();
          setTimeout(() => {
            this._lastHash = null;
          }, 1500);
        }, 600);
      })
      .catch(err => {
        console.error('[pawsistant-card] log_event (weight) failed:', err);
      });
  }

  /* ── Success flash ─────────────────────────────────────────────────── */
  _showSuccessFlash(btn) {
    // Show ✓ temporarily
    const originalHTML = btn.innerHTML;
    btn.innerHTML = `<span class="btn-emoji">✓</span>`;
    btn.classList.add('success-flash');
    setTimeout(() => {
      btn.innerHTML = originalHTML;
      btn.classList.remove('success-flash');
    }, 600);
  }

  /* ── Service calls ─────────────────────────────────────────────────── */
  _logEvent(eventType, extra = {}) {
    this._hass.callService('doglog', 'log_event', {
      dog: this._config.dog,
      event_type: eventType,
      ...extra,
    }).catch(err => {
      console.error('[pawsistant-card] log_event failed:', err);
    });
  }

  _deleteEvent(eventId) {
    this._hass.callService('doglog', 'delete_event', {
      event_id: eventId,
    }).catch(err => {
      console.error('[pawsistant-card] delete_event failed:', err);
    });
  }

  /* ── Helpers ───────────────────────────────────────────────────────── */
  // C7 — Delegate to the shared module-level escape function
  _escape(str) { return _escapeHTML(str); }

  getCardSize() { return 6; }
}

customElements.define('pawsistant-card', PawsistantCard);
