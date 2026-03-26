export type DetectionStatus = 'investigating' | 'resolved' | 'false_positive';
export type DetectionSeverity = 'critical' | 'high' | 'medium' | 'low';

export interface TicketSummary {
  readonly id: number;
  readonly external_id: string;
  readonly external_url: string;
  readonly provider: string;
  readonly external_status: string | null;
}

export interface DetectionResponse {
  readonly id: number;
  readonly rule_id: number;
  readonly rule_name: string | null;
  readonly rule_version: number;
  readonly severity: DetectionSeverity;
  readonly confidence: string;
  readonly confidence_score: number;
  readonly status: DetectionStatus;
  readonly title: string;
  readonly description: string;
  readonly actor: string | null;
  readonly org: string | null;
  readonly repo: string | null;
  readonly source_ip: string | null;
  readonly window_start: string | null;
  readonly window_end: string | null;
  readonly event_ids: readonly number[];
  readonly context_data: Record<string, unknown>;
  readonly triggered_at: string;
  readonly assigned_to: string | null;
  readonly resolved_at: string | null;
  readonly resolution_note: string | null;
  readonly tickets: readonly TicketSummary[];
}

export interface DetectionListResponse {
  readonly items: readonly DetectionResponse[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
  readonly has_next: boolean;
}

export interface UpdateDetectionStatusRequest {
  status: DetectionStatus;
  resolution_note?: string;
}

export interface AssignDetectionRequest {
  assigned_to: string;
}

export type RuleCategory =
  | 'exfiltration'
  | 'account_compromise'
  | 'privilege_escalation'
  | 'secret_leakage'
  | 'supply_chain'
  | 'branch_protection_bypass'
  | 'pat_abuse'
  | 'impossible_travel'
  | 'off_hours_anomaly'
  | 'other';

export interface RuleResponse {
  readonly id: number;
  readonly name: string;
  readonly slug: string;
  readonly description: string | null;
  readonly category: RuleCategory;
  readonly severity: DetectionSeverity;
  readonly enabled: boolean;
  readonly version: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface RuleCreate {
  name: string;
  slug: string;
  description?: string;
  category: RuleCategory;
  severity: DetectionSeverity;
  enabled?: boolean;
}
