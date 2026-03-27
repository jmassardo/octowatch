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
  readonly default_severity: string;
  readonly default_confidence: string;
  readonly logic_type: string;
  readonly logic_config: Record<string, unknown>;
  readonly enabled: boolean;
  readonly status: string;
  readonly version: number;
  readonly git_commit_sha: string | null;
  readonly created_by: string;
  readonly updated_by: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface RuleListResponse {
  readonly items: readonly RuleResponse[];
  readonly total: number;
  readonly limit: number;
  readonly offset: number;
}

export interface RuleCreate {
  name: string;
  slug: string;
  description?: string;
  category: RuleCategory;
  default_severity: string;
  default_confidence: string;
  logic_type: string;
  logic_config: Record<string, unknown>;
  enabled?: boolean;
  status?: string;
  change_summary?: string;
}
