/**
 * Pawsistant Card — Shared "time chooser" control.
 *
 * The hybrid picker used by every backdate / edit form: a quick minutes-ago
 * slider for the common recent case, plus a "pick a date" mode that swaps in a
 * native <input type="datetime-local"> so an event can be backdated an
 * arbitrary amount of time. Capped at "now" — future timestamps are not
 * allowed (the picker is bounded with `max` and the value is clamped on read).
 *
 * Self-contained: it owns its DOM subtree and queries within the container it
 * is mounted into, so several instances can coexist in one shadow root.
 */
import { T, TP } from './i18n';

/** Max value of the quick slider, in minutes (8 hours). */
export const SLIDER_MAX_MIN = 480;

export interface TimeChooser {
  /** Currently chosen timestamp as an ISO 8601 string, never in the future. */
  getTimestamp(): string;
}

export interface TimeChooserOptions {
  /** Prefix for element ids so multiple instances / labels stay unique. */
  idPrefix?: string;
  /** Existing event time (ISO) when editing; selects the starting mode/value. */
  initialTimestamp?: string;
}

/** Format a Date as a local `YYYY-MM-DDTHH:mm` value for datetime-local inputs. */
export function toLocalInputValue(d: Date): string {
  const pad = (n: number): string => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

/**
 * Render the hybrid time chooser into `container` and wire up its behavior.
 * Returns a handle exposing the chosen timestamp.
 */
export function mountTimeChooser(container: HTMLElement, opts: TimeChooserOptions = {}): TimeChooser {
  const pfx = opts.idPrefix || 'tc';
  const now = Date.now();

  // Derive starting minutes-ago and whether the initial time predates the slider.
  let minutesAgo = 0;
  if (opts.initialTimestamp) {
    const diff = now - new Date(opts.initialTimestamp).getTime();
    minutesAgo = Math.max(0, Math.round(diff / 60000));
  }
  // Anything older than the slider can reach starts in date mode (also fixes
  // editing events >8h old, which previously clamped to the slider's max).
  const startInDateMode = minutesAgo > SLIDER_MAX_MIN;
  const sliderStart = Math.min(minutesAgo, SLIDER_MAX_MIN);
  const initialDate = opts.initialTimestamp ? new Date(opts.initialTimestamp) : new Date(now);

  container.innerHTML = `
    <div class="form-field time-chooser">
      <div class="form-label-row">
        <label class="form-label" id="${pfx}-label" for="${pfx}-minutes-slider">${T('form.minutes_ago')}</label>
        <span class="slider-value" id="${pfx}-display">${T('time.now')}</span>
      </div>
      <input type="range" id="${pfx}-minutes-slider" min="0" max="${SLIDER_MAX_MIN}" step="1" value="${sliderStart}" aria-label="${T('form.minutes_ago')}" />
      <input type="datetime-local" id="${pfx}-datetime" max="${toLocalInputValue(new Date(now))}" value="${toLocalInputValue(initialDate)}" aria-label="${T('form.date_time')}" hidden />
      <button type="button" class="time-mode-toggle" id="${pfx}-toggle"></button>
    </div>
  `;

  const label = container.querySelector<HTMLElement>(`#${pfx}-label`)!;
  const display = container.querySelector<HTMLElement>(`#${pfx}-display`)!;
  const slider = container.querySelector<HTMLInputElement>(`#${pfx}-minutes-slider`)!;
  const dateInput = container.querySelector<HTMLInputElement>(`#${pfx}-datetime`)!;
  const toggle = container.querySelector<HTMLButtonElement>(`#${pfx}-toggle`)!;

  let dateMode = false;

  const updateSliderDisplay = (): void => {
    const v = parseInt(slider.value, 10);
    const t = new Date(Date.now() - v * 60000);
    const timeStr = t.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    display.textContent = (v === 0 ? T('time.now') : TP('time.min_ago', v)) + ` · ${timeStr}`;
  };

  const applyMode = (): void => {
    slider.hidden = dateMode;
    dateInput.hidden = !dateMode;
    display.hidden = dateMode;
    label.textContent = dateMode ? T('form.date_time') : T('form.minutes_ago');
    label.setAttribute('for', dateMode ? `${pfx}-datetime` : `${pfx}-minutes-slider`);
    toggle.textContent = dateMode ? T('form.use_slider') : T('form.pick_date');
    if (!dateMode) updateSliderDisplay();
  };

  slider.addEventListener('input', updateSliderDisplay);
  toggle.addEventListener('click', () => {
    // Entering date mode: seed the field from the slider's current position and
    // refresh `max` so the two controls stay continuous and bounded at now.
    if (!dateMode) {
      dateInput.value = toLocalInputValue(new Date(Date.now() - parseInt(slider.value, 10) * 60000));
      dateInput.max = toLocalInputValue(new Date());
    }
    dateMode = !dateMode;
    applyMode();
  });

  dateMode = startInDateMode;
  applyMode();

  return {
    getTimestamp(): string {
      if (dateMode) {
        const picked = new Date(dateInput.value);
        const ms = Number.isNaN(picked.getTime())
          ? Date.now()
          : Math.min(picked.getTime(), Date.now());
        return new Date(ms).toISOString();
      }
      return new Date(Date.now() - parseInt(slider.value, 10) * 60000).toISOString();
    },
  };
}
