import { api } from './client';

export interface HealthSummary {
  stale_repos: number;
  pat_no_expiry: number;
  pat_stale: number;
  bypass_offenders: number;
  ext_collab_total: number;
  ext_collab_elevated: number;
}

export interface PatToken {
  github_login: string;
  token_name: string | null;
  token_id: string | null;
  token_type: string | null;
  created_at: string;
  age_days: number;
  signal_type: 'no_expiry' | 'expired' | 'stale_90d' | 'ok';
}

export interface PatHealthResponse {
  summary: { no_expiry_count: number; expired_count: number; stale_90d_count: number };
  tokens: PatToken[];
  dormant: PatToken[];
}

export interface BypassOffender {
  actor: string;
  total_bypasses: number;
  push_protection_bypasses: number;
  branch_protection_overrides: number;
  first_bypass_at: string;
  last_bypass_at: string;
  active_days: number;
}

export interface StaleRepo {
  org: string;
  repo: string;
  last_event_at: string;
  days_since_activity: number;
}

export interface ArchivedRepo {
  org: string;
  repo: string;
  archived_at: string;
  archived_by: string;
  days_since_archived: number;
}

export interface AbandonedFork {
  actor: string;
  org: string;
  repo: string;
  forked_at: string;
  days_since_fork: number;
}

export interface RepoHealthResponse {
  stale: StaleRepo[];
  archived: ArchivedRepo[];
  abandoned_forks: AbandonedFork[];
}

export interface ExternalCollaborator {
  github_login: string;
  org: string;
  repo: string | null;
  role: string;
  granted_at: string;
  granted_by: string | null;
  last_event_at: string | null;
  days_since_last_event: number | null;
}

export interface CollabSummary {
  total_active: number;
  org_level_count: number;
  elevated_count: number;
  dormant_count: number;
}

export interface ExternalCollabResponse {
  summary: CollabSummary;
  collaborators: ExternalCollaborator[];
}

export interface DormantCollaborator {
  github_login: string;
  org: string;
  repo: string | null;
  role: string;
  granted_at: string;
  last_event_at: string | null;
  days_inactive: number;
}

export function getHealthSummary(): Promise<HealthSummary> {
  return api.get<HealthSummary>('/health-signals/summary');
}

export function getPatHealth(limit = 50): Promise<PatHealthResponse> {
  return api.get<PatHealthResponse>('/health-signals/pat-health', { limit });
}

export function getBypassOffenders(
  lookbackDays = 90,
  limit = 20,
): Promise<{ offenders: BypassOffender[] }> {
  return api.get('/health-signals/bypass-offenders', {
    lookback_days: lookbackDays,
    limit,
  });
}

export function getRepoHealth(
  staleThresholdDays = 90,
  limit = 50,
): Promise<RepoHealthResponse> {
  return api.get<RepoHealthResponse>('/health-signals/repo-health', {
    stale_threshold_days: staleThresholdDays,
    limit,
  });
}

export function getExternalCollaborators(
  limit = 50,
): Promise<ExternalCollabResponse> {
  return api.get<ExternalCollabResponse>('/health-signals/external-collaborators', {
    limit,
  });
}

export function getDormantCollaborators(
  dormancyDays = 60,
  limit = 50,
): Promise<{ dormant: DormantCollaborator[] }> {
  return api.get('/health-signals/dormant-collaborators', {
    dormancy_days: dormancyDays,
    limit,
  });
}

/* ------------------------------------------------------------------ */
/*  Phase 2–4: expanded health signal types & endpoints                */
/* ------------------------------------------------------------------ */

// --- Security Posture (Phase 2) ---

export interface SecurityPostureResponse {
  repos_with_secret_scanning: number;
  repos_with_dependabot: number;
  repos_with_codeql: number;
  repos_with_ghas: number;
  features_disabled_count: number;
}

export interface SecretScanningResponse {
  unresolved_total: number;
  publicly_leaked: number;
  open_gt_7d: number;
  open_gt_30d: number;
  mttr_hours: number;
}

export interface SsoOrgStatus {
  org: string;
  sso_enabled: boolean;
}

export interface SsoHealthResponse {
  orgs: SsoOrgStatus[];
}

export interface PrivilegeChangesResponse {
  admin_promotions: number;
  integration_manager_grants: number;
  custom_role_changes: number;
}

export function getSecurityPosture(): Promise<SecurityPostureResponse> {
  return api.get<SecurityPostureResponse>('/health-signals/security-posture');
}

export function getSecretScanning(): Promise<SecretScanningResponse> {
  return api.get<SecretScanningResponse>('/health-signals/secret-scanning');
}

export function getSsoHealth(): Promise<SsoHealthResponse> {
  return api.get<SsoHealthResponse>('/health-signals/sso');
}

export function getPrivilegeChanges(): Promise<PrivilegeChangesResponse> {
  return api.get<PrivilegeChangesResponse>('/health-signals/privilege-changes');
}

// --- App Governance (Phase 3) ---

export interface AppGovernanceResponse {
  apps_installed: number;
  apps_removed: number;
  oauth_approved: number;
  oauth_denied: number;
  token_revocations: number;
  webhooks_created: number;
  webhooks_removed: number;
  webhooks_modified: number;
}

export interface CodeScanningResponse {
  total_alerts: number;
  avg_hours_to_close: number;
  dismissed_count: number;
  reappeared_count: number;
}

export interface VulnerabilitiesResponse {
  total_open: number;
  critical_open: number;
  high_open: number;
  open_gt_30d: number;
  critical_open_gt_14d: number;
  avg_open_days: number;
}

