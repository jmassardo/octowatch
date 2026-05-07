import { api } from './client';

export interface TelemetrySummary {
  events_per_second: number;
  events_today: number;
  active_workers: number;
  queue_depth: number;
  last_event_at: string | null;
  error_rate: number;
}

export interface StreamStatus {
  org: string;
  ingestion_source: string;
  last_event_at: string;
  events_last_hour: number;
  events_per_minute: number;
  avg_latency_seconds: number;
  minutes_since_last: number;
}

export interface ActiveWorker {
  worker_type: string;
  tasks_processed_24h: number;
  last_heartbeat: string;
  first_seen_24h: string;
}

export interface HealthEvent {
  signal_type: string;
  severity: string;
  org: string | null;
  occurred_at: string;
  detail: Record<string, unknown>;
  resolved_at: string | null;
}

export interface WorkerHealthResponse {
  health_events: HealthEvent[];
  active_workers: ActiveWorker[];
}

export interface VolumeBucket {
  bucket_time: string;
  category: string;
  event_count: number;
}

export interface TopAction {
  action: string;
  count: number;
}

export interface EventVolumeResponse {
  volume: VolumeBucket[];
  top_actions: TopAction[];
}

export interface IngestionError {
  id: number;
  occurred_at: string;
  org: string | null;
  signal_type: string;
  severity: string;
  detail: Record<string, unknown>;
  resolved_at: string | null;
}

export interface IngestionGap {
  org: string;
  last_event_at: string;
  minutes_since_last: number;
}

export interface ErrorsResponse {
  errors: IngestionError[];
  gaps: IngestionGap[];
}

export function getTelemetrySummary(): Promise<TelemetrySummary> {
  return api.get<TelemetrySummary>('/telemetry/summary');
}

export function getStreamStatus(limit = 50): Promise<{ streams: StreamStatus[] }> {
  return api.get<{ streams: StreamStatus[] }>(`/telemetry/stream-status?limit=${limit}`);
}

export function getWorkerHealth(): Promise<WorkerHealthResponse> {
  return api.get<WorkerHealthResponse>('/telemetry/worker-health');
}

export function getEventVolume(bucket = 'hour', hours = 24): Promise<EventVolumeResponse> {
  return api.get<EventVolumeResponse>(`/telemetry/event-volume?bucket=${bucket}&hours=${hours}`);
}

export function getIngestionErrors(limit = 100): Promise<ErrorsResponse> {
  return api.get<ErrorsResponse>(`/telemetry/errors?limit=${limit}`);
}
