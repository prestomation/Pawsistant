/**
 * Pawsistant Button Card — Multi-button card element
 *
 * A compact card that shows one or more quick-log buttons for specific event types.
 * Tap opens backdate/weight form, long-press logs instantly.
 */

import './button-card-editor';
import type { HomeAssistant, PawsistantButtonCardConfig, ButtonConfig, EventMeta } from './types';
import { buildRegistry, getMeta } from './registry';
import { setLang, T } from './i18n';
import { logEvent } from './services';
import { findEntitiesByDog, stateNum, stateAttr, toDisplayWeight, _escapeHTML, getDogId } from './utils';
import { renderPawsistantButton } from './button';
import { openBackdateForm, openWeightForm } from './standalone-forms';
import { displayLabel, ensureTimelineStyles } from './timeline-render';
import { createEventLog } from './standalone-timeline';
import type { EventLogHandle } from './standalone-timeline';

/* ── Card picker registration ──────────────────────────────────────── */

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'pawsistant-button-card',
  name: 'Pawsistant Button',
  description: 'Quick-log buttons for one or more event types',
  preview: true,
});

/* ── Main card element ─────────────────────────────────────────────── */

export class PawsistantButtonCard extends HTMLElement {
  _config: PawsistantButtonCardConfig = { type: 'custom:pawsistant-button-card', dog: '', buttons: [] };
  _hass: HomeAssistant | null = null;
  _lastHash: string | null = null;
  _timers: (ReturnType<typeof setTimeout> | number)[] = [];
  _activeForm: boolean = false;
  _btnCleanups: (() => void)[] = [];
  _formCleanup: (() => void) | null = null;
  _eventLogHandle: EventLogHandle | null = null;

  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  static getConfigElement(): HTMLElement {
    return document.createElement('pawsistant-button-card-editor');
  }

  static getStubConfig(hass: HomeAssistant): PawsistantButtonCardConfig {
    let dog = 'MyDog';
    for (const state of Object.values(hass.states || {})) {
      if (state.attributes?.dog) {
        dog = state.attributes.dog as string;
        break;
      }
    }
    return { type: 'custom:pawsistant-button-card', dog, buttons: [{ event_type: 'poop' }] };
  }

  setConfig(config: PawsistantButtonCardConfig): void {
    if (!config.dog) throw new Error('Pawsistant button card requires a "dog" config field');

    // Backward compatibility: migrate single event_type → buttons[]
    const migrated = { ...config };
    if (!migrated.buttons && migrated.event_type) {
      migrated.buttons = [{ event_type: migrated.event_type }];
      delete migrated.event_type;
    }

    if (!migrated.buttons || migrated.buttons.length === 0) {
      throw new Error('Pawsistant button card requires at least one button');
    }

    this._config = migrated;
    this._lastHash = null;
  }

  set hass(hass: HomeAssistant) {
    this._hass = hass;
    setLang(hass.language);
    const hash = this._computeHash();
    if (hash !== this._lastHash) {
      this._lastHash = hash;
      if (!this._activeForm) {
        this._render();
      }
    }
  }

  _computeHash(): string {
    const hass = this._hass;
    if (!hass) return '';
    const cfg = this._config;
    const ent = findEntitiesByDog(hass, cfg.dog);
    const parts: string[] = [
      cfg.dog,
      JSON.stringify(cfg.buttons.map(b => b.event_type)),
      JSON.stringify(stateAttr(hass, ent.timeline, 'event_types') || {}),
      JSON.stringify(stateAttr(hass, ent.timeline, 'button_metrics') || {}),
    ];
    // Include relevant entity states for metric computation per button
    for (const btn of cfg.buttons) {
      const metric = this._getMetric(btn.event_type);
      if (metric === 'daily_count') {
        if (btn.event_type === 'pee') parts.push(String(stateNum(hass, ent.pee_count) ?? ''));
        else if (btn.event_type === 'poop') parts.push(String(stateNum(hass, ent.poop_count) ?? ''));
      } else if (metric === 'days_since') {
        parts.push(String(stateNum(hass, ent.medicine_days) ?? ''));
      } else if (metric === 'last_value') {
        parts.push(String(stateNum(hass, ent.weight) ?? ''));
      } else if (metric === 'hours_since') {
        parts.push(String(stateAttr(hass, ent.timeline, 'last_' + btn.event_type + '_ts') ?? ''));
      }
    }
    return parts.join('|');
  }

