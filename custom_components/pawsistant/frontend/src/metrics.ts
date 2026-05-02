/**
 * Pawsistant Card — Metric label formatters
 */

import type { MetricLabels } from './types';

export const METRIC_LABELS: MetricLabels = {
  daily_count: (n: number): string => `${n} today`,
  days_since:  (n: number): string => `${n} days`,
  last_value:  (v: number, unit?: string): string => `${v}${unit ? ' ' + unit : ''}`,
  hours_since: (n: number): string => `${n} hours`,
};