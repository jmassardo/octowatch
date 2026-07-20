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

export function getRepoHealth(staleThresholdDays = 90, limit = 50): Promise<RepoHealthResponse> {
  return api.get<RepoHealthResponse>('/health-signals/repo-health', {
    stale_threshold_days: staleThresholdDays,
    limit,
  });
}

export function getExternalCollaborators(limit = 50): Promise<ExternalCollabResponse> {
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
  push_protection_bypassed_count: number;
  open_gt_7d: number;
  open_gt_30d: number;
  mttr_hours: number;
  avg_hours_to_resolve: number | null;
  unresolved_gt_7d: number;
  unresolved_gt_30d: number;
  resolved_count: number;
  total_count: number;
  resolution_rate_pct: number;
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
  open_count: number;
  fixed_count: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
}

export interface VulnerabilitiesResponse {
  total_open: number;
  critical_open: number;
  high_open: number;
  open_gt_30d: number;
  critical_open_gt_14d: number;
  avg_open_days: number;
  open_medium: number;
  open_low: number;
  age_0_30d: number;
  age_30_60d: number;
  age_60_90d: number;
  age_gt_90d: number;
  critical_aging_gt_90d: number;
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
  last_run_at: string;
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

export function getGhostMembers(dormancyDays = 90, limit = 50): Promise<GhostMembersResponse> {
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

export function getStalePrs(staleDays = 30, limit = 50): Promise<{ stale_prs: StalePrResponse[] }> {
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

export function getUnhealthyHooks(limit = 50): Promise<{ unhealthy_hooks: UnhealthyHook[] }> {
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
  evidence?: Record<string, unknown>[];
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

// --- License Consumption (GHEC enterprise sync) ---

export interface LicenseConsumptionResponse {
  readonly enterprise_slug: string | null;
  readonly total_seats_purchased: number;
  readonly total_seats_consumed: number;
  readonly seats_available: number;
  readonly utilization_pct: number;
  readonly synced_at: string | null;
}

export function getLicenseConsumption(): Promise<LicenseConsumptionResponse> {
  return api.get<LicenseConsumptionResponse>('/health-signals/license-consumption');
}

// --- Security Alerts Summary (enterprise sync) ---

export interface SecurityAlertsSummaryResponse {
  readonly secret_scanning: ReadonlyArray<{
    org: string;
    open_count: number;
    resolved_count: number;
    total_count: number;
    synced_at: string;
  }>;
  readonly dependabot: ReadonlyArray<{
    org: string;
    open_count: number;
    fixed_count: number;
    dismissed_count: number;
    total_count: number;
    critical_count: number;
    high_count: number;
    medium_count: number;
    low_count: number;
    synced_at: string;
  }>;
}

export function getSecurityAlertsSummary(): Promise<SecurityAlertsSummaryResponse> {
  return api.get<SecurityAlertsSummaryResponse>('/health-signals/security-alerts-summary');
}

/* ------------------------------------------------------------------ */
/*  GHAS Individual Alert Types & Endpoints (Epic 5)                   */
/* ------------------------------------------------------------------ */

// --- Unified Security Dashboard ---

export interface AlertSeverityBreakdown {
  open: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  total: number;
}

export interface SecretScanningSummary {
  open: number;
  resolved: number;
  total: number;
  bypassed_open: number;
}

export interface DetectionsSummary {
  active: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
}

export interface DependabotSummary extends AlertSeverityBreakdown {
  critical_aging_gt_90d: number;
}

export interface TrendDay {
  day: string;
  secret_scanning: number;
  code_scanning: number;
  dependabot: number;
}

export interface UnifiedSecurityResponse {
  secret_scanning: SecretScanningSummary;
  code_scanning: AlertSeverityBreakdown;
  dependabot: DependabotSummary;
  detections: DetectionsSummary;
  trend_30d: TrendDay[];
}

export function getUnifiedSecurity(): Promise<UnifiedSecurityResponse> {
  return api.get<UnifiedSecurityResponse>('/health-signals/unified-security');
}

// --- Individual Alert Listing ---

export interface SecretScanningAlertItem {
  id: number;
  org_slug: string;
  alert_number: number;
  repo_full_name: string;
  secret_type: string;
  secret_type_display: string | null;
  file_path: string | null;
  commit_sha: string | null;
  state: string;
  resolution: string | null;
  push_protection_bypassed: boolean;
  push_protection_bypassed_by: string | null;
  validity: string | null;
  locations_count: number;
  resolved_by: string | null;
  created_at: string;
  updated_at: string | null;
  resolved_at: string | null;
}

export interface SecretScanningAlertsListResponse {
  alerts: SecretScanningAlertItem[];
  total: number;
}

export function getSecretScanningAlerts(
  limit = 50,
  offset = 0,
  state?: string,
): Promise<SecretScanningAlertsListResponse> {
  const params: Record<string, string | number> = { limit, offset };
  if (state) params.state = state;
  return api.get<SecretScanningAlertsListResponse>(
    '/health-signals/secret-scanning/alerts',
    params,
  );
}

export interface CodeScanningAlertItem {
  id: number;
  org_slug: string;
  alert_number: number;
  repo_full_name: string;
  rule_id: string;
  rule_description: string | null;
  severity: string | null;
  security_severity: string | null;
  cwe_ids: string[] | null;
  tool_name: string | null;
  file_path: string | null;
  start_line: number | null;
  state: string;
  dismissed_by: string | null;
  dismissed_reason: string | null;
  dismissed_at: string | null;
  created_at: string;
  fixed_at: string | null;
}

export interface CodeScanningAlertsListResponse {
  alerts: CodeScanningAlertItem[];
  total: number;
}

export function getCodeScanningAlerts(
  limit = 50,
  offset = 0,
  state?: string,
  severity?: string,
): Promise<CodeScanningAlertsListResponse> {
  const params: Record<string, string | number> = { limit, offset };
  if (state) params.state = state;
  if (severity) params.severity = severity;
  return api.get<CodeScanningAlertsListResponse>('/health-signals/code-scanning/alerts', params);
}

export interface DependabotAlertItem {
  id: number;
  org_slug: string;
  alert_number: number;
  repo_full_name: string;
  package_name: string;
  package_ecosystem: string | null;
  severity: string | null;
  cvss_score: number | null;
  cve_id: string | null;
  cwe_ids: string[] | null;
  vulnerable_version_range: string | null;
  patched_version: string | null;
  state: string;
  dismissed_by: string | null;
  dismissed_reason: string | null;
  created_at: string;
  fixed_at: string | null;
  auto_dismissed_at: string | null;
}

export interface DependabotAlertsListResponse {
  alerts: DependabotAlertItem[];
  total: number;
}

export function getDependabotAlerts(
  limit = 50,
  offset = 0,
  state?: string,
  severity?: string,
): Promise<DependabotAlertsListResponse> {
  const params: Record<string, string | number> = { limit, offset };
  if (state) params.state = state;
  if (severity) params.severity = severity;
  return api.get<DependabotAlertsListResponse>('/health-signals/vulnerabilities/alerts', params);
}

/* ------------------------------------------------------------------ */
/*  Strategic Security Dashboard (Issue #124)                          */
/* ------------------------------------------------------------------ */

// --- MTTR Trends ---

export interface MttrBySeverity {
  severity: string;
  mttr_hours: number;
  sample_size: number;
}

export interface MttrByTool {
  tool: string;
  mttr_hours: number;
}

export interface MttrTimePoint {
  date: string;
  mttr_hours: number;
}

export interface MttrTrendsResponse {
  current_mttr_hours: number;
  previous_mttr_hours: number;
  trend_pct: number;
  by_severity: MttrBySeverity[];
  time_series: MttrTimePoint[];
  by_tool: MttrByTool[];
}

export function getMttrTrends(period = '30d', severity?: string): Promise<MttrTrendsResponse> {
  const params: Record<string, string> = { period };
  if (severity) params.severity = severity;
  return api.get<MttrTrendsResponse>('/health-signals/strategic/mttr-trends', params);
}

// --- Coverage Growth ---

export interface FeatureCoverage {
  repos: number;
  pct: number;
}

export interface CoverageTimePoint {
  date: string;
  ghas_pct: number;
  code_scanning_pct: number;
  secret_scanning_pct: number;
  dependabot_pct: number;
  push_protection_pct: number;
  ghas_repos: number;
  code_scanning_repos: number;
  secret_scanning_repos: number;
  dependabot_repos: number;
  push_protection_repos: number;
}

export interface UncoveredRepo {
  repo_full_name: string;
  missing_features: string[];
}

export interface CoverageGrowthResponse {
  total_repos: number;
  feature_coverage: Record<string, FeatureCoverage>;
  time_series: CoverageTimePoint[];
  uncovered_repos: UncoveredRepo[];
}

export function getCoverageGrowth(period = '90d'): Promise<CoverageGrowthResponse> {
  return api.get<CoverageGrowthResponse>('/health-signals/strategic/coverage-growth', { period });
}

// --- Alert Aging ---

export interface AgeBucket {
  bucket: string;
  total_count: number;
  critical_count: number;
  high_count: number;
}

export interface OldestAlert {
  tool: string;
  alert_number: number;
  repo_full_name: string;
  created_at: string;
  severity: string;
  age_days: number;
  rule_info: string;
  rule_description: string | null;
}

export interface BurndownProjection {
  current_open: number;
  avg_close_rate_per_week: number;
  weeks_to_zero: number | null;
  time_series: { week: number; projected_open: number }[];
}

export interface AlertAgingResponse {
  age_buckets: AgeBucket[];
  oldest_critical: OldestAlert[];
  burndown_projection: BurndownProjection;
}

export function getAlertAging(): Promise<AlertAgingResponse> {
  return api.get<AlertAgingResponse>('/health-signals/strategic/alert-aging');
}

// --- Security Score ---

export interface ScoreComponent {
  name: string;
  score: number;
  weight: number;
  description: string;
}

export interface ScoreSuggestion {
  name: string;
  impact: number;
  suggestion: string;
}

export interface SecurityScoreResponse {
  score: number;
  components: ScoreComponent[];
  suggestions: ScoreSuggestion[];
}

export function getSecurityScore(): Promise<SecurityScoreResponse> {
  return api.get<SecurityScoreResponse>('/health-signals/strategic/security-score');
}

/* ------------------------------------------------------------------ */
/*  Org Health Dashboard (#129)                                        */
/* ------------------------------------------------------------------ */

// --- Health Score ---

export interface HealthScoreResponse {
  score: number;
  grade: string;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  total_signals: number;
  orgs_monitored: number;
}

export function getHealthScore(): Promise<HealthScoreResponse> {
  return api.get<HealthScoreResponse>('/health-signals/score');
}

// --- API Abuse ---

export interface AbuseSignal {
  signal_type: string;
  severity: string;
  actor: string;
  event_count: number;
  time_window_start: string | null;
  time_window_end: string | null;
  details: string;
  recommended_action: string;
}

export interface AbuseSignalsResponse {
  signals: AbuseSignal[];
}

export function getApiAbuseSignals(hours = 24, limit = 50): Promise<AbuseSignalsResponse> {
  return api.get<AbuseSignalsResponse>('/health-signals/api-abuse', { hours, limit });
}

// --- Dormant Users ---

export interface DormantUser {
  login: string;
  last_activity_date: string | null;
  days_inactive: number;
  seat_type: string;
  estimated_monthly_cost: number;
  recommended_action: string;
}

export interface DormantUsersResponse {
  users: DormantUser[];
  summary: {
    total_dormant: number;
    estimated_monthly_waste: number;
  };
}

export function getDormantUsers(daysInactive = 90, limit = 50): Promise<DormantUsersResponse> {
  return api.get<DormantUsersResponse>('/health-signals/dormant-users', {
    days_inactive: daysInactive,
    limit,
  });
}

// --- Platform Security ---

export interface PlatformSecurityOrg {
  org: string;
  sso_configured: boolean;
  two_fa_required: boolean;
  audit_log_streaming: boolean;
  ip_allowlist_configured: boolean;
  branch_protection_default: boolean;
  compliance_score: number;
  recommendations: string[];
}

export interface PlatformSecurityResponse {
  orgs: PlatformSecurityOrg[];
  overall_compliance_score: number;
}

export function getPlatformSecurity(): Promise<PlatformSecurityResponse> {
  return api.get<PlatformSecurityResponse>('/health-signals/platform-security');
}

// --- Maintenance Signals ---

export interface MaintenanceStaleRepo {
  org: string;
  repo: string;
  last_event_at: string;
  days_since_activity: number;
}

export interface MaintenanceEmptyRepo {
  org: string;
  repo: string;
  created_at: string;
}

export interface MaintenanceArchivedCandidate {
  org: string;
  repo: string;
  event_count: number;
  last_event_at: string;
  days_since_activity: number;
}

export interface MaintenanceSignalsResponse {
  stale_repos: MaintenanceStaleRepo[];
  empty_repos: MaintenanceEmptyRepo[];
  archived_candidates: MaintenanceArchivedCandidate[];
  summary: {
    stale_count: number;
    empty_count: number;
    archived_candidate_count: number;
  };
}

export function getMaintenanceSignals(
  staleThresholdDays = 180,
  limit = 50,
): Promise<MaintenanceSignalsResponse> {
  return api.get<MaintenanceSignalsResponse>('/health-signals/maintenance-signals', {
    stale_threshold_days: staleThresholdDays,
    limit,
  });
}

// --- GHAS Active Committers (billing) ---

export interface GHASActiveCommittersResponse {
  readonly total_active_committers: number;
  readonly maximum_active_committers: number;
  readonly purchased_committers: number;
}

export function getGHASActiveCommitters(): Promise<GHASActiveCommittersResponse> {
  return api.get<GHASActiveCommittersResponse>('/health-signals/ghas-active-committers');
}
