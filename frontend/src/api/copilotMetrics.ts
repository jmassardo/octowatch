import { api } from './client';

export interface CopilotOverview {
  acceptance_rate_days: string[];
  acceptance_rate_values: number[];
  acceptance_threshold: number;
  languages: Array<{ lang: string; pct: number; color: string }>;
  total_active_users: number;
  total_engaged_users: number;
  error?: string;
  message?: string;
}

export interface AdoptionTier {
  id: string;
  label: string;
  count: number;
  color: string;
  desc: string;
}

export interface PowerUser {
  user: string;
  days_active: number;
  features_used: number;
  last_activity?: string;
  editor?: string;
}

export interface MinimalUser {
  user: string;
  days_active: number;
  last_feature: string;
  last_activity?: string;
}

export interface CopilotAdoption {
  tiers: AdoptionTier[];
  total_adoption: number;
  power_users: PowerUser[];
  regular_users: PowerUser[];
  feature_adoption: Array<{
    feature: string;
    active_users: number;
    total_seats: number;
    pct: number;
    trend_7d: number;
    color: string;
  }>;
  minimal_users: MinimalUser[];
  inactive_users: MinimalUser[];
  error?: string;
  message?: string;
}

export interface CopilotModels {
  models: Array<{ model: string; pct: number; color: string }>;
  features: Array<{ feature: string; count: number; color: string }>;
  editors: Array<{ name: string; count: number; pct: number }>;
  error?: string;
  message?: string;
}

export interface CopilotAnomaly {
  id: number;
  severity: 'high' | 'medium' | 'low';
  title: string;
  description: string;
  timestamp: string;
  team: string;
  affected_count?: number;
}

export interface CopilotAnomalies {
  anomalies: CopilotAnomaly[];
  error?: string;
  message?: string;
}

export interface CopilotTeam {
  team_slug: string;
  team_name: string;
  org: string;
  total_members: number;
  active_users: number;
  inactive_users: number;
  adoption_pct: number;
  avg_days_since_activity: number;
  at_risk: boolean;
}

export interface CopilotTeams {
  teams: CopilotTeam[];
  total_teams: number;
  at_risk_count: number;
  error?: string;
  message?: string;
}

export interface CopilotBlocker {
  id: number;
  category: 'no_seat' | 'inactive_seat' | 'policy_restricted' | 'content_excluded';
  title: string;
  description: string;
  affected_users: string[];
  count: number;
  severity: 'high' | 'medium' | 'low';
  recommendation: string;
  policies?: Array<{ name: string; type: string }>;
}

export interface CopilotBlockers {
  blockers: CopilotBlocker[];
  quick_wins: Array<{
    action: string;
    impact: string;
    effort: string;
    description: string;
  }>;
  summary: {
    total_blockers: number;
    no_seat_count: number;
    inactive_count: number;
    policy_restricted_count: number;
  };
  error?: string;
  message?: string;
}

export interface PolicyChange {
  id: number;
  action: string;
  actor: string;
  timestamp: string;
  org: string;
  old_value: string;
  new_value: string;
  description: string;
}

export interface CopilotPolicyChanges {
  timeline: PolicyChange[];
  total_changes: number;
  error?: string;
  message?: string;
}

export interface CopilotROISummary {
  total_seats: number;
  active_seats: number;
  inactive_seats: number;
  utilization_pct: number;
  total_monthly_cost: number;
  wasted_monthly: number;
  annual_waste: number;
  cost_per_active_user: number;
}

export interface CopilotValueStreams {
  completion_value: number;
  chat_savings: number;
  pr_summary_savings: number;
  total_value: number;
}

export interface CopilotROIMetrics {
  total_roi: number;
  roi_ratio: number;
  breakeven_additional_users: number | null;
}

export interface CopilotGhostMember {
  user: string;
  last_activity: string;
  days_inactive: number;
  plan_type: string;
}

export interface CopilotLicenseOptimization {
  inactive_savings_monthly: number;
  inactive_savings_annual: number;
  ghost_member_count: number;
}

export interface CopilotGrowthForecast {
  current_active: number;
  projected_30d: number;
  projected_90d: number;
  monthly_growth_pct: number;
  weeks_to_capacity: number | null;
}

export interface CopilotROI {
  summary: CopilotROISummary;
  value_streams: CopilotValueStreams;
  roi: CopilotROIMetrics;
  ghost_members: CopilotGhostMember[];
  license_optimization: CopilotLicenseOptimization;
  growth_forecast: CopilotGrowthForecast | Record<string, never>;
  tier_breakdown: Record<string, number>;
  plan_breakdown: Record<string, number>;
  cost_trend: Array<{
    date: string;
    active_users: number;
    acceptance_rate: number;
    daily_cost_per_active_user: number;
  }>;
  recommendations: Array<{
    type: string;
    title: string;
    impact: string;
    priority: 'high' | 'medium' | 'low';
    description: string;
  }>;
  error?: string;
  message?: string;
}

export function getCopilotOverview(): Promise<CopilotOverview> {
  return api.get<CopilotOverview>('/copilot/overview');
}

export function getCopilotAdoption(): Promise<CopilotAdoption> {
  return api.get<CopilotAdoption>('/copilot/adoption');
}

export function getCopilotModels(): Promise<CopilotModels> {
  return api.get<CopilotModels>('/copilot/models');
}

export function getCopilotAnomalies(): Promise<CopilotAnomalies> {
  return api.get<CopilotAnomalies>('/copilot/anomalies');
}

export function getCopilotTeams(): Promise<CopilotTeams> {
  return api.get<CopilotTeams>('/copilot/teams');
}

export function getCopilotBlockers(): Promise<CopilotBlockers> {
  return api.get<CopilotBlockers>('/copilot/blockers');
}

export function getCopilotPolicyChanges(): Promise<CopilotPolicyChanges> {
  return api.get<CopilotPolicyChanges>('/copilot/policy-changes');
}

export function getCopilotROI(): Promise<CopilotROI> {
  return api.get<CopilotROI>('/copilot/roi');
}

// ── Billing / UBB types ──────────────────────────────────────────────────────

export interface CopilotBillingOverview {
  pool_total: number;
  total_consumed: number;
  projected_eom: number;
  pool_remaining: number;
  utilization_pct: number;
  unique_users: number;
  daily_rate: number;
  period_start: string;
  days_reported: number;
  error?: string;
  message?: string;
}

export interface CopilotUserBudget {
  login: string;
  org_slug: string;
  consumed: number;
  budget: number | null;
  utilization_pct: number;
  status: 'ok' | 'warning' | 'near' | 'over' | 'blocked';
  is_blocked: boolean;
}

export interface CopilotUserBudgets {
  users: CopilotUserBudget[];
  total_users: number;
  buckets: Record<string, number>;
  error?: string;
  message?: string;
}

export interface CopilotBillingTrendDay {
  date: string;
  total: number;
  completions: number;
  chat: number;
  pr: number;
  other: number;
  active_users: number;
}

export interface CopilotBillingTrends {
  trends: CopilotBillingTrendDay[];
  period_days: number;
  error?: string;
  message?: string;
}

export function getCopilotBillingOverview(): Promise<CopilotBillingOverview> {
  return api.get<CopilotBillingOverview>('/copilot/billing-overview');
}

export function getCopilotUserBudgets(): Promise<CopilotUserBudgets> {
  return api.get<CopilotUserBudgets>('/copilot/user-budgets');
}

export function getCopilotBillingTrends(): Promise<CopilotBillingTrends> {
  return api.get<CopilotBillingTrends>('/copilot/billing-trends');
}
