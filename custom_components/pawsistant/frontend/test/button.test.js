/**
 * Pawsistant Card — Button module tests
 */
import { describe, it, expect, vi } from 'vitest';
import { renderPawsistantButton } from '../src/button.js';

describe('renderPawsistantButton', () => {
  it('creates a button element with emoji and label', () => {
    const container = document.createElement('div');
    const meta = { emoji: '💩', label: 'Poop', color: '#888' };
    const { element, cleanup } = renderPawsistantButton({
      container,
      meta,
      metricText: '(3 today)',
      onTap: () => {},
      onLongPress: () => {},
      timers: [],
    });

    expect(element.tagName).toBe('BUTTON');
    expect(element.className).toBe('log-btn');
    expect(element.querySelector('.btn-emoji').textContent).toBe('💩');
    expect(element.querySelector('.btn-label').textContent).toBe('Poop (3 today)');

    cleanup();
  });

  it('label omits metric text when empty', () => {
    const container = document.createElement('div');
    const meta = { emoji: '💧', label: 'Pee', color: '#4FC3F7' };
    const { element, cleanup } = renderPawsistantButton({
      container,
      meta,
      metricText: '',
      onTap: () => {},
      onLongPress: () => {},
      timers: [],
    });

    expect(element.querySelector('.btn-label').textContent).toBe('Pee');
    cleanup();
  });

  it('fires onTap on short click', () => {
    const container = document.createElement('div');
    const meta = { emoji: '💩', label: 'Poop', color: '#888' };
    const taps = [];
    const { element, cleanup } = renderPawsistantButton({
      container,
      meta,
      metricText: '',
      onTap: () => taps.push(1),
      onLongPress: () => {},
      timers: [],
    });

    element.dispatchEvent(new MouseEvent('pointerdown'));
    element.dispatchEvent(new MouseEvent('pointerup'));
    element.dispatchEvent(new MouseEvent('click'));

    expect(taps.length).toBe(1);
    cleanup();
  });

  it('cleanup removes listeners without throwing', () => {
    const container = document.createElement('div');
    const meta = { emoji: '💩', label: 'Poop', color: '#888' };
    const { cleanup } = renderPawsistantButton({
      container,
      meta,
      metricText: '',
      onTap: () => {},
      onLongPress: () => {},
      timers: [],
    });

    expect(() => cleanup()).not.toThrow();
  });
});