  _getMetric(eventType: string): string {
    const hass = this._hass;
    if (!hass) return 'daily_count';
    const { metrics } = buildRegistry(hass);
    return metrics[eventType] || 'daily_count';
  }

  _metricText(eventType: string): string {
    const hass = this._hass;
    if (!hass) return '';
    const cfg = this._config;
    const ent = findEntitiesByDog(hass, cfg.dog);
    const weightUnit = cfg.weight_unit === 'kg' ? 'kg' : 'lbs';
    const metric = this._getMetric(eventType);

    if (metric === 'daily_count') {
      if (eventType === 'pee') {
        const n = stateNum(hass, ent.pee_count);
        if (n !== null) return `(${T('metric.daily_count', { n })})`;
      } else if (eventType === 'poop') {
        const n = stateNum(hass, ent.poop_count);
        if (n !== null) return `(${T('metric.daily_count', { n })})`;
      }
    } else if (metric === 'days_since') {
      const { registry } = buildRegistry(hass);
      const meta = getMeta(eventType, registry);
      const daysLabel = `days since ${meta.label.toLowerCase()}`;
      for (const [, st] of Object.entries(hass.states)) {
        if (st.attributes?.dog?.toLowerCase() === cfg.dog?.toLowerCase() &&
            st.attributes?.friendly_name?.toLowerCase().endsWith(daysLabel)) {
          const daysVal = parseFloat(st.state);
          if (!isNaN(daysVal)) return `(${Math.floor(daysVal)}d)`;
        }
      }
    } else if (metric === 'last_value') {
      const w = toDisplayWeight(stateNum(hass, ent.weight), weightUnit);
      if (w !== null) return `(${T('metric.last_value', { v: w, unit: ' ' + weightUnit })})`;
    } else if (metric === 'hours_since') {
      const lastTs = stateAttr(hass, ent.timeline, 'last_' + eventType + '_ts') as string | null;
      if (lastTs) {
        const hrs = Math.floor((Date.now() - new Date(lastTs).getTime()) / 3600000);
        if (hrs >= 0) return `(${T('metric.hours_since', { n: hrs })})`;
      }
    }
    return '';
  }

  /** Localized label for DISPLAY only (built-in types translated; custom keep
   *  their user name). Never use for the days_since friendly_name match. */
  _displayLabel(type: string, meta: EventMeta): string {
    return displayLabel(type, meta);
  }

