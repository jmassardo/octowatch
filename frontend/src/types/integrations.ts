export interface TicketingConfigResponse {
  readonly id: number;
  readonly provider: 'jira' | 'github_issues';
  readonly display_name: string;
  readonly target: string;
  readonly project_key: string | null;
  readonly default_issue_type: string;
  readonly auto_create: boolean;
  readonly auto_create_severities: readonly string[];
  readonly enabled: boolean;
  readonly created_by: string;
  readonly created_at: string;
}

export interface TicketingConfigCreate {
  provider: 'jira' | 'github_issues';
  display_name: string;
  target: string;
  project_key?: string;
  default_issue_type?: string;
  auto_create?: boolean;
  auto_create_severities?: string[];
  credential_env_var: string;
  enabled?: boolean;
}

export interface NotificationConfigResponse {
  readonly id: number;
  readonly channel_type: 'slack' | 'email' | 'webhook' | 'pagerduty';
  readonly display_name: string;
  readonly target: string;
  readonly notify_severities: readonly string[];
  readonly cooldown_seconds: number;
  readonly enabled: boolean;
  readonly created_by: string;
  readonly created_at: string;
}

export interface NotificationConfigCreate {
  channel_type: 'slack' | 'email' | 'webhook' | 'pagerduty';
  display_name: string;
  target: string;
  credential_env_var?: string;
  notify_severities?: string[];
  cooldown_seconds?: number;
  enabled?: boolean;
}

export interface IdpEnrichmentResponse {
  readonly github_login: string;
  readonly idp_provider: string;
  readonly idp_user_id: string | null;
  readonly email: string | null;
  readonly display_name: string | null;
  readonly department: string | null;
  readonly title: string | null;
  readonly employment_status: string | null;
}

// ── SIEM Export Types ───────────────────────────────────────────────────────

export type SiemExportType = 'syslog' | 'splunk_hec' | 'webhook';

export interface SiemExportConfigCreate {
  export_type: SiemExportType;
  display_name: string;
  // Syslog
  syslog_host?: string;
  syslog_port?: number;
  syslog_protocol?: 'tcp' | 'udp' | 'tls';
  syslog_format?: 'cef' | 'leef';
  // Splunk HEC
  splunk_hec_url?: string;
  splunk_hec_token_env_var?: string;
  splunk_sourcetype?: string;
  splunk_index?: string;
  // Webhook
  webhook_url?: string;
  webhook_secret_env_var?: string;
  webhook_headers?: Record<string, string>;
  // Common
  enabled?: boolean;
  export_events?: boolean;
  export_detections?: boolean;
}

export interface SiemExportConfigResponse {
  readonly id: number;
  readonly export_type: SiemExportType;
  readonly display_name: string;
  readonly syslog_host: string | null;
  readonly syslog_port: number | null;
  readonly syslog_protocol: string | null;
  readonly syslog_format: string | null;
  readonly splunk_hec_url: string | null;
  readonly splunk_hec_token_env_var: string | null;
  readonly splunk_sourcetype: string | null;
  readonly splunk_index: string | null;
  readonly webhook_url: string | null;
  readonly webhook_secret_env_var: string | null;
  readonly webhook_headers: Record<string, string> | null;
  readonly enabled: boolean;
  readonly export_events: boolean;
  readonly export_detections: boolean;
  readonly created_by: string;
  readonly created_at: string;
}
