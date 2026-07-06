import { api } from './client';

export type SlackNotificationSource =
  'detections' | 'sync_errors' | 'system_health' | 'threat_intel';

export interface SlackConfigResponse {
  bot_token_configured: boolean;
  signing_secret_configured: boolean;
  bot_token_masked: string | null;
  signing_secret_masked: string | null;
  default_channel: string;
  channel_mappings: Record<SlackNotificationSource, string>;
  notification_settings: Record<SlackNotificationSource, boolean>;
  installation_url: string;
  installation_instructions: string[];
  commands: string[];
}

export interface SlackConfigUpdate {
  bot_token?: string;
  signing_secret?: string;
  default_channel: string;
  channel_mappings: Record<SlackNotificationSource, string>;
  notification_settings: Record<SlackNotificationSource, boolean>;
}

export interface SlackTestResponse {
  ok: boolean;
  channel: string;
  message: string;
}

export function getSlackConfig(): Promise<SlackConfigResponse> {
  return api.get<SlackConfigResponse>('/integrations/slack/config');
}

export function updateSlackConfig(payload: SlackConfigUpdate): Promise<SlackConfigResponse> {
  return api.put<SlackConfigResponse>('/integrations/slack/config', payload);
}

export function testSlackConnection(): Promise<SlackTestResponse> {
  return api.post<SlackTestResponse>('/integrations/slack/test');
}
