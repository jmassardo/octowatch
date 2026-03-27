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
