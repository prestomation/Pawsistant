/**
 * Pawsistant Card — Inline form logic
 *
 * Standalone functions that operate on a PawsistantCard instance.
 * Using import type avoids a circular runtime dependency.
 */

import type { PawsistantCard } from './index';
import { T, TP } from './i18n';
import { getMeta } from './registry';
import { logEvent, updateEvent } from './services';
import { stateNum, _escapeHTML, toDisplayWeight } from './utils';

/* ── Backdate form ─────────────────────────────────────────────────── */
export function openBackdateForm(
  card: PawsistantCard,
  activeBtn: HTMLButtonElement | undefined,
  type: string | undefined,
): void {
  card._activeForm = 'backdate';
  card._activeType = type || null;
  card._activeTriggerBtn = activeBtn || null;

  const { registry } = card._registry();
  const meta = getMeta(type || '', registry);
  const formEl = card.shadowRoot!.getElementById('inline-form')!;
  /* U10 — proper <label for> on all inputs */
  formEl.innerHTML = `
      <div class="form-title">${meta.emoji} ${T('form.log_title', { label: _escapeHTML(meta.label) })}</div>
      <div class="form-field">
        <div class="form-label-row">
          <label class="form-label" for="minutes-slider">${T('form.minutes_ago')}</label>
          <span class="slider-value" id="slider-display">${T('time.now')}</span>
        </div>
        <input type="range" id="minutes-slider" min="0" max="480" step="1" value="0" aria-label="${T('form.minutes_ago')}" />
      </div>
      <div class="form-field">
        <label class="form-label" for="backdate-note">${T('form.note_optional')}</label>
        <input type="text" id="backdate-note" placeholder="${_escapeHTML(T('form.note_placeholder'))}" />
      </div>
      <div class="form-error" id="form-error" role="alert"></div>
      <div class="form-actions">
        <button class="btn-cancel" id="form-cancel">${T('form.cancel')}</button>
        <button class="btn-submit" id="form-submit">${T('form.log_event')}</button>
      </div>
    `;

  const slider = formEl.querySelector<HTMLInputElement>('#minutes-slider')!;
  const display = formEl.querySelector<HTMLElement>('#slider-display')!;
  const _updateSliderDisplay = () => {
    const v = parseInt(slider.value, 10);
    const t = new Date(Date.now() - v * 60000);
    const timeStr = t.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    display.textContent = (v === 0 ? T('time.now') : TP('time.min_ago', v)) + ` · ${timeStr}`;
  };
  slider.addEventListener('input', _updateSliderDisplay);
  _updateSliderDisplay();

  formEl.querySelector('#form-cancel')!.addEventListener('click', () => closeForm(card));
  formEl.querySelector('#form-submit')!.addEventListener('click', () => {
    const minutesAgo = parseInt(slider.value, 10);
    const note = formEl.querySelector<HTMLInputElement>('#backdate-note')!.value.trim();
    const timestamp = new Date(Date.now() - minutesAgo * 60000).toISOString();
    submitBackdate(card, activeBtn || null, type || '', timestamp, note || undefined);
  });

  applyFormOpenState(card, activeBtn || null);
}

/* ── Weight form ───────────────────────────────────────────────────── */
export function openWeightForm(card: PawsistantCard, activeBtn: HTMLButtonElement): void {
  card._activeForm = 'weight';
  card._activeType = 'weight';
  card._activeTriggerBtn = activeBtn;

  const ent = card._entities();
  const unit = card._weightUnit();
  const currentWeight = toDisplayWeight(stateNum(card._hass!, ent.weight), unit);

  const formEl = card.shadowRoot!.getElementById('inline-form')!;
  /* U10 — <label for>, U21 — inputmode="decimal", U22 — configurable unit */
  formEl.innerHTML = `
      <div class="form-title">⚖️ ${T('form.log_weight_title')}</div>
      <div class="form-field">
        <label class="form-label" for="weight-input">${T('form.weight_label', { unit: _escapeHTML(unit) })}</label>
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
        <button class="btn-cancel" id="form-cancel">${T('form.cancel')}</button>
        <button class="btn-submit" id="form-submit">${T('form.log_weight_title')}</button>
      </div>
    `;

  formEl.querySelector('#form-cancel')!.addEventListener('click', () => closeForm(card));
  formEl.querySelector('#form-submit')!.addEventListener('click', () => {
    const weightInput = formEl.querySelector<HTMLInputElement>('#weight-input')!;
    const value = parseFloat(weightInput.value);
    if (isNaN(value) || value < 1 || value > 999) {
      weightInput.style.outline = '2px solid var(--error-color, #ef5350)';
      weightInput.focus();
      return;
    }
    /* If unit is kg, convert to lbs before storing (store is always lbs) */
    const valueLbs = unit === 'kg' ? Math.round(value * 2.20462 * 10) / 10 : value;
    submitWeight(card, activeBtn, valueLbs);
  });

  applyFormOpenState(card, activeBtn);
}

