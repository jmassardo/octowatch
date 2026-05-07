import { api } from './client';

/** Per-repo bus factor analysis result. */
export interface BusFactorRepo {
  repo: string;
  bus_factor: number;
  contributor_count: number;
  top_contributors: { login: string; pct: number }[];
  risk_level: 'critical' | 'high' | 'medium' | 'low';
}

export interface BusFactorResponse {
  repos: BusFactorRepo[];
  lookback_days: number;
}

/** Developer engagement tier info. */
export interface DeveloperTierInfo {
  login: string;
  last_active: string | null;
  event_count: number;
}

/** Monthly engagement trend data point. */
export interface EngagementTrendPoint {
  month: string;
  active_developers: number;
}

export interface EngagementResponse {
  tiers: {
    active: DeveloperTierInfo[];
    regular: DeveloperTierInfo[];
    occasional: DeveloperTierInfo[];
    dormant: DeveloperTierInfo[];
  };
  counts: {
    active: number;
    regular: number;
    occasional: number;
    dormant: number;
  };
  total_developers: number;
  active_pct: number;
  trend: EngagementTrendPoint[];
  lookback_days: number;
}

/** A detected policy violation. */
export interface PolicyViolation {
  type: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  description: string;
  actor: string | null;
  repo: string | null;
  org: string | null;
  timestamp: string | null;
  action: string;
}

export interface PolicyViolationsResponse {
  violations: PolicyViolation[];
  current_count: number;
  previous_count: number;
  trend_direction: 'up' | 'down' | 'neutral';
  lookback_days: number;
}

/** Knowledge concentration risk for a repo. */
export interface ConcentrationRisk {
  repo: string;
  top_actor: string;
  concentration_pct: number;
  total_events: number;
  risk_level: 'high' | 'medium' | 'low';
  recommendation: string;
}

export interface KnowledgeConcentrationResponse {
  risks: ConcentrationRisk[];
  lookback_days: number;
}

/** Combined summary for the MetricCards strip. */
export interface TeamHealthSummary {
  bus_factor_score: number;
  active_contributors_pct: number;
  total_developers: number;
  dormant_developers: number;
  policy_violations_count: number;
  policy_violations_trend: 'up' | 'down' | 'neutral';
  knowledge_concentration_risk: 'high' | 'medium' | 'low';
  engagement_counts: {
    active: number;
    regular: number;
    occasional: number;
    dormant: number;
  };
}

export function getTeamHealthSummary(): Promise<TeamHealthSummary> {
  return api.get<TeamHealthSummary>('/team-health/summary');
}

export function getBusFactorAnalysis(lookbackDays?: number): Promise<BusFactorResponse> {
  const params: Record<string, number> = {};
  if (lookbackDays !== undefined) params.lookback_days = lookbackDays;
  return api.get<BusFactorResponse>('/team-health/bus-factor', params);
}

export function getEngagement(lookbackDays?: number): Promise<EngagementResponse> {
  const params: Record<string, number> = {};
  if (lookbackDays !== undefined) params.lookback_days = lookbackDays;
  return api.get<EngagementResponse>('/team-health/engagement', params);
}

export function getPolicyViolations(lookbackDays?: number): Promise<PolicyViolationsResponse> {
  const params: Record<string, number> = {};
  if (lookbackDays !== undefined) params.lookback_days = lookbackDays;
  return api.get<PolicyViolationsResponse>('/team-health/policy-violations', params);
}

export function getKnowledgeConcentration(
  lookbackDays?: number,
): Promise<KnowledgeConcentrationResponse> {
  const params: Record<string, number> = {};
  if (lookbackDays !== undefined) params.lookback_days = lookbackDays;
  return api.get<KnowledgeConcentrationResponse>('/team-health/knowledge-concentration', params);
}
