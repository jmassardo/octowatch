import { api } from './client';

export interface CopilotOverview {
  acceptance_rate_days: string[];
  acceptance_rate_values: number[];
  acceptance_threshold: number;
  languages: Array<{ lang: string; pct: number; color: string }>;
  total_active_users: number;
  total_engaged_users: number;
  total_provisioned_seats: number;
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
  credits_consumed?: number;
}

export interface MinimalUser {
  user: string;
  days_active: number;
  last_feature: string;
  last_activity?: string;
  credits_consumed?: number;
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
  time_series?: {
    dates: string[];
    models: Record<string, number[]>;
    features: Record<string, number[]>;
  };
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

export function getCopilotOverview(org?: string): Promise<CopilotOverview> {
  return api.get<CopilotOverview>('/copilot/overview', { org });
}

export function getCopilotAdoption(org?: string): Promise<CopilotAdoption> {
  return api.get<CopilotAdoption>('/copilot/adoption', { org });
}

export function getCopilotModels(org?: string): Promise<CopilotModels> {
  return api.get<CopilotModels>('/copilot/models', { org });
}

export interface CopilotModelUser {
  login: string;
  total_credits: number;
  completions_credits: number;
  chat_credits: number;
  pr_credits: number;
  other_credits: number;
  days_active: number;
  last_active: string | null;
}

export interface CopilotModelUsers {
  users: CopilotModelUser[];
  total_users: number;
  error?: string;
  message?: string;
}

export function getCopilotModelUsers(org?: string): Promise<CopilotModelUsers> {
  return api.get<CopilotModelUsers>('/copilot/model-users', { org });
}

export function getCopilotAnomalies(org?: string): Promise<CopilotAnomalies> {
  return api.get<CopilotAnomalies>('/copilot/anomalies', { org });
}

export function getCopilotTeams(org?: string): Promise<CopilotTeams> {
  return api.get<CopilotTeams>('/copilot/teams', { org });
}

export function getCopilotBlockers(org?: string): Promise<CopilotBlockers> {
  return api.get<CopilotBlockers>('/copilot/blockers', { org });
}

export function getCopilotPolicyChanges(org?: string): Promise<CopilotPolicyChanges> {
  return api.get<CopilotPolicyChanges>('/copilot/policy-changes', { org });
}

export function getCopilotROI(org?: string): Promise<CopilotROI> {
  return api.get<CopilotROI>('/copilot/roi', { org });
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

export function getCopilotBillingOverview(org?: string): Promise<CopilotBillingOverview> {
  return api.get<CopilotBillingOverview>('/copilot/billing-overview', { org });
}

export function getCopilotUserBudgets(org?: string): Promise<CopilotUserBudgets> {
  return api.get<CopilotUserBudgets>('/copilot/user-budgets', { org });
}

export function getCopilotBillingTrends(org?: string): Promise<CopilotBillingTrends> {
  return api.get<CopilotBillingTrends>('/copilot/billing-trends', { org });
}

// ── Activity metrics types ───────────────────────────────────────────────────

export interface CopilotActivity {
  dates: string[];
  ide_dau: number[];
  ide_wau: number[];
  completions_count: number[];
  completions_accepted: number[];
  acceptance_rate_pct: number[];
  chat_requests_per_user: number[];
  requests_per_mode: {
    dates: string[];
    completions: number[];
    chat: number[];
    dotcom_chat: number[];
    pr: number[];
  };
  error?: string;
  message?: string;
}

export function getCopilotActivity(org?: string): Promise<CopilotActivity> {
  return api.get<CopilotActivity>('/copilot/activity', { org });
}

// ── Chat metrics types ───────────────────────────────────────────────────────

export interface CopilotChatMetrics {
  dates: string[];
  total_interactions: number[];
  code_actions: number[];
  active_chat_users: number[];
  action_rate_pct: number[];
  error?: string;
  message?: string;
}

export function getCopilotChatMetrics(org?: string): Promise<CopilotChatMetrics> {
  return api.get<CopilotChatMetrics>('/copilot/chat-metrics', { org });
}

// ── Language breakdown types ─────────────────────────────────────────────────

export interface CopilotLanguageBreakdown {
  dates: string[];
  language_per_day: Record<string, number[]>;
  language_distribution: Array<{ name: string; value: number; color?: string }>;
  model_per_language: {
    labels: string[];
    series: Array<{ name: string; data: number[] }>;
  };
  acceptance_by_editor: Array<{ editor: string; rate: number }>;
  top_by_generations: Array<{ language: string; count: number }>;
  top_by_lines: Array<{ language: string; lines: number }>;
  error?: string;
  message?: string;
}

export function getCopilotLanguageBreakdown(org?: string): Promise<CopilotLanguageBreakdown> {
  return api.get<CopilotLanguageBreakdown>('/copilot/language-breakdown', { org });
}

// ── PR metrics types ─────────────────────────────────────────────────────────

export interface CopilotPRMetrics {
  dates: string[];
  pr_activity: number[];
  pr_contributions: number[];
  review_suggestions: number[];
  error?: string;
  message?: string;
}

export function getCopilotPRMetrics(org?: string): Promise<CopilotPRMetrics> {
  return api.get<CopilotPRMetrics>('/copilot/pr-metrics', { org });
}

// ── Agent activity types ─────────────────────────────────────────────────────

export interface CopilotAgentActivity {
  dates: string[];
  daily_lines_added: number[];
  daily_lines_accepted: number[];
  lines_by_mode: Record<string, number[]>;
  lines_by_model: Array<{ model: string; lines_added: number; lines_accepted: number }>;
  lines_by_language: Array<{ language: string; lines_added: number; lines_accepted: number }>;
  error?: string;
  message?: string;
}

export function getCopilotAgentActivity(org?: string): Promise<CopilotAgentActivity> {
  return api.get<CopilotAgentActivity>('/copilot/agent-activity', { org });
}