  _render(): void {
    const hass = this._hass;
    if (!hass) return;

    const root = this.shadowRoot!;
    const cfg = this._config;
    const buttonsPerRow = Math.max(2, Math.min(6, cfg.buttons_per_row || 3));

    // Validate dog
    const dogNameLower = cfg.dog.toLowerCase();
    let dogFound = false;
    for (const state of Object.values(hass.states)) {
      if (state.attributes?.dog?.toLowerCase() === dogNameLower) {
        dogFound = true;
        break;
      }
    }
    if (!dogFound) {
      this._renderError(`Unknown dog: "${_escapeHTML(cfg.dog)}"`);
      return;
    }

    if (!cfg.buttons || cfg.buttons.length === 0) {
      this._renderError('No buttons configured');
      return;
    }

    // Clean up previous buttons
    this._cleanupButtons();

    const showTitle = cfg.show_title !== false;
    const { registry } = buildRegistry(hass);

    // Build content
    root.innerHTML = `
      <style>
        :host { display: block; }
        .pbc-card {
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border-radius: var(--ha-card-border-radius, 12px);
          border: 1px solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
          box-shadow: var(--ha-card-box-shadow, none);
          overflow: hidden;
          padding: 12px;
          display: flex;
          flex-direction: column;
          align-items: stretch;
          gap: 8px;
        }
        .pbc-title {
          font-size: 14px;
          font-weight: 600;
          color: var(--primary-text-color);
          text-align: center;
        }
        .pbc-header {
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 30px;
        }
        .pbc-header .pbc-title { flex: 1; }
        .pbc-log-btn {
          position: absolute;
          right: 0;
          top: 50%;
          transform: translateY(-50%);
          background: none;
          border: none;
          cursor: pointer;
          font-size: 15px;
          padding: 6px;
          border-radius: 6px;
          min-width: 36px;
          min-height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--secondary-text-color);
          transition: background 0.15s;
        }
        .pbc-log-btn:hover { background: var(--secondary-background-color, #f5f5f5); }
        /* Event log popup. position: fixed inside shadow DOM resolves against
           the viewport unless an ancestor is transformed — fine for HA
           dashboards at rest (only transient drag states transform cards). */
        .pbc-overlay {
          position: fixed;
          inset: 0;
          z-index: 999;
          background: rgba(0, 0, 0, 0.45);
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 16px;
          box-sizing: border-box;
        }
        .pbc-dialog {
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
          width: min(480px, 100%);
          max-height: min(80vh, 640px);
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }
        .pbc-dialog-header {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 10px 8px 16px;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
          flex-shrink: 0;
        }
        .pbc-dialog-title {
          flex: 1;
          font-size: 14px;
          font-weight: 600;
          color: var(--primary-text-color);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .pbc-dialog-close {
          background: none;
          border: none;
          cursor: pointer;
          font-size: 16px;
          color: var(--secondary-text-color);
          padding: 8px;
          border-radius: 6px;
          min-width: 36px;
          min-height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background 0.15s;
        }
        .pbc-dialog-close:hover { background: var(--secondary-background-color, #f5f5f5); }
        .pbc-dialog .timeline-body { flex: 1; }
        .pbc-dialog .inline-form { margin: 8px 12px 0; }
        .pbc-grid {
          display: grid;
          grid-template-columns: repeat(${buttonsPerRow}, 1fr);
          gap: 8px;
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
          min-width: 0;
          width: 100%;
          position: relative;
        }
        .log-btn:hover { background: var(--divider-color, #e0e0e0); }
        .log-btn:active { transform: scale(0.94); }
        .log-btn .btn-emoji { font-size: 26px; line-height: 1; }
        .log-btn .btn-label { font-size: 12px; font-weight: 500; }
        .log-btn.success-flash {
          animation: success-anim 0.6s ease forwards;
        }
        @keyframes success-anim {
          0%   { background: var(--success-color, #4caf50); transform: scale(1); }
          40%  { transform: scale(0.93); }
          100% { background: var(--success-color, #4caf50); transform: scale(1); }
        }
      </style>
      <ha-card class="pbc-card">
        ${this._headerHTML(showTitle)}
        <div class="pbc-grid" id="pbc-grid"></div>
        <div id="pbc-form-slot"></div>
      </ha-card>
    `;

    const logBtn = root.getElementById('pbc-log-btn');
    if (logBtn) {
      logBtn.addEventListener('click', () => this._openEventLog());
    }

    const grid = root.getElementById('pbc-grid')!;

    for (const btnCfg of cfg.buttons) {
      const meta = getMeta(btnCfg.event_type, registry);
      const metricText = this._metricText(btnCfg.event_type);
      const isWeight = btnCfg.event_type === 'weight';

      const { element: btn, cleanup: btnCleanup } = renderPawsistantButton({
        container: grid,
        meta: { ...meta, label: this._displayLabel(btnCfg.event_type, meta) },
        metricText,
        onTap: () => {
          if (isWeight) {
            this._openWeight(btn, meta, btnCfg.event_type);
          } else {
            this._openBackdate(btn, meta, btnCfg.event_type);
          }
        },
        onLongPress: () => {
          if (isWeight) {
            this._openWeight(btn, meta, btnCfg.event_type);
          } else {
            this._instantLog(btn, btnCfg.event_type);
          }
        },
        timers: this._timers,
      });
      grid.appendChild(btn);
      this._btnCleanups.push(btnCleanup);
    }
  }

