/** Types for the Compliance Center. */

export type ControlStatus = 'pass' | 'fail' | 'partial' | 'not_assessed';
export type CheckScope = 'org' | 'repo';
export type CheckStatus = 'pass' | 'fail';

export interface FrameworkScore {
  readonly name: string;
  readonly display_name: string;
  readonly score: number;
  readonly controls_passing: number;
  readonly controls_total: number;
  readonly last_generated: string | null;
}

export interface ComplianceSummary {
  readonly overall_score: number;
  readonly frameworks_tracked: number;
  readonly controls_passing: number;
  readonly controls_total: number;
  readonly critical_gaps: number;
  readonly last_assessment_date: string | null;
  readonly frameworks: readonly FrameworkScore[];
}

export interface ControlItem {
  readonly control_id: string;
  readonly title: string;
  readonly description: string;
  readonly status: ControlStatus;
  readonly evidence_summary: string;
  readonly last_checked: string | null;
  readonly category: string;
}

export interface FrameworkDetail {
  readonly name: string;
  readonly display_name: string;
  readonly score: number;
  readonly controls: readonly ControlItem[];
  readonly last_generated: string | null;
}

export interface PolicyCheckResult {
  readonly check_name: string;
  readonly display_name: string;
  readonly status: CheckStatus;
  readonly scope: CheckScope;
  readonly last_checked: string;
  readonly details: string;
}

export interface PolicyCheckResults {
  readonly checks: readonly PolicyCheckResult[];
  readonly last_run: string | null;
  readonly checks_passing: number;
  readonly checks_total: number;
}

export interface DataProcessingActivity {
  readonly activity_name: string;
  readonly purpose: string;
  readonly legal_basis: string;
  readonly data_categories: readonly string[];
  readonly retention_period: string;
  readonly status: string;
}

export interface BreachChecklistItem {
  readonly item: string;
  readonly complete: boolean;
}

export interface GDPRSummary {
  readonly data_processing_activities: readonly DataProcessingActivity[];
  readonly consent_tracking_enabled: boolean;
  readonly dsr_requests_total: number;
  readonly dsr_requests_completed: number;
  readonly dsr_requests_pending: number;
  readonly breach_notification_readiness: readonly BreachChecklistItem[];
  readonly data_retention_compliant: boolean;
  readonly erasure_requests_processed: number;
  readonly last_updated: string | null;
}

export type ComplianceTab = 'overview' | 'soc2' | 'iso27001' | 'nist_csf' | 'gdpr' | 'policy';
