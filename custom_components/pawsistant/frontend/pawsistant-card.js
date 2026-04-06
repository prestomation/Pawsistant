/**
 * Pawsistant Card — All-in-one pet activity dashboard for Home Assistant
 * Bundled with the Pawsistant integration — no manual setup required.
 * Version: 2.8.1
 */

/* ── Card picker registration ───────────────────────────────────────────── */
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'pawsistant-card',
  name: 'Pawsistant',
  description: 'All-in-one pet activity tracker — log events, view timeline, track stats',
  preview: true,
});

/* ── Event-type metadata ────────────────────────────────────────────────── */
// Fallback registry — used when WS state hasn't been populated yet.
// The card reads live registry from sensor attributes; these values are
// retained as defaults so the card renders before any sensor has reported.
const FALLBACK_EVENT_META = {
  poop:     { emoji: '💩', label: 'Poop',     color: 'var(--warning-color, #FF8A65)' },
  pee:      { emoji: '💧', label: 'Pee',      color: 'var(--info-color, #4FC3F7)' },
  medicine: { emoji: '💊', label: 'Medicine', color: 'var(--error-color, #EF5350)' },
  sick:     { emoji: '🤒', label: 'Sick',     color: 'var(--error-color, #EF5350)' },
  food:     { emoji: '🍖', label: 'Food',     color: 'var(--warning-color, #FF8A65)' },
  treat:    { emoji: '🍪', label: 'Treat',    color: 'var(--warning-color, #FFCA28)' },
  walk:     { emoji: '🦮', label: 'Walk',     color: 'var(--success-color, #66BB6A)' },
  water:    { emoji: '🥤', label: 'Water',    color: 'var(--info-color, #29B6F6)' },
  sleep:    { emoji: '😴', label: 'Sleep',    color: 'var(--info-color, #7E57C2)' },
  vaccine:  { emoji: '💉', label: 'Vaccine',  color: 'var(--info-color, #26A69A)' },
  training: { emoji: '🎓', label: 'Training', color: 'var(--info-color, #5C6BC0)' },
  weight:   { emoji: '⚖️',  label: 'Weight',   color: 'var(--secondary-text-color, #78909C)' },
  teeth:    { emoji: '🦷', label: 'Teeth',   color: 'var(--secondary-text-color, #B0BEC5)' },
  grooming: { emoji: '✂️',  label: 'Grooming', color: 'var(--warning-color, #EC407A)' },
};
// Alias for backwards compat — old card config YAML may reference EVENT_META
const EVENT_META = FALLBACK_EVENT_META;

const DEFAULT_SHOWN_TYPES = ['poop', 'pee', 'medicine', 'sick', 'weight'];

/** Human-readable labels for button metric values */
const METRIC_LABELS = {
  daily_count: (n) => `${n} today`,
  days_since:  (n) => `${n} days`,
  last_value:  (v, unit) => `${v}${unit ? ' ' + unit : ''}`,
  hours_since: (n) => `${n} hours`,
};

/**
 * Build the dynamic event-type registry from sensor attributes.
 * Reads from any Pawsistant sensor's `event_types` attribute (a dict
 * of {key: {name, icon, color}}).  Falls back to FALLBACK_EVENT_META.
 *
 * Also reads `button_metrics` ({key: metric_name}) for button labels.
 */
