/**
 * Pawsistant Card — Event binding
 *
 * bindEvents wires up all DOM listeners after each render.
 * Using import type avoids a circular runtime dependency.
 */

import type { PawsistantCard } from './index';
import { setupLongPress } from './interactions';
import { openBackdateForm, openWeightForm, openEditForm, closeForm } from './forms';

interface LongPressBtn extends HTMLButtonElement {
  _longPressCleanup?: () => void;
}

export function bindEvents(card: PawsistantCard, root: ShadowRoot): void {

  root.querySelectorAll<LongPressBtn>('.log-btn').forEach(btn => {
    const isWeight = btn.dataset.weight === 'true';
    const hasLongPress = btn.dataset.longpress === 'true';

    if (isWeight) {
      btn.addEventListener('pointerdown', (e) => { e.preventDefault(); });
      btn.addEventListener('pointerup', (e) => {
        e.preventDefault();
        if (card._activeForm === 'weight') {
          closeForm(card);
        } else {
          openWeightForm(card, btn);
        }
      });
      /* U3 — keyboard: Enter opens form, Space = instant log (weight just opens form) */
      btn.addEventListener('keydown', (e: KeyboardEvent) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          if (card._activeForm === 'weight') {
            closeForm(card);
          } else {
            openWeightForm(card, btn);
          }
        }
      });
      return;
    }

    if (hasLongPress) {
      const cleanup = setupLongPress(btn, {
        onLongPress: (b) => {
          const type = b.dataset.type || '';
          card._instantLog(b, type);
        },
        onTap: (b) => {
          const type = b.dataset.type;
          if (card._activeForm === 'backdate' && card._activeType === type) {
            closeForm(card);
          } else {
            openBackdateForm(card, b, type);
          }
        },
      }, card._timers);
      // Store cleanup for future use if needed
      btn._longPressCleanup = cleanup;
      return;
    }

    // Fallback: simple click = backdate form
    btn.addEventListener('click', () => {
      openBackdateForm(card, btn, btn.dataset.type);
    });
  });

  /* U9 — two-tap delete confirmation */
  root.querySelectorAll<HTMLButtonElement>('.delete-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const eventId = btn.dataset.id;
      if (!eventId) return;

      if (card._deleteConfirmState.has(eventId)) {
        // Second tap — confirm and delete
        clearTimeout(card._deleteConfirmState.get(eventId));
        card._deleteConfirmState.delete(eventId);
        btn.classList.remove('confirm-pending');
        btn.textContent = '🗑️';
        card._deleteEvent(eventId, btn);
      } else {
        // First tap — show confirm state
        btn.classList.add('confirm-pending');
        btn.textContent = 'Delete?';
        const revertId = card._setTimeout(() => {
          card._deleteConfirmState.delete(eventId);
          btn.classList.remove('confirm-pending');
          btn.textContent = '🗑️';
        }, 3000);
        card._deleteConfirmState.set(eventId, revertId);
      }
    });
  });

  /* Edit button on event rows */
  root.querySelectorAll<HTMLButtonElement>('.edit-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const row = btn.closest<HTMLElement>('.event-row');
      if (!row) return;
      const eventType = row.dataset.type;
      const timestamp = row.dataset.timestamp;
      const note = row.dataset.note;
      const value = row.dataset.value;
      const eventId = row.dataset.id;
      openEditForm(card, eventType, timestamp, note, value, eventId);
    });
  });

  /* Load more button — click is fallback, IntersectionObserver auto-triggers */
  const loadMoreBtn = root.querySelector('#load-more-btn');
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', () => {
      card._fetchTimeline(true);
    });
  }

  /* ── Event Types Manager Panel listeners ── */

  // Gear button to open panel
  const gearBtn = root.querySelector('#et-gear-btn');
  if (gearBtn) {
    gearBtn.addEventListener('click', () => card._openEventTypesPanel());
  }

  // Back button in panel header
  const backBtn = root.querySelector('#et-back-btn');
  if (backBtn) {
    backBtn.addEventListener('click', () => card._closeEventTypesPanel());
  }

  // Back button in form header (return to list)
  const formBackBtn = root.querySelector('#et-form-back-btn');
  if (formBackBtn) {
    formBackBtn.addEventListener('click', () => {
      card._editingEventType = null;
      card._eventTypeFormError = null;
      card._render();
    });
  }

  // Add button
  const addBtn = root.querySelector('#et-add-btn');
  if (addBtn) {
    addBtn.addEventListener('click', () => card._openEventTypeForm('__ADD__'));
  }

  // Edit buttons on event type rows
  root.querySelectorAll<HTMLButtonElement>('.et-btn.edit').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.etKey;
      if (key) card._openEventTypeForm(key);
    });
  });

  // Delete buttons on event type rows
  root.querySelectorAll<HTMLButtonElement>('.et-btn.delete').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.etKey;
      if (key) card._deleteEventType(key);
    });
  });

  // Visibility checkboxes — toggle shown_types
  root.querySelectorAll<HTMLInputElement>('.et-visible-cb').forEach(cb => {
    cb.addEventListener('change', () => {
      const shownTypes = [...card._shownTypes()];
      const key = cb.dataset.etKey;
      if (cb.checked) {
        if (!shownTypes.includes(key!)) shownTypes.push(key!);
      } else {
        const idx = shownTypes.indexOf(key!);
        if (idx !== -1) shownTypes.splice(idx, 1);
      }
      card._saveShownTypes(shownTypes);
    });
  });

  // Drag-to-reorder on event type rows
  let _dragKey: string | null = null;
  root.querySelectorAll<HTMLElement>('.event-type-row[draggable]').forEach(row => {
    row.addEventListener('dragstart', (e: DragEvent) => {
      _dragKey = row.dataset.etKey || null;
      if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', _dragKey || '');
      }
      row.classList.add('et-dragging');
    });
    row.addEventListener('dragend', () => {
      row.classList.remove('et-dragging');
      root.querySelectorAll<HTMLElement>('.event-type-row').forEach(r => r.classList.remove('et-drag-over'));
      _dragKey = null;
    });
    row.addEventListener('dragover', (e: DragEvent) => {
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
      root.querySelectorAll<HTMLElement>('.event-type-row').forEach(r => r.classList.remove('et-drag-over'));
      row.classList.add('et-drag-over');
    });
    row.addEventListener('drop', (e: DragEvent) => {
      e.preventDefault();
      const fromKey = _dragKey;
      const toKey = row.dataset.etKey;
      if (!fromKey || fromKey === toKey) return;

      // Get current full ordered list from DOM
      const allRows = [...root.querySelectorAll<HTMLElement>('.event-type-row')];
      const orderedAll = allRows.map(r => r.dataset.etKey as string);

      // Reorder: move fromKey to toKey's position
      const fromIdx = orderedAll.indexOf(fromKey);
      const toIdx = orderedAll.indexOf(toKey!);
      orderedAll.splice(fromIdx, 1);
      orderedAll.splice(toIdx, 0, fromKey);

      // Only keep keys that were in shown_types (preserve visibility state)
      const shownTypes = card._shownTypes();
      const newShown = orderedAll.filter(k => shownTypes.includes(k));
      card._saveShownTypes(newShown);
    });
  });

  // Pick icon button — use the icon picker helper
  const browseBtn = root.querySelector('#et-browse-btn');
  if (browseBtn) {
    browseBtn.addEventListener('click', async () => {
      const iconInput = root.querySelector<HTMLInputElement>('#et-icon-input');
      const currentIcon = iconInput ? iconInput.value.trim() : '';
      const picked = await card._pickIcon(currentIcon);
      if (picked && iconInput) {
        iconInput.value = picked as string;
      }
    });
  }

  // Color input — update hex display
  const colorInput = root.querySelector<HTMLInputElement>('#et-color-input');
  const colorHex = root.querySelector<HTMLElement>('#et-color-hex');
  if (colorInput && colorHex) {
    colorInput.addEventListener('input', () => {
      colorHex.textContent = colorInput.value;
    });
  }

  // Submit form
  const submitBtn = root.querySelector('#et-form-submit');
  if (submitBtn) {
    submitBtn.addEventListener('click', () => card._saveEventTypeForm());
  }

  // Cancel form
  const cancelBtn = root.querySelector('#et-form-cancel');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', () => {
      card._editingEventType = null;
      card._eventTypeFormError = null;
      card._render();
    });
  }
}
