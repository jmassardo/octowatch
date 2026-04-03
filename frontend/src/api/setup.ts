import { api } from './client';

export interface SetupStatus {
  setup_required: boolean;
  setup_token_hint?: string;
}

export interface SetupLoginRequest {
  token: string;
}

export interface GitHubOAuthSetup {
  client_id: string;
  client_secret: string;
}

export interface GitHubAppSetup {
  app_id: string;
  private_key_pem: string;
  enterprise_slug: string;
  sync_enabled: boolean;
  sync_interval_days: number;
  sync_orgs: string;
}

export interface TLSSetup {
  cert_pem: string;
  key_pem: string;
  generate_self_signed: boolean;
}

export interface AppSetting {
  key: string;
  value: string;
  category: string;
  sensitivity: string;
  description: string | null;
  updated_by: string;
  updated_at: string;
}

export interface SettingAuditEntry {
  setting_key: string;
  action: string;
  changed_by: string;
  old_value_masked: string | null;
  new_value_masked: string | null;
  created_at: string;
}

export function getSetupStatus(): Promise<SetupStatus> {
  return api.get<SetupStatus>('/setup/status');
}

export function setupLogin(req: SetupLoginRequest): Promise<void> {
  return api.post<void>('/setup/login', req);
}

export function setupGitHubOAuth(req: GitHubOAuthSetup): Promise<void> {
  return api.post<void>('/setup/github-oauth', req);
}

export function setupGitHubApp(req: GitHubAppSetup): Promise<void> {
  return api.post<void>('/setup/github-app', req);
}

export function setupTLS(req: TLSSetup): Promise<void> {
  return api.post<void>('/setup/tls', req);
}

export function completeSetup(): Promise<void> {
  return api.post<void>('/setup/complete', {});
}

export function getSetupCurrentConfig(): Promise<Record<string, unknown>> {
  return api.get<Record<string, unknown>>('/setup/current');
}

export function listSettings(): Promise<AppSetting[]> {
  return api.get<AppSetting[]>('/admin/settings');
}

export function updateSetting(
  key: string,
  value: string,
  description?: string,
  options?: { category?: string; sensitivity?: string },
): Promise<AppSetting> {
  return api.put<AppSetting>(`/admin/settings/${key}`, {
    value,
    description,
    category: options?.category,
    sensitivity: options?.sensitivity,
  });
}

export function deleteSetting(key: string): Promise<void> {
  return api.delete<void>(`/admin/settings/${key}`);
}

export function getSettingsAuditTrail(): Promise<SettingAuditEntry[]> {
  return api.get<SettingAuditEntry[]>('/admin/settings/audit/trail');
}
