export interface ReportEnvelope {
  readonly report_type: string;
  readonly org: string | null;
  readonly granularity: string;
  readonly window_days: number;
  readonly generated_at: string;
  readonly data: readonly Record<string, unknown>[];
}

export interface MAUBucket {
  readonly bucket: string;
  readonly unique_actor_count: number;
  readonly unique_bot_actor_count: number;
  readonly new_actor_count: number;
}

export interface SeatUtilizationBucket {
  readonly bucket: string;
  readonly active_seat_count: number;
  readonly provisioned_seat_count: number;
  readonly utilization_pct: number;
}

export interface ActionsVolumeBucket {
  readonly bucket: string;
  readonly workflow_runs_total: number;
  readonly workflow_runs_succeeded: number;
  readonly workflow_runs_failed: number;
  readonly success_rate_pct: number;
  readonly unique_workflows: number;
}

export interface CopilotSeatsBucket {
  readonly bucket: string;
  readonly seats_assigned: number;
  readonly seats_revoked: number;
  readonly seats_net: number;
  readonly policy_change_count: number;
}

export interface PATCountsBucket {
  readonly bucket: string;
  readonly pats_created: number;
  readonly pats_deleted: number;
  readonly pats_expired: number;
  readonly fine_grained_pats: number;
  readonly classic_pats: number;
  readonly high_access_pats: number;
}

export interface WebhookCountsBucket {
  readonly bucket: string;
  readonly webhooks_created: number;
  readonly webhooks_deleted: number;
  readonly app_installs: number;
  readonly app_uninstalls: number;
  readonly unique_webhook_targets: number;
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
  readonly generated_at: string;
  readonly status: string;
  readonly tags: readonly string[];
}
