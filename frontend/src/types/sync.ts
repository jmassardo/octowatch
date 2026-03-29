export type SyncRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

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
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly error_message: string | null;
  readonly entity_counts: Record<string, number> | null;
  readonly cursors: EntityStatus[];
}

export interface SyncRunSummary {
  readonly id: string;
  readonly status: SyncRunStatus;
  readonly trigger_type: 'manual' | 'scheduled';
  readonly triggered_by: string | null;
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
