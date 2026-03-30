import { api } from './client';

export interface PostureCheckResult {
  rule_id: number;
  rule_name: string;
  category: string;
  severity: string;
  status: string;
  title: string;
  description: string;
  detection_id: number | null;
  context_data: Record<string, unknown>;
  triggered_at: string | null;
}

export interface RepoSummary {
  total: number;
  passing: number;
  warning: number;
  failing: number;
}

export interface RepoPosture {
  repo_name: string;
  org: string;
  visibility: string | null;
  default_branch: string | null;
  archived: boolean;
  fork: boolean;
  language: string | null;
  pushed_at: string | null;
  score: number;
  checks: PostureCheckResult[];
  detection_count: number;
}

export interface OrgPosture {
  org_login: string;
  score: number;
  two_factor_required: boolean | null;
  default_repo_permission: string | null;
  members_can_fork_private_repos: boolean | null;
  members_can_create_public_repos: boolean | null;
  ip_allow_list_enabled: boolean | null;
  checks: PostureCheckResult[];
  repos: RepoPosture[] | null;
  repo_summary: RepoSummary | null;
  detection_count: number;
}

export interface BreadcrumbItem {
  label: string;
  href: string | null;
}

export interface PostureResponse {
  level: string;
  score: number;
  orgs: OrgPosture[] | null;
  org: OrgPosture | null;
  repo: RepoPosture | null;
  breadcrumb: BreadcrumbItem[];
  last_sync_at: string | null;
  page: number;
  page_size: number;
  total: number;
  has_next: boolean;
}

export function getPosture(params?: { org?: string; repo?: string; search?: string; page?: number; page_size?: number }): Promise<PostureResponse> {
  return api.get<PostureResponse>('/posture', params as Record<string, string>);
}
