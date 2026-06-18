export type AuditLogOutcome = 'success' | 'denied' | 'error' | string;

export interface AuditLogEntry {
  readonly id: number;
  readonly timestamp: string;
  readonly actor: string;
  readonly action: string;
  readonly resource_type: string | null;
  readonly resource_id: string | null;
  readonly details: Record<string, unknown> | null;
  readonly ip_address: string | null;
  readonly user_agent: string | null;
  readonly outcome: AuditLogOutcome;
}

export interface AuditLogListResponse {
  readonly items: readonly AuditLogEntry[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
  readonly has_more: boolean;
}

export interface AuditLogListParams {
  page?: number;
  page_size?: number;
  actor?: string;
  action?: string;
  resource_type?: string;
  outcome?: string;
  start_date?: string;
  end_date?: string;
}
