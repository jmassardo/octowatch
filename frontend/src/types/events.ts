export interface EventResponse {
  readonly id: number;
  readonly document_id: string;
  readonly created_at: string;
  readonly ingested_at: string;
  readonly action: string;
  readonly namespace: string;
  readonly actor: string | null;
  readonly actor_id: number | null;
  readonly actor_is_bot: boolean;
  readonly org: string | null;
  readonly org_id: number | null;
  readonly repo: string | null;
  readonly repo_id: number | null;
  readonly business: string | null;
  readonly source_ip: string | null;
  readonly user_agent: string | null;
  readonly geo_country_code: string | null;
  readonly geo_city: string | null;
  readonly geo_is_proxy: boolean | null;
  readonly data: Record<string, unknown>;
  readonly ingestion_source: string;
  readonly source_file_path: string;
}

export interface EventListResponse {
  readonly items: readonly EventResponse[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
  readonly has_next: boolean;
}

export interface EventListParams {
  org?: string;
  repo?: string;
  actor?: string;
  action?: string;
  namespace?: string;
  source_ip?: string;
  since?: string;
  until?: string;
  actor_is_bot?: boolean;
  geo_country_code?: string;
  sort?: 'created_at_desc' | 'created_at_asc';
  page?: number;
  page_size?: number;
}
