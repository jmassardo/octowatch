import { api } from './client';

/** Login history entry returned by the profile endpoint. */
export interface LoginHistoryEntry {
  readonly timestamp: string;
  readonly ip_address: string | null;
}

/** Full user profile response. */
export interface UserProfile {
  readonly github_login: string;
  readonly github_id: number;
  readonly display_name: string;
  readonly email: string | null;
  readonly avatar_url: string | null;
  readonly roles: readonly string[];
  readonly scoped_orgs: readonly string[];
  readonly scoped_repos: readonly string[];
  readonly scope_type: string;
  readonly login_history: readonly LoginHistoryEntry[];
  readonly session_expires_at: string;
}

/** User preferences. */
export interface UserPreferences {
  readonly theme: 'system' | 'light' | 'dark';
  readonly default_dashboard_view: 'operations' | 'executive' | 'security' | 'cicd';
  readonly default_org: string;
  readonly timezone: string;
  readonly date_format: 'relative' | 'absolute';
  readonly items_per_page: number;
}

/** Active session entry. */
export interface SessionInfo {
  readonly session_id: string;
  readonly ip_address: string | null;
  readonly user_agent: string | null;
  readonly created_at: string | null;
  readonly expires_at: string | null;
  readonly is_current: boolean;
}

/** Session list response. */
export interface SessionListResponse {
  readonly sessions: readonly SessionInfo[];
}

/** Fetch current user's full profile. */
export function getUserProfile(): Promise<UserProfile> {
  return api.get<UserProfile>('/user/profile');
}

/** Fetch current user's preferences. */
export function getUserPreferences(): Promise<UserPreferences> {
  return api.get<UserPreferences>('/user/preferences');
}

/** Update current user's preferences. */
export function updateUserPreferences(prefs: UserPreferences): Promise<UserPreferences> {
  return api.put<UserPreferences>('/user/preferences', prefs);
}

/** List current user's active sessions. */
export function getUserSessions(): Promise<SessionListResponse> {
  return api.get<SessionListResponse>('/user/sessions');
}

/** Revoke a specific session. */
export function revokeSession(sessionId: string): Promise<void> {
  return api.delete<void>(`/user/sessions/${sessionId}`);
}
