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