/* ── Edit form for existing event ───────────────────────────────────── */
export function openEditForm(
  card: PawsistantCard,
  eventType: string | undefined,
  timestamp: string | undefined,
  note: string | undefined,
  value: string | undefined,
  eventId: string | undefined,
): void {
  card._activeForm = 'edit';
  card._activeType = eventType || null;
  card._editEventId = eventId || null;

  const { registry } = card._registry();
  const meta = getMeta(eventType || '', registry);
  const isWeight = eventType === 'weight';
  const unit = card._weightUnit();

  // Calculate minutes ago from timestamp
  let minutesAgo = 0;
  if (timestamp) {
    const diff = Date.now() - new Date(timestamp).getTime();
    minutesAgo = Math.max(0, Math.round(diff / 60000));
  }

  const formEl = card.shadowRoot!.getElementById('inline-form')!;

  if (isWeight) {
    const displayVal = value ? (unit === 'kg' ? Math.round(Number(value) / 2.20462 * 10) / 10 : value) : '';
    formEl.innerHTML = `
        <div class="form-title">⚖️ ${T('form.edit_weight_title')}</div>
        <div class="form-field">
          <label class="form-label" for="weight-input">${T('form.weight_label', { unit: _escapeHTML(unit) })}</label>
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
          <button class="btn-cancel" id="form-cancel">${T('form.cancel')}</button>
          <button class="btn-submit" id="form-submit">${T('form.update_weight')}</button>
        </div>
      `;
    formEl.querySelector('#form-cancel')!.addEventListener('click', () => closeForm(card));
    formEl.querySelector('#form-submit')!.addEventListener('click', () => {
      const wInput = formEl.querySelector<HTMLInputElement>('#weight-input')!;
      const w = parseFloat(wInput.value);
      if (isNaN(w) || w < 1 || w > 999) {
        wInput.style.outline = '2px solid var(--error-color, #ef5350)';
        wInput.focus();
        return;
      }
      const valueLbs = unit === 'kg' ? Math.round(w * 2.20462 * 10) / 10 : w;
      submitEdit(card, { value: valueLbs });
    });
  } else {
    formEl.innerHTML = `
        <div class="form-title">${meta.emoji} ${T('form.edit_title', { label: _escapeHTML(meta.label) })}</div>
        <div class="form-field">
          <div class="form-label-row">
            <label class="form-label" for="minutes-slider">${T('form.minutes_ago')}</label>
            <span class="slider-value" id="slider-display">${T('time.now')}</span>
          </div>
          <input type="range" id="minutes-slider" min="0" max="480" step="1" value="${minutesAgo}" aria-label="${T('form.minutes_ago')}" />
        </div>
        <div class="form-field">
          <label class="form-label" for="backdate-note">${T('form.note_optional')}</label>
          <input type="text" id="backdate-note" placeholder="${_escapeHTML(T('form.note_placeholder'))}" value="${_escapeHTML(note || '')}" />
        </div>
        <div class="form-error" id="form-error" role="alert"></div>
        <div class="form-actions">
          <button class="btn-cancel" id="form-cancel">${T('form.cancel')}</button>
          <button class="btn-submit" id="form-submit">${T('form.update_event')}</button>
        </div>
      `;

    const slider = formEl.querySelector<HTMLInputElement>('#minutes-slider')!;
    const display = formEl.querySelector<HTMLElement>('#slider-display')!;
    const _updateSliderDisplay = () => {
      const v = parseInt(slider.value, 10);
      const t = new Date(Date.now() - v * 60000);
      const timeStr = t.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
      display.textContent = (v === 0 ? T('time.now') : TP('time.min_ago', v)) + ` · ${timeStr}`;
    };
    slider.addEventListener('input', _updateSliderDisplay);
    _updateSliderDisplay();

    formEl.querySelector('#form-cancel')!.addEventListener('click', () => closeForm(card));
    formEl.querySelector('#form-submit')!.addEventListener('click', () => {
      const minutesAgoVal = parseInt(slider.value, 10);
      const noteVal = formEl.querySelector<HTMLInputElement>('#backdate-note')!.value.trim();
      const ts = new Date(Date.now() - minutesAgoVal * 60000).toISOString();
      const updates: Record<string, unknown> = { timestamp: ts };
      if (noteVal) updates['note'] = noteVal;
      else updates['note'] = '';  // clear note if empty
      submitEdit(card, updates);
    });
  }

  applyFormOpenState(card, null);
}

