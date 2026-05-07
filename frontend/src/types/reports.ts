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

// Custom report types

export interface CustomReportColumnDef {
  readonly field: string;
  readonly label: string;
  readonly visible: boolean;
}

export interface CustomReportFilterDef {
  readonly field: string;
  readonly operator: 'eq' | 'neq' | 'gt' | 'gte' | 'lt' | 'lte' | 'contains' | 'in';
  readonly value: string | number | boolean | string[];
}

export interface CustomReportGrouping {
  readonly group_by: string | null;
  readonly time_bucket: 'hourly' | 'daily' | 'weekly' | 'monthly' | null;
}

export type DataSourceType =
  | 'events'
  | 'detections'
  | 'posture'
  | 'copilot'
  | 'workflows'
  | 'users';

export type VisualizationType = 'table' | 'table_chart' | 'chart';

export interface CustomReportCreate {
  name: string;
  description?: string;
  data_sources: DataSourceType[];
  columns: CustomReportColumnDef[];
  filters: CustomReportFilterDef[];
  grouping: CustomReportGrouping;
  visualization: VisualizationType;
}

export interface CustomReport {
  readonly id: number;
  readonly name: string;
  readonly description: string | null;
  readonly owner_login: string;
  readonly data_sources: DataSourceType[];
  readonly columns: CustomReportColumnDef[];
  readonly filters: CustomReportFilterDef[];
  readonly grouping: CustomReportGrouping;
  readonly visualization: VisualizationType;
  readonly is_shared: boolean;
  readonly shared_with: readonly string[];
  readonly last_run_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ReportRunParams {
  window_days?: number;
  start_date?: string;
  end_date?: string;
  org?: string;
  granularity?: ReportGranularity;
}

export interface ReportRunResult {
  readonly report_id: number;
  readonly report_name: string;
  readonly data_sources: DataSourceType[];
  readonly generated_at: string;
  readonly window_days: number;
  readonly org: string | null;
  readonly data: readonly Record<string, unknown>[];
  readonly row_count: number;
}

export interface ShareReportRequest {
  logins: string[];
}

export type ReportTab = 'templates' | 'my-reports' | 'shared' | 'recent';

export interface ReportTemplate {
  readonly id: string;
  readonly type: string;
  readonly title: string;
  readonly description: string;
  readonly category: string;
  readonly data_source: string;
  readonly tags: readonly string[];
}
