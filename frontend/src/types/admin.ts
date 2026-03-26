export interface RoleDefinition {
  readonly name: string;
  readonly permissions: readonly string[];
}

export interface RoleAssignment {
  readonly id: number;
  readonly github_login: string;
  readonly role: string;
  readonly assigned_by: string;
  readonly assigned_at: string;
}

export interface RoleAssignmentCreate {
  github_login: string;
  role: string;
}

export interface IngestionSource {
  readonly id: number;
  readonly source_type: string;
  readonly display_name: string;
  readonly enabled: boolean;
  readonly created_at: string;
}

export interface RetentionPolicy {
  readonly hot_days: number;
  readonly warm_days: number;
  readonly cold_days: number;
}

export interface TopActor {
  readonly actor: string;
  readonly event_count: number;
  readonly action_types: readonly string[];
}
