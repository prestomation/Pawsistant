/**
 * Pawsistant Card — English source of truth for translations.
 *
 * This file defines every translation key. All other locale files are typed
 * `Dict` so the TypeScript compiler enforces that they cover every key here.
 *
 * Interpolation tokens use {name} syntax (see i18n/index.ts → interpolate).
 */
export const en = {
  /* ── Inline forms ───────────────────────────────────────────────── */
  'form.log_title': 'Log {label}',
  'form.edit_title': 'Edit {label}',
  'form.log_weight_title': 'Log Weight',
  'form.edit_weight_title': 'Edit Weight',
  'form.minutes_ago': 'Minutes ago',
  'form.note_optional': 'Note (optional)',
  'form.note_placeholder': 'Add a note…',
  'form.weight_label': 'Weight ({unit})',
  'form.cancel': 'Cancel',
  'form.log_event': 'Log Event',
  'form.update_event': 'Update Event',
  'form.update_weight': 'Update Weight',

  /* ── Form error toasts ──────────────────────────────────────────── */
  'form.error.log_event': 'Failed to log event. Please try again.',
  'form.error.log_weight': 'Failed to log weight. Please try again.',
  'form.error.update_event': 'Failed to update event. Please try again.',

  /* ── Timeline ───────────────────────────────────────────────────── */
  'timeline.title': 'Timeline',
  'timeline.loading': 'Loading timeline…',
  'timeline.loading_short': 'Loading...',
  'timeline.empty_no_events': 'No events logged yet',
  'timeline.empty_24h': 'No events in the last 24 hours',
  'timeline.load_more': 'Load more (showing {shown} of {total})',
  'timeline.aria.edit_event': 'Edit {type} event at {time}',
  'timeline.aria.delete_event': 'Delete {type} event at {time}',
  'timeline.aria.edit_event_title': 'Edit event',
  'timeline.aria.delete_event_title': 'Delete event',
  'timeline.delete_confirm': 'Delete?',

  /* ── Quick-log button aria labels ───────────────────────────────── */
  'button.aria.log_weight': 'Log weight',
  'button.aria.log_event': 'Log {label}. Hold to log now.',
  'button.hold_hint': 'Hold to log now',

  /* ── Metric badges / suffixes ───────────────────────────────────── */
  'metric.daily_count': '{n} today',
  'metric.days_since': '{n} days',
  'metric.hours_since': '{n} hours',
  'metric.last_value': '{v}{unit}',
  'metric.daily_count_label': 'daily count',
  'metric.days_since_label': 'days since',
  'metric.hours_since_label': 'hours since',
  'metric.last_value_label': 'last value',

  /* ── Event types panel (gear) ───────────────────────────────────── */
  'panel.title': 'Event Types',
  'panel.configure': 'Configure event types',
  'panel.back': 'Back',
  'panel.back_to_list': 'Back to list',
  'panel.hint': 'Drag ☰ to reorder · 👁 toggles button visibility',
  'panel.add_event_type': 'Add Event Type',
  'panel.drag_to_reorder': 'Drag to reorder',
  'panel.hide_from_card': 'Hide from card',
  'panel.show_on_card': 'Show on card',
  'panel.edit_key': "Edit '{key}'",
  'panel.delete_key': "Delete '{key}'",
  'panel.delete_confirm': "Delete event type '{key}'? Events logged with this type will be preserved.",
  'panel.delete_failed': 'Delete failed: {msg}',
  'panel.unknown_error': 'Unknown error',

  /* ── Event type add/edit form ───────────────────────────────────── */
  'panel.form.add_title': 'Add Event Type',
  'panel.form.edit_title': 'Edit Event Type',
  'panel.form.display_name': 'Display name',
  'panel.form.display_name_placeholder': 'e.g. Morning Walk',
  'panel.form.key_prefix': 'Key:',
  'panel.form.event_type_key': 'Event type key',
  'panel.form.icon': 'Icon',
  'panel.form.color': 'Color',
  'panel.form.button_metric': 'Button metric',
  'panel.form.metric_hint': 'daily_count = "N today" · days_since = "N days" · last_value = "value" · hours_since = "N hours"',
  'panel.form.cancel': 'Cancel',
  'panel.form.add_submit': 'Add Event Type',
  'panel.form.save_submit': 'Save Changes',

  /* ── Event type form validation errors ──────────────────────────── */
  'panel.form.error.name_chars': 'Display name must contain letters or numbers.',
  'panel.form.error.name_required': 'Display name is required.',
  'panel.form.error.icon_required': 'Icon is required.',

  /* ── Card editors ───────────────────────────────────────────────── */
  'editor.pet': 'Pet *',
  'editor.select_pet': '— select a pet —',
  'editor.no_dogs_hint': 'No dogs found — enter a name manually or set up dogs via the integration options.',
  'editor.no_dogs_hint_short': 'No dogs found — enter a name manually.',
  'editor.weight_unit': 'Weight unit',
  'editor.buttons': 'Buttons',
  'editor.no_buttons': 'No buttons added yet.',
  'editor.add_event_type_option': '— add event type —',
  'editor.show_pet_name': 'Show pet name',
  'editor.show_event_log': 'Show event log button',
  'editor.buttons_per_row': 'Buttons per row',
  'editor.move_up': 'Move up',
  'editor.move_down': 'Move down',
  'editor.remove': 'Remove',
  'editor.pet_placeholder': 'Sharky',

  /* ── Event type fallback labels (built-in defaults only) ────────── */
  'eventtype.poop': 'Poop',
  'eventtype.pee': 'Pee',
  'eventtype.medicine': 'Medicine',
  'eventtype.sick': 'Sick',
  'eventtype.food': 'Food',
  'eventtype.treat': 'Treat',
  'eventtype.walk': 'Walk',
  'eventtype.water': 'Water',
  'eventtype.sleep': 'Sleep',
  'eventtype.vaccine': 'Vaccine',
  'eventtype.training': 'Training',
  'eventtype.weight': 'Weight',
  'eventtype.teeth': 'Teeth',
  'eventtype.grooming': 'Grooming',

  /* ── Event log popup (button card) ──────────────────────────────── */
  'button_card.open_event_log': 'Open event log',
  'popup.close': 'Close',

  /* ── Relative time (slider display) ─────────────────────────────── */
  'time.now': 'Now',
  'time.min_ago.one': '{n} min ago',
  'time.min_ago.other': '{n} min ago',
} as const;

export type TranslationKey = keyof typeof en;
export type Dict = Record<TranslationKey, string>;
