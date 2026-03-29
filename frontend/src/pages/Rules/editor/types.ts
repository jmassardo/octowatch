export interface FieldCondition {
  field: string;
  operator: string;
  value: unknown;
}

export interface SequenceStep {
  action: string;
  min_count: number;
}

export interface XConfig {
  engine: string;
  distance_threshold_km?: number;
  speed_threshold_kmh?: number;
  suppress_proxy_ips?: boolean;
}

export interface LogicConfig {
  action_filters?: string[];
  field_conditions?: FieldCondition[];
  confidence?: number;
  // Threshold
  threshold?: number;
  time_window_minutes?: number;
  aggregation_key?: string;
  distinct_count_field?: string;
  // Sequence
  sequence_steps?: SequenceStep[];
  // Statistical
  x_config?: XConfig;
  // Posture
  entity_type?: string;
  check_type?: string;
  field?: string;
  operator?: string;
  expected?: unknown;
  value?: unknown;
  scope?: Record<string, unknown>;
}
