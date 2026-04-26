/**
 * Pawsistant Card — forms module tests
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { openBackdateForm, openWeightForm } from '../src/forms.js';

describe('openBackdateForm', () => {
  let host;
  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });
  afterEach(() => {
    host.remove();
    document.body.querySelectorAll('.pawsistant-form-dialog').forEach(el => el.remove());
    // Clean stray injected styles to keep tests independent
    document.head.querySelectorAll('style[data-pawsistant-forms]').forEach(el => el.remove());
  });

  it('resolves null when the user cancels', async () => {
    const meta = { emoji: 'P', label: 'Poop', color: '#888', icon: '' };
    const p = openBackdateForm({ container: host, meta, defaults: {} });

    await Promise.resolve();
    const cancelBtn = host.querySelector('.btn-cancel')
      || document.querySelector('.pawsistant-form-dialog .btn-cancel');
    cancelBtn.click();

    const result = await p;
    expect(result).toBeNull();
  });

  it('resolves { timestamp, note, cleanup } on submit', async () => {
    const meta = { emoji: 'P', label: 'Poop', color: '#888', icon: '' };
    const p = openBackdateForm({ container: host, meta, defaults: {} });
    await Promise.resolve();

    const slider = host.querySelector('#minutes-slider')
      || document.querySelector('.pawsistant-form-dialog #minutes-slider');
    slider.value = '10';
    slider.dispatchEvent(new Event('input'));

    const note = host.querySelector('#backdate-note')
      || document.querySelector('.pawsistant-form-dialog #backdate-note');
    note.value = 'after dinner';

    const submitBtn = host.querySelector('.btn-submit')
      || document.querySelector('.pawsistant-form-dialog .btn-submit');
    submitBtn.click();

    const result = await p;
    expect(result).not.toBeNull();
    expect(typeof result.timestamp).toBe('string');
    expect(result.note).toBe('after dinner');
    expect(typeof result.cleanup).toBe('function');
    const delta = Date.now() - new Date(result.timestamp).getTime();
    expect(delta).toBeGreaterThan(9 * 60000);
    expect(delta).toBeLessThan(11 * 60000);
    // Caller controls cleanup now
    result.cleanup();
  });

  it('keeps form in the DOM after submit until cleanup is called', async () => {
    const meta = { emoji: 'P', label: 'Poop', color: '#888', icon: '' };
    const p = openBackdateForm({ container: host, meta, defaults: {} });
    await Promise.resolve();

    const submitBtn = host.querySelector('.btn-submit')
      || document.querySelector('.pawsistant-form-dialog .btn-submit');
    submitBtn.click();
    const result = await p;

    // Form must still be mounted so caller can call _showFormError on error
    expect(host.querySelector('.pawsistant-form')).not.toBeNull();

    result.cleanup();
    expect(host.querySelector('.pawsistant-form')).toBeNull();
  });

  it('auto-removes its DOM on cancel', async () => {
    const meta = { emoji: 'P', label: 'Poop', color: '#888', icon: '' };
    const p = openBackdateForm({ container: host, meta, defaults: {} });
    await Promise.resolve();

    const cancelBtn = host.querySelector('.btn-cancel')
      || document.querySelector('.pawsistant-form-dialog .btn-cancel');
    cancelBtn.click();
    await p;

    expect(host.querySelector('.pawsistant-form')).toBeNull();
    expect(document.querySelectorAll('.pawsistant-form-dialog').length).toBe(0);
  });

  it('resolves with undefined note when no note entered', async () => {
    const meta = { emoji: 'P', label: 'Poop', color: '#888', icon: '' };
    const p = openBackdateForm({ container: host, meta, defaults: {} });
    await Promise.resolve();

    const submitBtn = host.querySelector('.btn-submit')
      || document.querySelector('.pawsistant-form-dialog .btn-submit');
    submitBtn.click();

    const result = await p;
    expect(result).not.toBeNull();
    expect(result.note).toBeUndefined();
    result.cleanup();
  });

  it('escapes unsafe meta.label when rendering', async () => {
    const badLabel = '<scr' + 'ipt>x</scr' + 'ipt>';
    const meta = { emoji: 'P', label: badLabel, color: '#888', icon: '' };
    const p = openBackdateForm({ container: host, meta, defaults: {} });
    await Promise.resolve();
    const title = host.querySelector('.form-title')
      || document.querySelector('.pawsistant-form-dialog .form-title');
    expect(title.querySelector('script')).toBeNull();
    expect(title.textContent).toContain(badLabel);

    const cancelBtn = host.querySelector('.btn-cancel')
      || document.querySelector('.pawsistant-form-dialog .btn-cancel');
    cancelBtn.click();
    await p;
  });

  it('injects the form stylesheet into a ShadowRoot when container lives inside one', async () => {
    const shadowHost = document.createElement('div');
    document.body.appendChild(shadowHost);
    const shadow = shadowHost.attachShadow({ mode: 'open' });
    const inner = document.createElement('div');
    shadow.appendChild(inner);

    const meta = { emoji: 'P', label: 'Poop', color: '#888', icon: '' };
    const p = openBackdateForm({ container: inner, meta, defaults: {} });
    await Promise.resolve();

    // Style must be inside the ShadowRoot, not only in document.head
    const shadowStyle = shadow.querySelector('style[data-pawsistant-forms]');
    expect(shadowStyle).not.toBeNull();

    // Cancel to resolve
    shadow.querySelector('.btn-cancel').click();
    await p;

    shadowHost.remove();
  });

  it('injects the form stylesheet into document.head when container is null (floating)', async () => {
    const meta = { emoji: 'P', label: 'Poop', color: '#888', icon: '' };
    const p = openBackdateForm({ container: null, meta, defaults: {} });
    await Promise.resolve();

    const headStyle = document.head.querySelector('style[data-pawsistant-forms]');
    expect(headStyle).not.toBeNull();

    document.querySelector('.pawsistant-form-dialog .btn-cancel').click();
    await p;
  });

  it('does not duplicate the style element when opened twice in the same root', async () => {
    const shadowHost = document.createElement('div');
    document.body.appendChild(shadowHost);
    const shadow = shadowHost.attachShadow({ mode: 'open' });
    const inner = document.createElement('div');
    shadow.appendChild(inner);

    const meta = { emoji: 'P', label: 'Poop', color: '#888', icon: '' };

    const p1 = openBackdateForm({ container: inner, meta, defaults: {} });
    await Promise.resolve();
    shadow.querySelector('.btn-cancel').click();
    await p1;

    const p2 = openBackdateForm({ container: inner, meta, defaults: {} });
    await Promise.resolve();

    const styles = shadow.querySelectorAll('style[data-pawsistant-forms]');
    expect(styles.length).toBe(1);

    shadow.querySelector('.btn-cancel').click();
    await p2;

    shadowHost.remove();
  });
});

describe('openWeightForm', () => {
  let host;
  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });
  afterEach(() => {
    host.remove();
    document.body.querySelectorAll('.pawsistant-form-dialog').forEach(el => el.remove());
    document.head.querySelectorAll('style[data-pawsistant-forms]').forEach(el => el.remove());
  });

  it('resolves null on cancel', async () => {
    const meta = { emoji: 'W', label: 'Weight', color: '#888', icon: '' };
    const p = openWeightForm({ container: host, meta, currentWeight: 42, displayUnit: 'lbs' });
    await Promise.resolve();

    const cancelBtn = host.querySelector('.btn-cancel')
      || document.querySelector('.pawsistant-form-dialog .btn-cancel');
    cancelBtn.click();
    expect(await p).toBeNull();
  });

  it('resolves { value, timestamp, note, cleanup } in lbs when displayUnit is lbs', async () => {
    const meta = { emoji: 'W', label: 'Weight', color: '#888', icon: '' };
    const p = openWeightForm({ container: host, meta, currentWeight: null, displayUnit: 'lbs' });
    await Promise.resolve();

    const input = host.querySelector('#weight-input')
      || document.querySelector('.pawsistant-form-dialog #weight-input');
    input.value = '55';
    const submit = host.querySelector('.btn-submit')
      || document.querySelector('.pawsistant-form-dialog .btn-submit');
    submit.click();

    const r = await p;
    expect(r.value).toBe(55);
    expect(typeof r.timestamp).toBe('string');
    expect(typeof r.cleanup).toBe('function');
    r.cleanup();
  });

  it('converts kg entry to stored lbs', async () => {
    const meta = { emoji: 'W', label: 'Weight', color: '#888', icon: '' };
    const p = openWeightForm({ container: host, meta, currentWeight: null, displayUnit: 'kg' });
    await Promise.resolve();

    const input = host.querySelector('#weight-input')
      || document.querySelector('.pawsistant-form-dialog #weight-input');
    input.value = '20';
    const submit = host.querySelector('.btn-submit')
      || document.querySelector('.pawsistant-form-dialog .btn-submit');
    submit.click();

    const r = await p;
    expect(r.value).toBeCloseTo(44.1, 1);
    r.cleanup();
  });

  it('stays open on invalid input', async () => {
    const meta = { emoji: 'W', label: 'Weight', color: '#888', icon: '' };
    const p = openWeightForm({ container: host, meta, currentWeight: null, displayUnit: 'lbs' });
    await Promise.resolve();

    const input = host.querySelector('#weight-input')
      || document.querySelector('.pawsistant-form-dialog #weight-input');
    input.value = 'nope';
    const submit = host.querySelector('.btn-submit')
      || document.querySelector('.pawsistant-form-dialog .btn-submit');
    submit.click();

    await new Promise(r => setTimeout(r, 10));
    expect(host.querySelector('#weight-input')
      || document.querySelector('.pawsistant-form-dialog #weight-input')).not.toBeNull();

    const cancelBtn = host.querySelector('.btn-cancel')
      || document.querySelector('.pawsistant-form-dialog .btn-cancel');
    cancelBtn.click();
    expect(await p).toBeNull();
  });

  it('keeps form in the DOM after submit until cleanup is called', async () => {
    const meta = { emoji: 'W', label: 'Weight', color: '#888', icon: '' };
    const p = openWeightForm({ container: host, meta, currentWeight: null, displayUnit: 'lbs' });
    await Promise.resolve();

    const input = host.querySelector('#weight-input');
    input.value = '50';
    const submit = host.querySelector('.btn-submit');
    submit.click();

    const r = await p;
    expect(host.querySelector('.pawsistant-form')).not.toBeNull();

    r.cleanup();
    expect(host.querySelector('.pawsistant-form')).toBeNull();
  });

  it('auto-removes its DOM on cancel', async () => {
    const meta = { emoji: 'W', label: 'Weight', color: '#888', icon: '' };
    const p = openWeightForm({ container: host, meta, currentWeight: null, displayUnit: 'lbs' });
    await Promise.resolve();

    host.querySelector('.btn-cancel').click();
    await p;

    expect(host.querySelector('.pawsistant-form')).toBeNull();
  });

  it('injects the form stylesheet into a ShadowRoot when container lives inside one', async () => {
    const shadowHost = document.createElement('div');
    document.body.appendChild(shadowHost);
    const shadow = shadowHost.attachShadow({ mode: 'open' });
    const inner = document.createElement('div');
    shadow.appendChild(inner);

    const meta = { emoji: 'W', label: 'Weight', color: '#888', icon: '' };
    const p = openWeightForm({ container: inner, meta, currentWeight: null, displayUnit: 'lbs' });
    await Promise.resolve();

    const shadowStyle = shadow.querySelector('style[data-pawsistant-forms]');
    expect(shadowStyle).not.toBeNull();

    shadow.querySelector('.btn-cancel').click();
    await p;

    shadowHost.remove();
  });
});
