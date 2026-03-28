export interface RoleDefinition {
  readonly name: string;
  readonly permissions: readonly string[];
}

export interface RoleAssignment {
  readonly id: number;
  readonly github_login: string;
  readonly github_team_slug: string | null;
  readonly role_id: number;
  readonly scope_type: string;
  readonly scope_value: string | null;
  readonly granted_by: string;
  readonly granted_at: string;
  readonly expires_at: string | null;
  readonly active: boolean;
}

export interface RoleAssignmentCreate {
  github_login: string;
  role_name: string;
  scope_type: string;
  scope_value?: string;
  expires_at?: string;
}

export interface IngestionSource {
  readonly id: number;
  readonly source_type: string;
  readonly source_name: string;
  readonly source_region: string | null;
  readonly source_prefix: string;
  readonly last_prefix: string;
  readonly last_event_count: number;
  readonly last_processed_at: string | null;
  readonly status: string;
  readonly error_message: string | null;
  readonly error_count: number;
  readonly poll_interval_sec: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface RetentionPolicy {
  readonly hot_days: number;
  readonly warm_days: number;
  readonly cold_days: number;
}

export interface ActiveSession {
  readonly login: string;
  readonly last_active_at: string | null;
  readonly session_count: number;
  readonly role: string;
  readonly mfa_enabled: boolean;
}
