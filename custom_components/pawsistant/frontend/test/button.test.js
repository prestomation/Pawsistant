/**
 * Pawsistant Card — button module tests
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderPawsistantButton } from '../src/button.js';

describe('renderPawsistantButton', () => {
  let host;
  beforeEach(() => { host = document.createElement('div'); document.body.appendChild(host); });
  afterEach(() => { host.remove(); });

  const meta = { emoji: 'P', label: 'Poop', color: '#FF8A65', icon: '' };

  it('renders emoji, label, and metric text', () => {
    const { element } = renderPawsistantButton({
      container: host, meta, metricText: '3 today', disabled: false,
      onTap: () => {}, onLongPress: () => {}, timers: [], haptics: false,
    });
    expect(element.querySelector('.btn-emoji').textContent).toBe('P');
    expect(element.querySelector('.btn-label').textContent).toContain('Poop');
    expect(element.querySelector('.btn-label').textContent).toContain('3 today');
  });

  it('escapes unsafe label content', () => {
    const bad = { emoji: 'W', label: '<img src=x>', color: '#888', icon: '' };
    const { element } = renderPawsistantButton({
      container: host, meta: bad, metricText: '', disabled: false,
      onTap: () => {}, onLongPress: () => {}, timers: [], haptics: false,
    });
    expect(element.querySelector('.btn-label').querySelector('img')).toBeNull();
    expect(element.querySelector('.btn-label').textContent).toContain('<img src=x>');
  });

  it('invokes onTap on short click', () => {
    const taps = [];
    const { element, cleanup } = renderPawsistantButton({
      container: host, meta, metricText: '', disabled: false,
      onTap: () => taps.push(1), onLongPress: () => {}, timers: [], haptics: false,
    });
    element.dispatchEvent(new MouseEvent('pointerdown'));
    element.dispatchEvent(new MouseEvent('pointerup'));
    element.dispatchEvent(new MouseEvent('click'));
    expect(taps.length).toBe(1);
    cleanup();
  });

  it('invokes onLongPress after 500ms hold', () => {
    const holds = [];
    const { element, cleanup } = renderPawsistantButton({
      container: host, meta, metricText: '', disabled: false,
      onTap: () => {}, onLongPress: () => holds.push(1), timers: [], haptics: false,
    });
    vi.useFakeTimers();
    element.dispatchEvent(new MouseEvent('pointerdown'));
    vi.advanceTimersByTime(500);
    vi.useRealTimers();
    expect(holds.length).toBe(1);
    cleanup();
  });

  it('suppresses onTap and onLongPress when disabled', () => {
    const taps = [];
    const holds = [];
    const { element, cleanup } = renderPawsistantButton({
      container: host, meta, metricText: '', disabled: true,
      onTap: () => taps.push(1), onLongPress: () => holds.push(1), timers: [], haptics: false,
    });
    element.dispatchEvent(new MouseEvent('pointerdown'));
    element.dispatchEvent(new MouseEvent('pointerup'));
    element.dispatchEvent(new MouseEvent('click'));
    expect(taps.length).toBe(0);
    vi.useFakeTimers();
    element.dispatchEvent(new MouseEvent('pointerdown'));
    vi.advanceTimersByTime(500);
    vi.useRealTimers();
    expect(holds.length).toBe(0);
    cleanup();
  });

  it('cleanup() removes listeners', () => {
    const taps = [];
    const { element, cleanup } = renderPawsistantButton({
      container: host, meta, metricText: '', disabled: false,
      onTap: () => taps.push(1), onLongPress: () => {}, timers: [], haptics: false,
    });
    cleanup();
    element.dispatchEvent(new MouseEvent('pointerdown'));
    element.dispatchEvent(new MouseEvent('pointerup'));
    element.dispatchEvent(new MouseEvent('click'));
    expect(taps.length).toBe(0);
  });

  it('triggers navigator.vibrate on long-press when haptics is true', () => {
    const vibrateCalls = [];
    const orig = navigator.vibrate;
    navigator.vibrate = (ms) => { vibrateCalls.push(ms); return true; };

    const { element, cleanup } = renderPawsistantButton({
      container: host, meta, metricText: '', disabled: false,
      onTap: () => {}, onLongPress: () => {}, timers: [], haptics: true,
    });
    vi.useFakeTimers();
    element.dispatchEvent(new MouseEvent('pointerdown'));
    vi.advanceTimersByTime(500);
    vi.useRealTimers();
    expect(vibrateCalls).toEqual([40]);
    cleanup();
    navigator.vibrate = orig;
  });
});