function buildRegistry(hass) {
  // Deep-copy fallback as the base
  const fallbackRegistry = {};
  for (const [k, v] of Object.entries(FALLBACK_EVENT_META)) {
    fallbackRegistry[k] = { ...v };
  }
  const metrics = {};
  let foundLiveTypes = false;
  let liveRegistry = {};

  if (hass && hass.states) {
    for (const state of Object.values(hass.states)) {
      const attrs = state.attributes || {};
      if (attrs.event_types && typeof attrs.event_types === 'object' && !Array.isArray(attrs.event_types) && Object.keys(attrs.event_types).length > 0) {
        foundLiveTypes = true;
        // Build registry from ONLY the live event_types (authoritative source).
        // This ensures deleted types (tombstones) don't appear — they're not in this dict.
        for (const [k, v] of Object.entries(attrs.event_types)) {
          if (v && typeof v === 'object') {
            const fallbackEntry = fallbackRegistry[k] || {};
            liveRegistry[k] = {
              // If live icon maps to 📝 (unknown icon), preserve fallback emoji instead of overwriting
              emoji:    v.icon ? (iconToEmoji(v.icon) !== '📝' ? iconToEmoji(v.icon) : (fallbackEntry.emoji || '📝')) : (fallbackEntry.emoji || '📝'),
              label:    v.name  || k,
              color:    v.color || fallbackEntry.color || '#888',
              icon:     v.icon  || '',
            };
          }
        }
      }
      if (attrs.button_metrics && typeof attrs.button_metrics === 'object') {
        Object.assign(metrics, attrs.button_metrics);
      }
      if (foundLiveTypes) {
        break;  // got live types from this sensor, use them
      }
    }
  }

  // Use live registry if we found one; otherwise fall back to defaults
  const registry = foundLiveTypes ? liveRegistry : fallbackRegistry;

  return { registry, metrics };
}

function getMeta(type, registry) {
  if (registry && registry[type]) {
    // Live registry: {emoji, label, icon, color} — emoji is pre-resolved by buildRegistry
    const entry = registry[type];
    // Use already-resolved emoji if available; only re-resolve if icon changed (entry.icon set, emoji undefined)
    const resolvedEmoji = (entry.emoji && entry.emoji !== '📝')
      ? entry.emoji
      : (entry.icon ? iconToEmoji(entry.icon) : (entry.emoji || '📝'));
    return {
      emoji: resolvedEmoji,
      label: entry.label || type,
      color: entry.color || 'var(--secondary-text-color, #888)',
      icon: entry.icon || '',
    };
  }
  const fallback = FALLBACK_EVENT_META[type];
  if (fallback) return { ...fallback, icon: '' };
  return { emoji: '📝', label: type, color: 'var(--secondary-text-color, #888)', icon: '' };
}

/** Map an MDI icon name (e.g. "mdi:walk") to a fallback emoji. */
function iconToEmoji(icon) {
  if (!icon) return undefined;  // undefined → getMeta uses fallback emoji from registry
  const map = {
    'mdi:walk': '🦮', 'mdi:food-drumstick': '🍖', 'mdi:cookie': '🍪',
    'mdi:bowl': '🍽️', 'mdi:cup-water': '🥤', 'mdi:water': '💧',
    'mdi:emoticon-poop': '💩', 'mdi:pill': '💊', 'mdi:scale-bathroom': '⚖️',
    'mdi:needle': '💉', 'mdi:sleep': '😴', 'mdi:content-cut': '✂️',
    'mdi:hand-pointing-up': '🎯', 'mdi:toothbrush': '🦷', 'mdi:emoticon-sick': '🤒',
    'mdi:tag': '🏷️', 'mdi:school': '🎓',
  };
  return map[icon] || '📝';
}

/* ── Utilities ──────────────────────────────────────────────────────────── */

/** U13 — slugify handles non-ASCII names (kept for fallback / YAML power users) */
function slugify(name) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
}

/**
 * Resolve entity IDs for a dog by scanning hass.states for sensors with
 * `attributes.dog === dogName` (case-insensitive) and matching by friendly_name
 * suffix. This is rename-safe: works even if the user renamed entity IDs in HA.
 *
 * Falls back to slug-derived IDs for any role not found via attribute scan.
 */
