export interface QueryRunRequest {
  sql: string;
  org?: string;
  format?: 'json' | 'csv';
}

export interface QueryRunResponse {
  readonly columns: readonly string[];
  readonly rows: readonly (readonly unknown[])[];
  readonly row_count: number;
  readonly truncated: boolean;
  readonly execution_ms: number;
  readonly query_id: string;
}

export interface QueryTemplate {
  readonly id: number;
  readonly name: string;
  readonly description: string | null;
  readonly sql: string;
  readonly created_by: string;
  readonly created_at: string;
}

export interface QueryTemplateCreate {
  name: string;
  description?: string;
  sql: string;
}

// ── Saved Queries ────────────────────────────────────────────────────────────

export interface SavedQuery {
  readonly id: number;
  readonly name: string;
  readonly description: string | null;
  readonly sql_text: string;
  readonly owner_login: string;
  readonly is_shared: boolean;
  readonly shared_with: readonly string[] | null;
  readonly tags: readonly string[] | null;
  readonly schedule_cron: string | null;
  readonly schedule_enabled: boolean;
  readonly last_run_at: string | null;
  readonly created_at: string;
  readonly updated_at: string | null;
}

export interface SavedQueryCreate {
  name: string;
  description?: string;
  sql_text: string;
  tags?: string[];
}

export interface SavedQueryUpdate {
  name?: string;
  description?: string;
  sql_text?: string;
  tags?: string[];
}

// ── Schema ──────────────────────────────────────────────────────────────────

export interface SchemaColumn {
  readonly name: string;
  readonly type: string;
}

export interface SchemaTable {
  readonly table: string;
  readonly columns: readonly SchemaColumn[];
}
