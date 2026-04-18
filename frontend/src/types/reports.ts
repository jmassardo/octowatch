export interface ReportEnvelope {
  readonly report_type: string;
  readonly org: string | null;
  readonly granularity: string;
  readonly window_days: number;
  readonly data_source: string;
  readonly generated_at: string;
  readonly data: readonly Record<string, unknown>[];
}

export interface MAUBucket {
  readonly bucket: string;
  readonly unique_actors: number;
  readonly total_events: number;
}

export interface SeatUtilizationBucket {
  readonly bucket: string;
  readonly active_seat_count: number;
  readonly provisioned_seat_count: number;
  readonly utilization_pct: number;
}

export interface ActionsVolumeBucket {
  readonly bucket: string;
  readonly org: string | null;
  readonly workflow_runs: number;
  readonly unique_actors: number;
  readonly unique_repos: number;
  readonly workflow_runs_total: number;
  readonly workflow_runs_succeeded: number;
  readonly workflow_runs_failed: number;
  readonly success_rate_pct: number;
}

export interface CopilotSeatsBucket {
  readonly bucket: string;
  readonly seats_assigned: number;
  readonly seats_revoked: number;
  readonly seats_net: number;
  readonly policy_change_count: number;
}

export interface RepoCreationRateBucket {
  readonly bucket: string;
  readonly org: string | null;
  readonly repos_created: number;
  readonly unique_creators: number;
}

export interface CodespaceHoursBucket {
  readonly bucket: string;
  readonly org: string | null;
  readonly codespace_events: number;
  readonly unique_users: number;
  readonly total_billable_hours: number;
}

export interface PATCountsBucket {
  readonly bucket: string;
  readonly org: string | null;
  readonly actions: Readonly<Record<string, number>>;
}

export interface WebhookCountsBucket {
  readonly bucket: string;
  readonly org: string | null;
  readonly actions: Readonly<Record<string, number>>;
}

export type ReportGranularity = 'daily' | 'weekly' | 'monthly';

export interface ReportParams {
  org?: string;
  granularity?: ReportGranularity;
  window_days?: 7 | 30 | 60 | 90;
}

export interface ReportCatalogEntry {
  readonly id: string;
  readonly type: string;
  readonly title: string;
  readonly description?: string;
  readonly data_source?: string;
  readonly generated_at: string | null;
  readonly status: string;
  readonly tags?: readonly string[];
}
