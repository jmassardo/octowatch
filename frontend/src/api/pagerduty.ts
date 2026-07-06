import { api } from './client';

export type PagerDutyNotificationSource =
  'detections' | 'sync_errors' | 'system_health' | 'threat_intel';

export type PagerDutySeverity = 'critical' | 'error' | 'warning' | 'info';
export type OctoWatchSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info';

export interface PagerDutyConfigResponse {
  routing_key_configured: boolean;
  routing_key_masked: string | null;
  severity_mapping: Record<OctoWatchSeverity, PagerDutySeverity>;
  notification_settings: Record<PagerDutyNotificationSource, boolean>;
  auto_resolve: boolean;
}

export interface PagerDutyConfigUpdate {
  routing_key?: string;
  severity_mapping: Record<OctoWatchSeverity, PagerDutySeverity>;
  notification_settings: Record<PagerDutyNotificationSource, boolean>;
  auto_resolve: boolean;
}

export interface PagerDutyTestResponse {
  ok: boolean;
  message: string;
}

export function getPagerDutyConfig(): Promise<PagerDutyConfigResponse> {
  return api.get<PagerDutyConfigResponse>('/integrations/pagerduty/config');
}

export function updatePagerDutyConfig(
  payload: PagerDutyConfigUpdate,
): Promise<PagerDutyConfigResponse> {
  return api.put<PagerDutyConfigResponse>('/integrations/pagerduty/config', payload);
}

export function testPagerDutyConnection(): Promise<PagerDutyTestResponse> {
  return api.post<PagerDutyTestResponse>('/integrations/pagerduty/test');
}
