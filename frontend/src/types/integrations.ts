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
  readonly channel_type: 'slack' | 'email';
  readonly display_name: string;
  readonly target: string;
  readonly notify_severities: readonly string[];
  readonly cooldown_seconds: number;
  readonly enabled: boolean;
  readonly created_by: string;
  readonly created_at: string;
}

export interface NotificationConfigCreate {
  channel_type: 'slack' | 'email';
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
