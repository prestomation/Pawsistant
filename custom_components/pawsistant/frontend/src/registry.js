/**
 * Pawsistant Card — Event-type registry
 *
 * Fallback metadata, dynamic registry builder, and icon→emoji mapping.
 */

/* Fallback registry — used when WS state hasn't been populated yet.
 * The card reads live registry from sensor attributes; these values are
 * retained as defaults so the card renders before any sensor has reported. */
export const FALLBACK_EVENT_META = {
  poop:     { emoji: '💩', label: 'Poop',     color: 'var(--warning-color, #FF8A65)' },
  pee:      { emoji: '💧', label: 'Pee',      color: 'var(--info-color, #4FC3F7)' },
  medicine: { emoji: '💊', label: 'Medicine', color: 'var(--error-color, #EF5350)' },
  sick:     { emoji: '🤒', label: 'Sick',     color: 'var(--error-color, #EF5350)' },
  food:     { emoji: '🍖', label: 'Food',     color: 'var(--warning-color, #FF8A65)' },
  treat:    { emoji: '🍪', label: 'Treat',    color: 'var(--warning-color, #FFCA28)' },
  walk:     { emoji: '🦮', label: 'Walk',     color: 'var(--success-color, #66BB6A)' },
  water:    { emoji: '🥤', label: 'Water',    color: 'var(--info-color, #29B6F6)' },
  sleep:    { emoji: '😴', label: 'Sleep',    color: 'var(--info-color, #7E57C2)' },
  vaccine:  { emoji: '💉', label: 'Vaccine',  color: 'var(--info-color, #26A69A)' },
  training: { emoji: '🎓', label: 'Training', color: 'var(--info-color, #5C6BC0)' },
  weight:   { emoji: '⚖️',  label: 'Weight',   color: 'var(--secondary-text-color, #78909C)' },
  teeth:    { emoji: '🦷', label: 'Teeth',   color: 'var(--secondary-text-color, #B0BEC5)' },
  grooming: { emoji: '✂️',  label: 'Grooming', color: 'var(--warning-color, #EC407A)' },
};

// Alias for backwards compat — old card config YAML may reference EVENT_META
export const EVENT_META = FALLBACK_EVENT_META;

export const DEFAULT_SHOWN_TYPES = ['poop', 'pee', 'medicine', 'sick', 'weight'];

/** Map an MDI icon name (e.g. "mdi:walk") to a fallback emoji. */
export function iconToEmoji(icon) {
  if (!icon) return undefined;  // undefined → getMeta uses fallback emoji from registry
  const map = {
    'mdi:walk': '🦮', 'mdi:food-drumstick': '🍖', 'mdi:cookie': '🍪',
    'mdi:bowl': '🍽️', 'mdi:cup-water': '🥤', 'mdi:water': '💧',
    'mdi:emoticon-poop': '💩', 'mdi:pill': '💊', 'mdi:scale-bathroom': '⚖️',
    'mdi:needle': '💉', 'mdi:sleep': '😴', 'mdi:content-cut': '✂️',
    'mdi:hand-pointing-up': '🎯', 'mdi:toothbrush': '🦷', 'mdi:emoticon-sick': '🤒',
    'mdi:tag': '🏷️', 'mdi:school': '🎓',
  };
  return map[icon] || '📝';
}

/**
 * Build the dynamic event-type registry from sensor attributes.
 * Reads from any Pawsistant sensor's `event_types` attribute (a dict
 * of {key: {name, icon, color}}).  Falls back to FALLBACK_EVENT_META.
 *
 * Also reads `button_metrics` ({key: metric_name}) for button labels.
 */
export function buildRegistry(hass) {
  // Deep-copy fallback as the base
  const fallbackRegistry = {};
  for (const [k, v] of Object.entries(FALLBACK_EVENT_META)) {
    fallbackRegistry[k] = { ...v };
  }
  const metrics = {};
  let foundLiveTypes = false;
  let liveRegistry = {};

  if (hass && hass.states) {
    for (const state of Object.values(hass.states)) {
      const attrs = state.attributes || {};
      if (attrs.event_types && typeof attrs.event_types === 'object' && !Array.isArray(attrs.event_types) && Object.keys(attrs.event_types).length > 0) {
        foundLiveTypes = true;
        // Build registry from ONLY the live event_types (authoritative source).
        // This ensures deleted types (tombstones) don't appear — they're not in this dict.
        for (const [k, v] of Object.entries(attrs.event_types)) {
          if (v && typeof v === 'object') {
            const fallbackEntry = fallbackRegistry[k] || {};
            liveRegistry[k] = {
              // If live icon maps to 📝 (unknown icon), preserve fallback emoji instead of overwriting
              emoji:    v.icon ? (iconToEmoji(v.icon) !== '📝' ? iconToEmoji(v.icon) : (fallbackEntry.emoji || '📝')) : (fallbackEntry.emoji || '📝'),
              label:    v.name  || k,
              color:    v.color || fallbackEntry.color || '#888',
              icon:     v.icon  || '',
            };
          }
        }
      }
      if (attrs.button_metrics && typeof attrs.button_metrics === 'object') {
        Object.assign(metrics, attrs.button_metrics);
      }
      if (foundLiveTypes) {
        break;  // got live types from this sensor, use them
      }
    }
  }

  // Use live registry if we found one; otherwise fall back to defaults
  const registry = foundLiveTypes ? liveRegistry : fallbackRegistry;

  return { registry, metrics };
}

export function getMeta(type, registry) {
  if (registry && registry[type]) {
    // Live registry: {emoji, label, icon, color} — emoji is pre-resolved by buildRegistry
    const entry = registry[type];
    // Use already-resolved emoji if available; only re-resolve if icon changed (entry.icon set, emoji undefined)
    const resolvedEmoji = (entry.emoji && entry.emoji !== '📝')
      ? entry.emoji
      : (entry.icon ? iconToEmoji(entry.icon) : (entry.emoji || '📝'));
    return {
      emoji: resolvedEmoji,
      label: entry.label || type,
      color: entry.color || 'var(--secondary-text-color, #888)',
      icon: entry.icon || '',
    };
  }
  const fallback = FALLBACK_EVENT_META[type];
  if (fallback) return { ...fallback, icon: '' };
  return { emoji: '📝', label: type, color: 'var(--secondary-text-color, #888)', icon: '' };
}