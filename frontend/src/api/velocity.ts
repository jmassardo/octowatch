import { api } from './client';

// ── Types ────────────────────────────────────────────────────────────────────

export interface MetricWithTrend {
  value: number;
  previous_value: number;
  trend_pct: number;
  classification: string;
}

export interface LeadershipSummaryResponse {
  deployment_frequency: MetricWithTrend;
  lead_time: MetricWithTrend;
  change_failure_rate: MetricWithTrend;
  mttr: MetricWithTrend;
  pr_throughput: MetricWithTrend;
  active_contributors: MetricWithTrend;
  period_days: number;
  cached_at: string | null;
}

export interface TeamMetricsItem {
  team: string;
  value: number;
  classification: string;
}

export interface TeamComparisonResponse {
  items: TeamMetricsItem[];
  metric: string;
  period_days: number;
  cached_at: string | null;
}

export interface CadenceDayItem {
  date: string;
  deployments: number;
  merges: number;
  reviews: number;
}

export interface ShippingCadenceResponse {
  items: CadenceDayItem[];
  period_days: number;
  cached_at: string | null;
}

// ── API functions ────────────────────────────────────────────────────────────

export function getLeadershipSummary(params?: {
  period?: number;
}): Promise<LeadershipSummaryResponse> {
  return api.get<LeadershipSummaryResponse>('/velocity/leadership-summary', params);
}

export function getTeamComparison(params?: {
  period?: number;
  metric?: 'deploy_freq' | 'lead_time' | 'cfr' | 'mttr';
}): Promise<TeamComparisonResponse> {
  return api.get<TeamComparisonResponse>('/velocity/team-comparison', params);
}

export function getShippingCadence(params?: { period?: number }): Promise<ShippingCadenceResponse> {
  return api.get<ShippingCadenceResponse>('/velocity/shipping-cadence', params);
}