function findEntitiesByDog(hass, dogName) {
  const slug = slugify(dogName);
  const fallback = {
    timeline:      `sensor.${slug}_recent_timeline`,
    pee_count:     `sensor.${slug}_daily_pee_count`,
    poop_count:    `sensor.${slug}_poop_count_today`,
    medicine_days: `sensor.${slug}_days_since_medicine`,
    weight:        `sensor.${slug}_weight`,
  };

  if (!hass || !dogName) return fallback;

  const nameLower = dogName.toLowerCase();
  const result = { ...fallback };

  // Role → friendly_name suffix (matches HA's _attr_name / entity_description.name)
  const ROLE_SUFFIXES = {
    timeline:      'recent timeline',
    pee_count:     'daily pee count',
    poop_count:    'poop count today',
    medicine_days: 'days since medicine',
    weight:        'weight',
  };

  for (const [entityId, state] of Object.entries(hass.states)) {
    const attrDog = state.attributes && state.attributes.dog;
    if (!attrDog || attrDog.toLowerCase() !== nameLower) continue;

    const friendlyName = (state.attributes.friendly_name || '').toLowerCase();
    for (const [role, suffix] of Object.entries(ROLE_SUFFIXES)) {
      if (friendlyName.endsWith(suffix)) {
        result[role] = entityId;
        break;
      }
    }
  }

  return result;
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
  const entities = findEntitiesByDog(hass, cfg.dog || '');
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
    // Include registry hash so event-type edits trigger re-render
    JSON.stringify(stateAttr(hass, tEnt, 'event_types') || {}),
    JSON.stringify(stateAttr(hass, tEnt, 'button_metrics') || {}),
  ];
  return parts.join('|');
}

