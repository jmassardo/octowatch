import { api } from './client';

/** A single risk signal for a user. */
export interface RiskSignal {
  action: string;
  label: string;
  category: string;
  count: number;
  weight: number;
  last_seen: string | null;
}

/** Category breakdown for a user's risk. */
export interface CategoryBreakdown {
  category: string;
  label: string;
  count: number;
}

/** A user with their risk assessment. */
export interface RiskyUser {
  user_login: string;
  risk_score: number;
  risk_level: 'high' | 'medium' | 'low' | 'none';
  signals: RiskSignal[];
  category_breakdown: CategoryBreakdown[];
  orgs: string[];
  last_risky_action_at: string | null;
}

/** Top risk category summary. */
export interface TopCategory {
  category: string;
  label: string;
  description: string;
  event_count: number;
}

/** Response from GET /user-behavior/risk-summary. */
export interface RiskSummaryResponse {
  total_users_with_signals: number;
  high_risk_count: number;
  medium_risk_count: number;
  low_risk_count: number;
  anomaly_count: number;
  top_categories: TopCategory[];
  lookback_days: number;
}

/** Response from GET /user-behavior/risky-users. */
export interface RiskyUsersResponse {
  users: RiskyUser[];
  total: number;
  page: number;
  page_size: number;
}

/** An anomalous user record. */
export interface AnomalousUser {
  user_login: string;
  recent_event_count: number;
  baseline_daily_avg: number;
  activity_ratio: number;
  recent_action_types: number;
  baseline_action_types: number;
  recent_ips: number;
  baseline_ips: number;
  deviation_reasons: string[];
}

/** Response from GET /user-behavior/anomalies. */
export interface AnomaliesResponse {
  anomalies: AnomalousUser[];
  lookback_days: number;
}

/** A user with permission drift analysis. */
export interface PermissionDriftUser {
  user_login: string;
  total_events: number;
  admin_events: number;
  dev_events: number;
  admin_pct: number;
  last_active: string | null;
  status: 'review_recommended' | 'low_activity' | 'normal';
  reason: string;
}

/** Response from GET /user-behavior/permission-drift. */
export interface PermissionDriftResponse {
  users: PermissionDriftUser[];
  lookback_days: number;
}

/** Fetch the aggregate risk summary. */
export function getRiskSummary(lookbackDays?: number): Promise<RiskSummaryResponse> {
  const params: Record<string, number> = {};
  if (lookbackDays !== undefined) params.lookback_days = lookbackDays;
  return api.get<RiskSummaryResponse>('/user-behavior/risk-summary', params);
}

/** Fetch paginated risky users with optional filters. */
export function getRiskyUsers(params?: {
  lookback_days?: number;
  risk_level?: string;
  page?: number;
  page_size?: number;
}): Promise<RiskyUsersResponse> {
  const queryParams: Record<string, string | number> = {};
  if (params?.lookback_days) queryParams.lookback_days = params.lookback_days;
  if (params?.risk_level) queryParams.risk_level = params.risk_level;
  if (params?.page) queryParams.page = params.page;
  if (params?.page_size) queryParams.page_size = params.page_size;
  return api.get<RiskyUsersResponse>('/user-behavior/risky-users', queryParams);
}

/** Fetch anomalous users deviating from their baseline. */
export function getAnomalies(params?: {
  lookback_days?: number;
  threshold?: number;
}): Promise<AnomaliesResponse> {
  const queryParams: Record<string, number> = {};
  if (params?.lookback_days) queryParams.lookback_days = params.lookback_days;
  if (params?.threshold) queryParams.threshold = params.threshold;
  return api.get<AnomaliesResponse>('/user-behavior/anomalies', queryParams);
}

/** Fetch permission drift analysis. */
export function getPermissionDrift(lookbackDays?: number): Promise<PermissionDriftResponse> {
  const params: Record<string, number> = {};
  if (lookbackDays !== undefined) params.lookback_days = lookbackDays;
  return api.get<PermissionDriftResponse>('/user-behavior/permission-drift', params);
}
