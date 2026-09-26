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
  callService: (
    domain: string,
    service: string,
    data: Record<string, unknown>,
    target?: Record<string, unknown>,
    notifyOnError?: boolean,
    returnResponse?: boolean,
  ) => Promise<unknown>;
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

/** The supply an event type uses: a part that Home Keeper counts. */
export interface SupplyMeta {
  asset_id?: string;
  part_id?: string;
  name?: string;
  amount?: number;
  /** Home Keeper's spares number for the part; the backend resolves it. */
  entity_id?: string | null;
}

export interface EventMeta {
  emoji: string;
  label: string;
  color: string;
  icon?: string;
  supply?: SupplyMeta;
}

export interface EventMetaInput {
  name?: string;
  icon?: string;
  color?: string;
  supply?: SupplyMeta;
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
  /** The "Uses a supply" fields, as typed. Empty strings mean "not set". */
  supply?: SupplyFormState;
}

export interface SupplyFormState {
  name: string;
  amount: string;
  stock: string;
  reorder_at: string;
  unit: string;
  pack: string;
}

/* ── Metric label formatters ───────────────────────────────────────── */

export interface MetricLabels {
  [key: string]: unknown;
  daily_count: (n: number) => string;
  days_since: (n: number) => string;
  last_value: (v: number, unit?: string) => string;
  hours_since: (n: number) => string;
}

/* ── Button card config ───────────────────────────────────────────── */

export interface ButtonConfig {
  event_type: string;
}

export interface PawsistantButtonCardConfig {
  type: string;
  dog: string;
  buttons: ButtonConfig[];
  show_title?: boolean;
  show_event_log?: boolean;
  weight_unit?: string;
  buttons_per_row?: number;
  /** @deprecated — use buttons[] instead; kept for backward compat migration */
  event_type?: string;
}

/* ── Standalone form results ─────────────────────────────────────── */

export interface BackdateFormResult {
  timestamp: string;
  note?: string;
  cleanup: () => void;
  /** The logged event, for an Undo; null from an older backend. */
  eventId?: string | null;
}

export interface WeightFormResult {
  value: number;
  cleanup: () => void;
}

export interface EditFormResult {
  cleanup: () => void;
}

/* ── Interaction types ─────────────────────────────────────────────── */

export interface LongPressHandlers {
  onLongPress?: (btn: HTMLButtonElement) => void;
  onTap?: (btn: HTMLButtonElement) => void;
}