/* ── Shared escape helper (XSS prevention) ──────────────────────────────── */
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
    const currentShown = Array.isArray(cfg.shown_types) ? cfg.shown_types : DEFAULT_SHOWN_TYPES;
    const weightUnit = cfg.weight_unit || 'lbs';
    const buttonsPerRow = cfg.buttons_per_row != null ? String(cfg.buttons_per_row) : '';

    // Discover registered dog names from any sensor's `dog` attribute.
    // This is rename-safe: doesn't depend on entity ID patterns.
    const dogNames = this._dogNamesFromHass(this.__hass);

    // Build checkbox rows for every known event type
    const { registry } = buildRegistry(this.__hass);
    const allTypes = Object.keys(registry);
    const checkboxesHTML = allTypes.map(type => {
      const meta = getMeta(type, registry);
      const checked = currentShown.includes(type) ? 'checked' : '';
      return `
        <label class="type-checkbox">
          <input type="checkbox" name="shown_type_cb" value="${esc(type)}" ${checked} />
          <span class="type-chip">${meta.emoji} ${esc(meta.label)}</span>
        </label>`;
    }).join('');

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
        /* Checkbox grid for event types */
        .type-grid {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .type-checkbox {
          display: flex;
          align-items: center;
          gap: 0;
          cursor: pointer;
        }
        .type-checkbox input[type="checkbox"] {
          position: absolute;
          opacity: 0;
          width: 0;
          height: 0;
          pointer-events: none;
        }
        .type-chip {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 5px 10px;
          border-radius: 20px;
          font-size: 13px;
          border: 1px solid var(--divider-color);
          background: var(--secondary-background-color, #f5f5f5);
          color: var(--primary-text-color);
          cursor: pointer;
          transition: background 0.15s, border-color 0.15s, color 0.15s;
          user-select: none;
        }
        .type-checkbox input:checked + .type-chip {
          background: var(--primary-color, #2196f3);
          border-color: var(--primary-color, #2196f3);
          color: var(--text-primary-color, #fff);
        }
        .type-checkbox:focus-within .type-chip {
          outline: 2px solid var(--primary-color, #2196f3);
          outline-offset: 2px;
        }
        .max-hint {
          font-size: 11px;
          color: var(--secondary-text-color);
          margin-top: 4px;
        }
        .max-hint.over { color: var(--error-color, #EF5350); }
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
        <div>
          <span class="field-label">Shown buttons (tap to toggle, max 12)</span>
          <div class="type-grid" id="type-grid">
            ${checkboxesHTML}
          </div>
          <div class="max-hint" id="max-hint">${currentShown.length}/12 selected</div>
        </div>
        <div>
          <label class="field-label" for="ed-buttons-per-row">Buttons per row (2–6, leave blank for auto)</label>
          <input id="ed-buttons-per-row" name="buttons_per_row" type="number" min="2" max="6" value="${esc(buttonsPerRow)}" placeholder="auto" />
          <div class="hint">When set, buttons render in a CSS grid of N equal columns. When blank, flex-wrap is used.</div>
        </div>
      </div>
    `;

    // Attach listeners on text/select inputs
    this.shadowRoot.querySelectorAll('input[type="text"], input[type="number"], select').forEach(el => {
      el.addEventListener('change', () => this._valueChanged());
    });

    // Checkbox listeners — enforce max 12, update counter
    const hint = this.shadowRoot.getElementById('max-hint');
    this.shadowRoot.querySelectorAll('input[name="shown_type_cb"]').forEach(cb => {
      cb.addEventListener('change', () => {
        const checked = [...this.shadowRoot.querySelectorAll('input[name="shown_type_cb"]:checked')];
        if (checked.length > 12) {
          // Uncheck the one just checked
          cb.checked = false;
        }
        const count = Math.min(checked.length, 12);
        hint.textContent = `${count}/12 selected`;
        hint.className = count >= 12 ? 'max-hint over' : 'max-hint';
        this._valueChanged();
      });
    });
  }

  _valueChanged() {
    const newConfig = { ...this._config };

    // Scalar inputs
    this.shadowRoot.querySelectorAll('input[type="text"], input[type="number"], select').forEach(el => {
      const key = el.name;
      const val = el.value.trim();
      if (key === 'buttons_per_row') {
        const n = parseInt(val, 10);
        if (!isNaN(n) && n >= 2 && n <= 6) {
          newConfig['buttons_per_row'] = n;
        } else {
          delete newConfig['buttons_per_row'];
        }
      } else if (val) {
        newConfig[key] = val;
      } else {
        delete newConfig[key];
      }
    });

    // shown_types from checkboxes
    const checked = [...this.shadowRoot.querySelectorAll('input[name="shown_type_cb"]:checked')];
    const shownTypes = checked.map(cb => cb.value);
    if (shownTypes.length > 0) {
      newConfig['shown_types'] = shownTypes;
    } else {
      delete newConfig['shown_types'];
    }

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
      // Don't re-render if a form is open — would destroy it
      if (!this._activeForm && !this._eventTypesPanel) {
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
    const t = this._config.shown_types;
    let types = (Array.isArray(t) && t.length > 0) ? t : DEFAULT_SHOWN_TYPES;
    // Maximum of 12 buttons total
    if (types.length > 12) {
      console.warn('[pawsistant-card] shown_types has more than 12 entries; trimming to 12. Maximum is 12 buttons.');
      types = types.slice(0, 12);
    }
    return types;
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
        timelineHTML += `
          <div class="event-row" data-id="${_escapeHTML(ev.event_id)}">
            <span class="event-emoji">${meta.emoji}</span>
            <span class="event-time">${_escapeHTML(ev.time)}</span>
            <span class="event-type">${_escapeHTML(meta.label)}</span>
            ${noteHTML}
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
        else if (type === 'food' && peeCount !== null) {} // food has no inline stat
      } else if (metric === 'days_since' && medDays !== null) {
        countSuffix = ` (${Math.floor(medDays)}d)`;
      } else if (metric === 'last_value') {
        const w = stateNum(hass, ent.weight);
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
        : `Log ${meta.label} now. Hold to backdate.`;
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
          <div class="longpress-hint" aria-live="polite">Hold to backdate</div>

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

    // List view — all types are deletable (defaults are just seeded data)
    const rows = Object.entries(allTypes).map(([key, meta]) => {
      const displayMeta = getMeta(key, registry);
      const metric = buttonMetrics[key] || 'daily_count';
      const metricBadge = METRIC_LABELS[metric] ? metric.replace(/_/g, ' ') : metric;
      const icon = displayMeta.icon ? iconToEmoji(displayMeta.icon) : displayMeta.emoji;
      return `
        <li class="event-type-row" data-et-key="${esc(key)}">
          <span class="et-color-swatch" style="background:${esc(displayMeta.color)}" title="${esc(displayMeta.color)}"></span>
          <span class="et-icon" title="${esc(displayMeta.icon || '')}">${icon}</span>
          <span class="et-name">${esc(displayMeta.label)}</span>
          <span class="et-badge">${metricBadge}</span>
          <div class="et-actions">
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

    const serviceName = isAdd ? 'add_event_type' : 'update_event_type';

    this._hass.callService('pawsistant', serviceName, payload)
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

  /* ── Delete Event Type ─────────────────────────────────────────────── */
  _deleteEventType(key) {
    if (!confirm(`Delete event type '${key}'? Events logged with this type will be preserved.`)) return;
    this._hass.callService('pawsistant', 'delete_event_type', { event_type: key })
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
          this._timers.push(pressTimer);
        };

        const endPress = (e) => {
          if (pressTimer) {
            clearTimeout(pressTimer);
            this._timers = this._timers.filter(t => t !== pressTimer);
            pressTimer = null;
          }
          if (!didLongPress && e.type !== 'pointerleave' && e.type !== 'pointercancel') {
            const type = btn.dataset.type;
            this._instantLog(btn, type);
          }
          didLongPress = false;
        };

        btn.addEventListener('pointerdown', startPress);
        btn.addEventListener('pointerup', endPress);
        btn.addEventListener('pointerleave', endPress);
        btn.addEventListener('pointercancel', endPress);

        /* U3 — keyboard: Enter = backdate form, Space = instant log */
        btn.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            const type = btn.dataset.type;
            if (this._activeForm === 'backdate' && this._activeType === type) {
              this._closeForm();
            } else {
              this._openBackdateForm(btn, type);
            }
          } else if (e.key === ' ') {
            e.preventDefault();
            this._instantLog(btn, btn.dataset.type);
          }
        });

        return;
      }

      // Fallback: simple click
      btn.addEventListener('click', () => {
        this._instantLog(btn, btn.dataset.type);
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
  _instantLog(btn, type) {
    /* U7 — debounce: set pending, re-enable after service call */
    if (btn.dataset.pending) return;
    btn.dataset.pending = '1';
    this._logEvent(type)
      .then(() => {
        delete btn.dataset.pending;
        btn.classList.remove('flash');
        void btn.offsetWidth;
        btn.classList.add('flash');
        btn.addEventListener('animationend', () => btn.classList.remove('flash'), { once: true });
      })
      .catch(() => {
        delete btn.dataset.pending;
      });
  }

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
          <span class="slider-value" id="slider-display">1 min ago</span>
        </div>
        <input type="range" id="minutes-slider" min="1" max="480" step="1" value="1" aria-label="Minutes ago" />
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
      display.textContent = (v === 1 ? '1 min ago' : `${v} min ago`) + ` · ${timeStr}`;
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
    const currentWeight = stateNum(this._hass, ent.weight);
    const unit = this._weightUnit();

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
    const payload = {
      dog: this._config.dog,
      event_type: type,
      timestamp: timestamp,
    };
    if (note) payload.note = note;

    this._hass.callService('pawsistant', 'log_event', payload)
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
    this._hass.callService('pawsistant', 'log_event', {
      dog: this._config.dog,
      event_type: 'weight',
      value: value,
    })
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
    return this._hass.callService('pawsistant', 'log_event', {
      dog: this._config.dog,
      event_type: eventType,
      ...extra,
    });
  }

  _deleteEvent(eventId, btn) {
    /* U7 — debounce via pending attr */
    if (btn) btn.dataset.pending = '1';
    this._hass.callService('pawsistant', 'delete_event', {
      event_id: eventId,
    }).then(() => {
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