/* ── Submit backdate ───────────────────────────────────────────────── */
export function submitBackdate(
  card: PawsistantCard,
  btn: HTMLButtonElement | null,
  type: string,
  timestamp: string,
  note: string | undefined,
): void {
  const extra: Record<string, unknown> = { timestamp };
  if (note) extra['note'] = note;

  logEvent(card._hass!, card._config.dog, type, extra)
    .then(() => {
      if (btn) card._showSuccessFlash(btn);
      card._setTimeout(() => {
        closeForm(card);
        card._fetchTimeline();
      }, 600);
    })
    .catch(err => {
      /* U11 — show error in form instead of just console.error */
      console.error('[pawsistant-card] log_event (backdate) failed:', err);
      showFormError(card, T('form.error.log_event'));
    });
}

/* ── Submit weight ─────────────────────────────────────────────────── */
export function submitWeight(card: PawsistantCard, btn: HTMLButtonElement, value: number): void {
  logEvent(card._hass!, card._config.dog, 'weight', { value })
    .then(() => {
      card._showSuccessFlash(btn);
      card._setTimeout(() => {
        closeForm(card);
        card._fetchTimeline();
      }, 600);
    })
    .catch(err => {
      /* U11 — show error in form */
      console.error('[pawsistant-card] log_event (weight) failed:', err);
      showFormError(card, T('form.error.log_weight'));
    });
}

/* ── Submit edit ───────────────────────────────────────────────────── */
export function submitEdit(card: PawsistantCard, updates: Record<string, unknown>): void {
  const eventId = card._editEventId;
  if (!eventId) return;

  updateEvent(card._hass!, eventId, updates)
    .then(() => {
      card._setTimeout(() => {
        closeForm(card);
        card._fetchTimeline();
      }, 600);
    })
    .catch(err => {
      console.error('[pawsistant-card] update_event failed:', err);
      showFormError(card, T('form.error.update_event'));
    });
}

/* ── Apply visual state when form opens ───────────────────────────── */
export function applyFormOpenState(card: PawsistantCard, activeBtn: HTMLButtonElement | null): void {
  const root = card.shadowRoot!;
  root.querySelectorAll<HTMLButtonElement>('.log-btn').forEach(b => {
    if (b === activeBtn) {
      b.classList.add('active-btn');
      b.classList.remove('dimmed');
    } else {
      b.classList.add('dimmed');
      b.classList.remove('active-btn');
    }
  });

  const wrap = root.getElementById('inline-form-wrap') as HTMLElement;
  void wrap.offsetWidth;
  wrap.classList.add('open');

  // Focus first input after animation
  card._setTimeout(() => {
    const first = root.querySelector<HTMLElement>('#inline-form input');
    if (first) first.focus();
  }, 300);
}

/* ── Close form ────────────────────────────────────────────────────── */
export function closeForm(card: PawsistantCard): void {
  const triggerBtn = card._activeTriggerBtn;
  card._activeForm = null;
  card._activeType = null;
  card._activeTriggerBtn = null;
  card._editEventId = null;

  const root = card.shadowRoot!;
  const wrap = root.getElementById('inline-form-wrap');
  if (wrap) wrap.classList.remove('open');

  root.querySelectorAll('.log-btn').forEach(b => {
    b.classList.remove('dimmed', 'active-btn');
  });

  /* U17 — return focus to trigger button */
  if (triggerBtn) {
    card._setTimeout(() => triggerBtn.focus(), 50);
  }
}

/* ── Show form error ───────────────────────────────────────────────── */
export function showFormError(card: PawsistantCard, msg: string): void {
  const el = card.shadowRoot!.querySelector<HTMLElement>('#form-error');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('visible');
}
