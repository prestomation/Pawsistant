/**
 * Pawsistant Card — Metric label formatters
 */

export const METRIC_LABELS = {
  daily_count: (n) => `${n} today`,
  days_since:  (n) => `${n} days`,
  last_value:  (v, unit) => `${v}${unit ? ' ' + unit : ''}`,
  hours_since: (n) => `${n} hours`,
};