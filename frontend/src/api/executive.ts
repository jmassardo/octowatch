import { api } from './client';

/** Executive summary response from the backend. */
export interface ExecutiveSummary {
  readonly posture_score: number;
  readonly posture_score_previous: number;
  readonly score_delta: number;
  readonly score_delta_pct: number;
  readonly detection_trend: Record<string, number>;
  readonly severity_breakdown: Record<string, number>;
  readonly compliance_summary: readonly ComplianceStatusItem[];
  readonly top_risks: readonly TopRisk[];
  readonly month_over_month: MonthOverMonth;
}

export interface ComplianceStatusItem {
  readonly framework: string;
  readonly controls_assessed: number;
  readonly controls_with_evidence: number;
  readonly compliance_pct: number;
}

export interface TopRisk {
  readonly title: string;
  readonly severity: string;
  readonly category: string;
  readonly count: number;
  readonly actor: string | null;
}

export interface MonthOverMonth {
  readonly current_detections: number;
  readonly previous_detections: number;
  readonly current_events: number;
  readonly previous_events: number;
  readonly detection_change_pct: number;
  readonly event_change_pct: number;
}

export function getExecutiveSummary(
  period: 7 | 30 | 90 = 30,
): Promise<ExecutiveSummary> {
  return api.get<ExecutiveSummary>('/reports/executive-summary', {
    period,
  });
}

export function exportExecutivePdf(period: 7 | 30 | 90 = 30): void {
  window.open(
    `/api/v1/reports/executive-summary/pdf?period=${period}`,
    '_blank',
  );
}

/** Detection investigation timeline. */
export interface TimelineEvent {
  readonly id: number;
  readonly created_at: string;
  readonly action: string;
  readonly actor: string | null;
  readonly org: string | null;
  readonly repo: string | null;
  readonly source_ip: string | null;
  readonly geo_country_code: string | null;
  readonly geo_city: string | null;
  readonly geo_latitude: number | null;
  readonly geo_longitude: number | null;
  readonly data: Record<string, unknown>;
  readonly is_sequence_step: boolean;
  readonly sequence_index: number | null;
}

export interface DetectionTimeline {
  readonly detection_id: number;
  readonly detection_title: string;
  readonly detection_severity: string;
  readonly detection_category: string | null;
  readonly events: readonly TimelineEvent[];
  readonly sequence_steps: readonly string[];
  readonly context_data: Record<string, unknown>;
}

export function getDetectionTimeline(
  detectionId: number,
): Promise<DetectionTimeline> {
  return api.get<DetectionTimeline>(
    `/detections/${detectionId}/timeline`,
  );
}
