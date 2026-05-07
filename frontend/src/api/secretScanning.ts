import { api } from './client';

// ── Response types ────────────────────────────────────────────────────────────

export interface SecretAlertItem {
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
  synced_at: string | null;
}

export interface SecretAlertsListResponse {
  alerts: SecretAlertItem[];
  total: number;
}

export interface SecretAlertSummaryResponse {
  open_alerts: number;
  resolved_30d: number;
  push_protection_bypasses: number;
  active_secrets: number;
  mttr_hours: number;
  open_by_type: { secret_type_label: string; count: number }[];
  resolution_breakdown: { resolution: string; count: number }[];
}

export interface TrendPoint {
  date: string;
  new_alerts: number;
  resolved_alerts: number;
}

export interface SecretTrendsResponse {
  period: number;
  points: TrendPoint[];
}

export interface AuditEvent {
  id: number;
  action: string;
  actor: string;
  org: string;
  repo: string | null;
  created_at: string;
  data: Record<string, unknown> | null;
}

export interface AuditTrailResponse {
  alert_id: number;
  events: AuditEvent[];
}

export interface PushProtectionStatsResponse {
  total: number;
  bypassed: number;
  blocked: number;
  effectiveness_pct: number;
}

export interface SyncResultItem {
  org: string;
  created: number;
  updated: number;
  total_fetched: number;
  errors: string[];
}

export interface SyncResponse {
  sync_results: SyncResultItem[];
}

// ── API functions ─────────────────────────────────────────────────────────────

export function listSecretAlerts(
  limit = 50,
  offset = 0,
  state?: string,
  secretType?: string,
  validity?: string,
  pushProtectionBypassed?: boolean,
): Promise<SecretAlertsListResponse> {
  const params: Record<string, string | number | boolean> = { limit, offset };
  if (state) params.state = state;
  if (secretType) params.secret_type = secretType;
  if (validity) params.validity = validity;
  if (pushProtectionBypassed !== undefined) {
    params.push_protection_bypassed = pushProtectionBypassed;
  }
  return api.get<SecretAlertsListResponse>('/secret-scanning/alerts', params);
}

export function getSecretAlertSummary(): Promise<SecretAlertSummaryResponse> {
  return api.get<SecretAlertSummaryResponse>('/secret-scanning/summary');
}

export function getSecretAlertTrends(period = 30): Promise<SecretTrendsResponse> {
  return api.get<SecretTrendsResponse>('/secret-scanning/trends', { period });
}

export function getSecretAlertDetail(alertId: number): Promise<SecretAlertItem> {
  return api.get<SecretAlertItem>(`/secret-scanning/alerts/${alertId}`);
}

export function triggerSecretSync(): Promise<SyncResponse> {
  return api.post<SyncResponse>('/secret-scanning/sync');
}

export function getSecretAlertAuditTrail(alertId: number): Promise<AuditTrailResponse> {
  return api.get<AuditTrailResponse>(`/secret-scanning/alerts/${alertId}/audit-trail`);
}

export function getPushProtectionStats(): Promise<PushProtectionStatsResponse> {
  return api.get<PushProtectionStatsResponse>('/secret-scanning/push-protection-stats');
}
