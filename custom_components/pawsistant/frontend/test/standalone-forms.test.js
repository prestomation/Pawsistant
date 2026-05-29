/**
 * Pawsistant Card — Standalone forms tests
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { openBackdateForm, openWeightForm, _ensureFormStyles } from '../src/standalone-forms.js';

// Mock hass
function mockHass() {
  return {
    states: {},
    callService: vi.fn().mockResolvedValue(undefined),
  };
}

describe('_ensureFormStyles', () => {
  it('injects styles into a container', () => {
    const container = document.createElement('div');
    _ensureFormStyles(container);
    const style = container.querySelector('[data-pawsistant-forms]');
    expect(style).not.toBeNull();
    expect(style.tagName).toBe('STYLE');
  });

  it('does not duplicate styles on second call', () => {
    const container = document.createElement('div');
    _ensureFormStyles(container);
    _ensureFormStyles(container);
    const styles = container.querySelectorAll('[data-pawsistant-forms]');
    expect(styles.length).toBe(1);
  });
});

describe('openBackdateForm', () => {
  it('resolves with timestamp on submit', async () => {
    const container = document.createElement('div');
    const hass = mockHass();
    const meta = { emoji: '💩', label: 'Poop', color: '#888' };

    const promise = openBackdateForm({
      container,
      meta,
      hass,
      dog: 'Sharky',
      eventType: 'poop',
    });

    // Simulate clicking submit
    const submitBtn = container.querySelector('#pbc-form-submit');
    expect(submitBtn).not.toBeNull();
    submitBtn.click();

    const result = await promise;
    expect(result).not.toBeNull();
    expect(result.timestamp).toBeDefined();
    expect(typeof result.cleanup).toBe('function');
    expect(hass.callService).toHaveBeenCalledWith('pawsistant', 'log_event', expect.objectContaining({
      dog: 'Sharky',
      event_type: 'poop',
    }));
  });

  it('resolves null on cancel', async () => {
    const container = document.createElement('div');
    const hass = mockHass();
    const meta = { emoji: '💩', label: 'Poop', color: '#888' };

    const promise = openBackdateForm({
      container,
      meta,
      hass,
      dog: 'Sharky',
      eventType: 'poop',
    });

    const cancelBtn = container.querySelector('#pbc-form-cancel');
    expect(cancelBtn).not.toBeNull();
    cancelBtn.click();

    const result = await promise;
    expect(result).toBeNull();
  });
});

describe('openWeightForm', () => {
  it('validates weight range (rejects invalid)', async () => {
    const container = document.createElement('div');
    const hass = mockHass();
    const meta = { emoji: '⚖️', label: 'Weight', color: '#888' };

    const promise = openWeightForm({
      container,
      meta,
      hass,
      dog: 'Sharky',
    });

    // Set an invalid weight and submit
    const input = container.querySelector('#pbc-weight-input');
    input.value = '0'; // below min of 1
    const submitBtn = container.querySelector('#pbc-form-submit');
    submitBtn.click();

    // Form should NOT have resolved — callService should not be called
    expect(hass.callService).not.toHaveBeenCalled();

    // Cancel to clean up
    container.querySelector('#pbc-form-cancel').click();
    const result = await promise;
    expect(result).toBeNull();
  });

  it('resolves null on cancel', async () => {
    const container = document.createElement('div');
    const hass = mockHass();
    const meta = { emoji: '⚖️', label: 'Weight', color: '#888' };

    const promise = openWeightForm({
      container,
      meta,
      hass,
      dog: 'Sharky',
    });

    container.querySelector('#pbc-form-cancel').click();
    const result = await promise;
    expect(result).toBeNull();
  });
});