export function getAppGovernance(): Promise<AppGovernanceResponse> {
  return api.get<AppGovernanceResponse>('/health-signals/app-governance');
}

export function getCodeScanning(): Promise<CodeScanningResponse> {
  return api.get<CodeScanningResponse>('/health-signals/code-scanning');
}

export function getVulnerabilities(): Promise<VulnerabilitiesResponse> {
  return api.get<VulnerabilitiesResponse>('/health-signals/vulnerabilities');
}

// --- Operations Health (Phase 4) ---

export interface WorkflowRow {
  repo: string;
  workflow_name: string;
  total_runs: number;
  successes: number;
  failures: number;
  failure_rate_pct: number;
  last_run: string;
}

export interface WorkflowHealthResponse {
  workflows: WorkflowRow[];
}

export interface BranchProtectionResponse {
  protections_removed: number;
  policy_overrides: number;
  modified: number;
  distinct_repos_affected: number;
}

export interface CopilotGovernanceResponse {
  seats_granted_90d: number;
  seats_removed: number;
  unique_users: number;
}

export interface CodespacesResponse {
  active_never_suspended: number;
  large_machine_count: number;
  unique_users: number;
}

export interface RunnerRow {
  org: string;
  runner_name: string;
  version: string;
  group: string;
  last_event: string;
}

export interface RunnerHealthResponse {
  runners: RunnerRow[];
}

export async function getWorkflowHealth(): Promise<WorkflowHealthResponse> {
  const data = await api.get<WorkflowHealthResponse>('/health-signals/workflows');
  // PostgreSQL ROUND() returns numeric/Decimal which JSON-serializes as a string
  data.workflows = data.workflows.map((wf) => ({
    ...wf,
    failure_rate_pct: Number(wf.failure_rate_pct),
  }));
  return data;
}

export function getBranchProtection(): Promise<BranchProtectionResponse> {
  return api.get<BranchProtectionResponse>('/health-signals/branch-protection');
}

export function getCopilotGovernance(): Promise<CopilotGovernanceResponse> {
  return api.get<CopilotGovernanceResponse>('/health-signals/copilot-governance');
}

export function getCodespaces(): Promise<CodespacesResponse> {
  return api.get<CodespacesResponse>('/health-signals/codespaces');
}

export function getRunnerHealth(): Promise<RunnerHealthResponse> {
  return api.get<RunnerHealthResponse>('/health-signals/runners');
}

// --- System Health & Extended Summary ---

export interface SystemHealthResponse {
  gap_detected: boolean;
  gap_duration_minutes: number | null;
  last_event_at: string | null;
}

export interface ExtendedHealthSummary extends HealthSummary {
  unresolved_secret_alerts: number;
  security_feature_disables_7d: number;
}

export function getSystemHealth(): Promise<SystemHealthResponse> {
  return api.get<SystemHealthResponse>('/health-signals/system');
}

export function getExtendedHealthSummary(): Promise<ExtendedHealthSummary> {
  return api.get<ExtendedHealthSummary>('/health-signals/summary');
}

// --- Health Settings ---

export function getHealthSettings(): Promise<Record<string, unknown>> {
  return api.get<Record<string, unknown>>('/health-signals/settings');
}

export function updateHealthSettings(
  settings: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return api.put<Record<string, unknown>>('/health-signals/settings', settings);
}

// --- Ghost Members (License Pane) ---

export interface GhostMember {
  actor: string;
  last_active: string | null;
}

export interface GhostMembersResponse {
  ghost_members: GhostMember[];
}

export function getGhostMembers(
  dormancyDays = 90,
  limit = 50,
): Promise<GhostMembersResponse> {
  return api.get<GhostMembersResponse>('/health-signals/ghost-members', {
    dormancy_days: dormancyDays,
    limit,
  });
}

// --- Maintenance Signals ---

export interface StalePrResponse {
  org: string;
  repo: string;
  pr_number: string;
  title: string;
  actor: string;
  opened_at: string;
  days_open: number;
}

export function getStalePrs(
  staleDays = 30,
  limit = 50,
): Promise<{ stale_prs: StalePrResponse[] }> {
  return api.get('/health-signals/stale-prs', {
    stale_days: staleDays,
    limit,
  });
}

export interface UnhealthyHook {
  org: string;
  repo: string;
  action: string;
  actor: string;
  hook_id: string | null;
  app_name: string | null;
  config_url: string | null;
  created_at: string;
}

export function getUnhealthyHooks(
  limit = 50,
): Promise<{ unhealthy_hooks: UnhealthyHook[] }> {
  return api.get('/health-signals/unhealthy-hooks', { limit });
}

export interface SkippedWorkflowResponse {
  org: string;
  repo: string;
  action: string;
  actor: string;
  workflow_name: string | null;
  workflow_id: string | null;
  created_at: string;
}

export function getSkippedWorkflows(
  limit = 50,
): Promise<{ skipped_workflows: SkippedWorkflowResponse[] }> {
  return api.get('/health-signals/skipped-workflows', { limit });
}

// --- WAF Findings ---

export interface WafFindingResponse {
  id: string;
  pillar: string;
  finding: string;
  severity: string;
  status: string;
  evaluated: boolean;
  detail: string;
  evidence_count: number;
}

export function getWafFindings(): Promise<{ findings: WafFindingResponse[] }> {
  return api.get('/health-signals/waf-findings');
}

export interface TeamInfo {
  readonly org: string;
  readonly team_slug: string;
  readonly team_name: string;
  readonly members: readonly string[];
}

export interface TeamsResponse {
  readonly teams: readonly TeamInfo[];
}

export function getTeams(): Promise<TeamsResponse> {
  return api.get<TeamsResponse>('/health-signals/teams');
}
