export interface MeResponse {
  readonly github_login: string;
  readonly github_id: number;
  readonly roles: readonly string[];
  readonly scoped_orgs: readonly string[];
  readonly scoped_repos: readonly string[];
  readonly scope_type: string;
  readonly session_expires_at: string;
}
