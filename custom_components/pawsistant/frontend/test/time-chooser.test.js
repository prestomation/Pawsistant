/**
 * Pawsistant Card — Shared time-chooser tests.
 */
import { describe, it, expect } from 'vitest';
import { mountTimeChooser, toLocalInputValue, SLIDER_MAX_MIN } from '../src/time-chooser.js';

function mount(opts) {
  const container = document.createElement('div');
  const chooser = mountTimeChooser(container, opts);
  return { container, chooser };
}

describe('toLocalInputValue', () => {
  it('formats a date as local YYYY-MM-DDTHH:mm', () => {
    const d = new Date(2026, 5, 9, 7, 4); // local time, June 9 2026 07:04
    expect(toLocalInputValue(d)).toBe('2026-06-09T07:04');
  });
});

describe('mountTimeChooser — slider mode (default)', () => {
  it('renders a slider, datetime input, and toggle', () => {
    const { container } = mount();
    expect(container.querySelector('#tc-minutes-slider')).not.toBeNull();
    expect(container.querySelector('#tc-datetime')).not.toBeNull();
    expect(container.querySelector('#tc-toggle')).not.toBeNull();
  });

  it('starts in slider mode (slider visible, datetime hidden)', () => {
    const { container } = mount();
    expect(container.querySelector('#tc-minutes-slider').hidden).toBe(false);
    expect(container.querySelector('#tc-datetime').hidden).toBe(true);
  });

  it('caps the slider at SLIDER_MAX_MIN', () => {
    const { container } = mount();
    expect(container.querySelector('#tc-minutes-slider').max).toBe(String(SLIDER_MAX_MIN));
  });

  it('returns "now" (≈0 minutes ago) when slider is 0', () => {
    const { chooser } = mount();
    const ts = new Date(chooser.getTimestamp()).getTime();
    expect(Math.abs(Date.now() - ts)).toBeLessThan(2000);
  });

  it('subtracts the slider minutes from now', () => {
    const { container, chooser } = mount();
    const slider = container.querySelector('#tc-minutes-slider');
    slider.value = '120';
    const ts = new Date(chooser.getTimestamp()).getTime();
    const expected = Date.now() - 120 * 60000;
    expect(Math.abs(expected - ts)).toBeLessThan(2000);
  });

  it('uses a unique id prefix', () => {
    const { container } = mount({ idPrefix: 'pbc-bd' });
    expect(container.querySelector('#pbc-bd-minutes-slider')).not.toBeNull();
  });
});

describe('mountTimeChooser — date mode', () => {
  it('switches to date mode when the toggle is clicked', () => {
    const { container } = mount();
    container.querySelector('#tc-toggle').click();
    expect(container.querySelector('#tc-minutes-slider').hidden).toBe(true);
    expect(container.querySelector('#tc-datetime').hidden).toBe(false);
  });

  it('returns the picked datetime (interpreted as local) as ISO', () => {
    const { container, chooser } = mount();
    container.querySelector('#tc-toggle').click();
    const input = container.querySelector('#tc-datetime');
    input.value = '2025-01-02T03:04';
    const expected = new Date('2025-01-02T03:04').getTime();
    expect(new Date(chooser.getTimestamp()).getTime()).toBe(expected);
  });

  it('clamps a future pick back to now', () => {
    const { container, chooser } = mount();
    container.querySelector('#tc-toggle').click();
    const input = container.querySelector('#tc-datetime');
    input.value = toLocalInputValue(new Date(Date.now() + 7 * 24 * 60 * 60000)); // a week ahead
    const ts = new Date(chooser.getTimestamp()).getTime();
    expect(ts).toBeLessThanOrEqual(Date.now() + 1000);
  });

  it('sets the datetime max to now so future dates cannot be picked', () => {
    const { container } = mount();
    const input = container.querySelector('#tc-datetime');
    expect(input.max).toBeTruthy();
    expect(new Date(input.max).getTime()).toBeLessThanOrEqual(Date.now() + 60000);
  });
});

describe('mountTimeChooser — editing an existing event', () => {
  it('starts in slider mode for a recent event (< 8h old)', () => {
    const initial = new Date(Date.now() - 30 * 60000).toISOString();
    const { container } = mount({ initialTimestamp: initial });
    expect(container.querySelector('#tc-minutes-slider').hidden).toBe(false);
    expect(container.querySelector('#tc-minutes-slider').value).toBe('30');
  });

  it('starts in DATE mode for an event older than the slider (fixes the >8h clamp bug)', () => {
    const initial = new Date(Date.now() - 5 * 24 * 60 * 60000).toISOString(); // 5 days ago
    const { container, chooser } = mount({ initialTimestamp: initial });
    expect(container.querySelector('#tc-datetime').hidden).toBe(false);
    expect(container.querySelector('#tc-minutes-slider').hidden).toBe(true);
    // The chosen time should round-trip near the original (minute precision).
    const got = new Date(chooser.getTimestamp()).getTime();
    expect(Math.abs(got - new Date(initial).getTime())).toBeLessThan(60000);
  });
});
