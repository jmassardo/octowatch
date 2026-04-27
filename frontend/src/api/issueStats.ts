import { api } from './client';

export interface OrgIssueStat {
  org: string;
  opened: number;
  closed: number;
  net_open: number;
  avg_hours_to_close: number | null;
}

export interface RepoIssueStat {
  org: string;
  repo: string;
  opened: number;
  closed: number;
  net_open: number;
  avg_hours_to_close: number | null;
}

export interface IssueStatsByOrgResponse {
  window_days: number;
  total_opened: number;
  total_closed: number;
  orgs: OrgIssueStat[];
}

export interface IssueStatsByRepoResponse {
  window_days: number;
  total_opened: number;
  total_closed: number;
  repos: RepoIssueStat[];
}

export function getIssueStatsByOrg(params: { window_days?: number; org?: string }) {
  return api.get<IssueStatsByOrgResponse>('/issue-stats/by-org', params);
}

export function getIssueStatsByRepo(params: { window_days?: number; org?: string }) {
  return api.get<IssueStatsByRepoResponse>('/issue-stats/by-repo', params);
}
