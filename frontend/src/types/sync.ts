export type SyncRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export type PostProcessingStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface EntityStatus {
  readonly entity_type: string;
  readonly org: string | null;
  readonly status: 'pending' | 'in_progress' | 'completed' | 'failed';
  readonly items_synced: number;
  readonly last_cursor: string | null;
}

export interface SyncRun {
  readonly id: string;
  readonly status: SyncRunStatus;
  readonly trigger_type: 'manual' | 'scheduled';
  readonly triggered_by: string | null;
  readonly scope: string;
  readonly created_at: string;
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly error_message: string | null;
  readonly entity_counts: Record<string, number> | null;
  readonly post_processing_status: PostProcessingStatus | null;
  readonly cursors: EntityStatus[];
}

export interface SyncRunSummary {
  readonly id: string;
  readonly status: SyncRunStatus;
  readonly trigger_type: 'manual' | 'scheduled';
  readonly triggered_by: string | null;
  readonly created_at: string;
  readonly started_at: string | null;
  readonly completed_at: string | null;
}

export interface SyncRunsResponse {
  readonly items: SyncRunSummary[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
  readonly has_next: boolean;
}

export interface SyncConfig {
  readonly app_id: number | null;
  readonly enterprise_slug: string | null;
  readonly installation_ids: { org: string | null; installation_id: number }[];
  readonly sync_enabled: boolean;
  readonly interval_days: number;
  readonly orgs: string[];
}

export interface SyncSchedule {
  readonly enabled: boolean;
  readonly interval_hours: number;
  readonly scope: string;
  readonly next_run_at: string | null;
  readonly last_completed_at: string | null;
}

export interface SyncLogEntry {
  readonly seq: number;
  readonly timestamp: string;
  readonly level: 'info' | 'warn' | 'error';
  readonly message: string;
  readonly entity_type: string | null;
  readonly org: string | null;
  readonly details: Record<string, unknown> | null;
}

export interface SyncLogsResponse {
  readonly entries: SyncLogEntry[];
  readonly last_seq: number;
}