  _headerHTML(showTitle: boolean): string {
    const cfg = this._config;
    const titleHTML = showTitle ? `<div class="pbc-title">${_escapeHTML(cfg.dog)}</div>` : '';
    if (cfg.show_event_log !== true) return titleHTML;
    const label = T('button_card.open_event_log');
    return `
      <div class="pbc-header">
        ${titleHTML}
        <button class="pbc-log-btn" id="pbc-log-btn" aria-label="${label}" title="${label}" aria-haspopup="dialog">📋</button>
      </div>
    `;
  }

  /* ── Event log popup ───────────────────────────────────────────────── */

  _openEventLog(): void {
    if (this._activeForm || !this._hass) return;
    // Blocks hass-driven re-renders that would rebuild innerHTML and
    // destroy the open popup (see the hash check in `set hass`).
    this._activeForm = true;

    const root = this.shadowRoot!;
    const dog = this._config.dog;
    ensureTimelineStyles(root);

    const overlay = document.createElement('div');
    overlay.className = 'pbc-overlay';
    overlay.innerHTML = `
      <div class="pbc-dialog" role="dialog" aria-modal="true" aria-label="${_escapeHTML(dog)} — ${T('timeline.title')}">
        <div class="pbc-dialog-header">
          <span class="pbc-dialog-title">📋 ${_escapeHTML(dog)} — ${T('timeline.title')}</span>
          <button class="pbc-dialog-close" id="pbc-dialog-close" aria-label="${T('popup.close')}" title="${T('popup.close')}">✕</button>
        </div>
        <div id="pbc-log-form-slot"></div>
        <div class="timeline-body" id="pbc-log-body"></div>
      </div>
    `;
    root.appendChild(overlay);

    const body = overlay.querySelector<HTMLElement>('#pbc-log-body')!;
    const formSlot = overlay.querySelector<HTMLElement>('#pbc-log-form-slot')!;

    const dogId = getDogId(this._hass, dog);
    if (dogId) {
      const { registry } = buildRegistry(this._hass);
      this._eventLogHandle = createEventLog({
        container: body,
        formSlot,
        hass: this._hass,
        dogId,
        registry,
        weightUnit: this._config.weight_unit === 'kg' ? 'kg' : 'lbs',
      });
    } else {
      body.innerHTML = `<div class="empty">${T('timeline.empty_no_events')}</div>`;
    }

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) this._closeEventLog();
    });
    overlay.querySelector('#pbc-dialog-close')!.addEventListener('click', () => this._closeEventLog());
    overlay.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        this._closeEventLog();
        return;
      }
      if (e.key === 'Tab') {
        // Lightweight focus trap: cycle between first/last focusable
        const focusables = overlay.querySelectorAll<HTMLElement>('button, input, [tabindex]:not([tabindex="-1"])');
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = root.activeElement as HTMLElement | null;
        if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    });

    overlay.querySelector<HTMLElement>('#pbc-dialog-close')!.focus();
  }

  _closeEventLog(): void {
    if (this._eventLogHandle) {
      this._eventLogHandle.cleanup();
      this._eventLogHandle = null;
    }
    const overlay = this.shadowRoot!.querySelector('.pbc-overlay');
    if (overlay) overlay.remove();
    this._activeForm = false;
    // Re-render so button metrics reflect edits/deletes made in the popup
    if (this._hass) {
      this._lastHash = this._computeHash();
      this._render();
    }
    const logBtn = this.shadowRoot!.getElementById('pbc-log-btn');
    if (logBtn) (logBtn as HTMLElement).focus();
  }

  _renderError(message: string): void {
    this.shadowRoot!.innerHTML = `
      <style>
        :host { display: block; }
        .pbc-error {
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border-radius: var(--ha-card-border-radius, 12px);
          border: 1px solid var(--error-color, #EF5350);
          padding: 16px;
          text-align: center;
          color: var(--error-color, #EF5350);
          font-size: 13px;
        }
      </style>
      <ha-card class="pbc-error">${message}</ha-card>
    `;
  }

  async _openBackdate(btn: HTMLButtonElement, meta: EventMeta, eventType: string): Promise<void> {
    if (this._activeForm) return;
    this._activeForm = true;
    const formSlot = this.shadowRoot!.getElementById('pbc-form-slot')!;

    const result = await openBackdateForm({
      container: formSlot,
      meta,
      hass: this._hass!,
      dog: this._config.dog,
      eventType,
    });

    if (result) {
      this._showSuccessFlash(btn);
      setTimeout(() => {
        result.cleanup();
        this._activeForm = false;
        this._lastHash = null;
      }, 600);
    } else {
      this._activeForm = false;
    }
  }

  async _openWeight(btn: HTMLButtonElement, meta: EventMeta, eventType: string): Promise<void> {
    if (this._activeForm) return;
    this._activeForm = true;
    const formSlot = this.shadowRoot!.getElementById('pbc-form-slot')!;
    const ent = findEntitiesByDog(this._hass!, this._config.dog);
    const weightUnit = this._config.weight_unit === 'kg' ? 'kg' : 'lbs';
    const currentWeight = toDisplayWeight(stateNum(this._hass!, ent.weight), weightUnit);

    const result = await openWeightForm({
      container: formSlot,
      meta,
      hass: this._hass!,
      dog: this._config.dog,
      currentWeight,
      displayUnit: weightUnit,
    });

    if (result) {
      this._showSuccessFlash(btn);
      setTimeout(() => {
        result.cleanup();
        this._activeForm = false;
        this._lastHash = null;
      }, 600);
    } else {
      this._activeForm = false;
    }
  }

  _instantLog(btn: HTMLButtonElement, eventType: string): void {
    logEvent(this._hass!, this._config.dog, eventType)
      .then(() => {
        this._showSuccessFlash(btn);
      })
      .catch((err) => {
        console.error('[pawsistant-button-card] instant log failed:', err);
      });
  }

  _showSuccessFlash(btn: HTMLButtonElement): void {
    const emojiSpan = btn.querySelector('.btn-emoji');
    const originalEmoji = emojiSpan?.textContent || '';
    if (emojiSpan) emojiSpan.textContent = '\u2713';
    btn.classList.add('success-flash');
    const timerId = setTimeout(() => {
      if (emojiSpan) emojiSpan.textContent = originalEmoji;
      btn.classList.remove('success-flash');
      this._timers = this._timers.filter(t => t !== timerId);
    }, 600);
    this._timers.push(timerId);
  }

  _cleanupButtons(): void {
    for (const cleanup of this._btnCleanups) {
      cleanup();
    }
    this._btnCleanups = [];
  }

  disconnectedCallback(): void {
    for (const id of this._timers) {
      clearTimeout(id);
    }
    this._timers = [];
    this._cleanupButtons();
    if (this._formCleanup) {
      this._formCleanup();
      this._formCleanup = null;
    }
    if (this._eventLogHandle) {
      this._eventLogHandle.cleanup();
      this._eventLogHandle = null;
      this.shadowRoot!.querySelector('.pbc-overlay')?.remove();
      this._activeForm = false;
    }
  }

  getCardSize(): number {
    const rows = Math.ceil(this._config.buttons.length / (this._config.buttons_per_row || 3));
    return Math.max(2, rows);
  }
}

customElements.define('pawsistant-button-card', PawsistantButtonCard);
