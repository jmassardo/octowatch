import { api } from './client';

// ── Types ────────────────────────────────────────────────────────────────────

export interface FeatureSummary {
  feature_area: string;
  unique_actors: number;
  active_days: number;
  total_actions_minutes: number;
  total_actions_runs: number;
  total_copilot_suggestions: number;
  total_copilot_acceptances: number;
  total_copilot_credits: number;
  total_git_clones: number;
  total_git_pushes: number;
  total_packages_published: number;
}

export interface UsageSummaryResponse {
  features: FeatureSummary[];
  period_days: number;
}

export interface Consumer {
  actor_login: string;
  org_slug: string;
  total_actions_minutes: number;
  total_actions_runs: number;
  total_copilot_suggestions: number;
  total_copilot_acceptances: number;
  total_copilot_credits: number;
  total_git_clones: number;
  total_git_pushes: number;
  active_days: number;
}

export interface TopConsumersResponse {
  consumers: Consumer[];
  feature_area: string;
  period_days: number;
}

export interface TrendPoint {
  date: string;
  feature_area: string;
  unique_actors: number;
  actions_minutes: number;
  copilot_credits: number;
  git_clones: number;
  git_pushes: number;
}

export interface TrendsResponse {
  trends: TrendPoint[];
  period_days: number;
}

export interface Anomaly {
  id: number;
  triggered_at: string;
  severity: string;
  confidence_score: number;
  actor: string;
  org: string;
  rule_name: string;
  rule_slug: string;
  category: string;
}

export interface AnomaliesResponse {
  anomalies: Anomaly[];
  period_days: number;
}

export interface UserFact {
  feature_area: string;
  date: string;
  actions_minutes: number | null;
  actions_runs: number | null;
  copilot_suggestions: number | null;
  copilot_acceptances: number | null;
  copilot_credits: number | null;
  git_clones: number | null;
  git_pushes: number | null;
  packages_published: number | null;
  storage_bytes: number | null;
}

export interface UserUsageResponse {
  login: string;
  facts: UserFact[];
  period_days: number;
}

// ── API functions ────────────────────────────────────────────────────────────

export function fetchUsageSummary(params?: {
  org?: string;
  days?: number;
}): Promise<UsageSummaryResponse> {
  return api.get<UsageSummaryResponse>('/platform-usage/summary', params);
}

export function fetchTopConsumers(params?: {
  feature_area?: string;
  org?: string;
  days?: number;
  limit?: number;
}): Promise<TopConsumersResponse> {
  return api.get<TopConsumersResponse>('/platform-usage/top-consumers', params);
}

export function fetchUsageTrends(params?: {
  org?: string;
  feature_area?: string;
  days?: number;
}): Promise<TrendsResponse> {
  return api.get<TrendsResponse>('/platform-usage/trends', params);
}

export function fetchAnomalies(params?: {
  org?: string;
  days?: number;
  limit?: number;
}): Promise<AnomaliesResponse> {
  return api.get<AnomaliesResponse>('/platform-usage/anomalies', params);
}

export function fetchUserUsage(
  login: string,
  params?: { org?: string; days?: number },
): Promise<UserUsageResponse> {
  return api.get<UserUsageResponse>(`/platform-usage/user/${login}`, params);
}
