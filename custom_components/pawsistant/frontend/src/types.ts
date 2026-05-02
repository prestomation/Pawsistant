/**
 * Pawsistant Card — TypeScript type definitions
 */

/* ── Home Assistant minimal types ──────────────────────────────────── */

export interface HassEntity {
  state: string;
  attributes: Record<string, any>;
}

export interface HassServices {
  [domain: string]: {
    [service: string]: (data: Record<string, unknown>) => Promise<unknown>;
  };
}

export interface HassConnection {
  sendCommand: (command: Record<string, unknown>) => Promise<unknown>;
  sendMessagePromise: (msg: Record<string, unknown>) => Promise<unknown>;
}

export interface HomeAssistant {
  states: Record<string, HassEntity>;
  callService: (domain: string, service: string, data: Record<string, unknown>) => Promise<unknown>;
  connection?: HassConnection;
  language?: string;
  config?: { time_zone?: string };
}

/* ── Event / Timeline types ───────────────────────────────────────── */

export interface TimelineEvent {
  type: string;
  event_id: string;
  time: string;
  day: string;
  date: string;
  iso: string;
  note: string;
  value?: number | string | null;
}

export interface WSEvent {
  id: string;
  event_type: string;
  timestamp: string;
  pet_name: string;
  note: string;
  created_by_name?: string;
  extra?: Record<string, unknown>;
  value?: number | string | null;
}

/* ── Registry types ───────────────────────────────────────────────── */

export interface EventMeta {
  emoji: string;
  label: string;
  color: string;
  icon?: string;
}

export interface EventMetaInput {
  name?: string;
  icon?: string;
  color?: string;
}

export interface Registry {
  [eventType: string]: EventMeta;
}

export interface RegistryResult {
  registry: Registry;
  metrics: Record<string, string>;
}

/* ── Entity resolution ────────────────────────────────────────────── */

export interface DogEntities {
  timeline: string;
  pee_count: string;
  poop_count: string;
  medicine_days: string;
  weight: string;
}

/* ── Card config ───────────────────────────────────────────────────── */

export interface PawsistantCardConfig {
  type: string;
  dog: string;
  timeline_entity?: string;
  pee_count_entity?: string;
  poop_count_entity?: string;
  medicine_days_entity?: string;
  weight_entity?: string;
  buttons_per_row?: number;
  weight_unit?: string;
  shown_types?: string[];
}

/* ── Card state ────────────────────────────────────────────────────── */

export interface EventTypeFormState {
  event_type: string;
  name: string;
  icon: string;
  color: string;
  metric: string;
}

/* ── Metric label formatters ───────────────────────────────────────── */

export interface MetricLabels {
  daily_count: (n: number) => string;
  days_since: (n: number) => string;
  last_value: (v: number, unit?: string) => string;
  hours_since: (n: number) => string;
}

/* ── Interaction types ─────────────────────────────────────────────── */

export interface LongPressHandlers {
  onLongPress?: (btn: HTMLButtonElement) => void;
  onTap?: (btn: HTMLButtonElement) => void;
}