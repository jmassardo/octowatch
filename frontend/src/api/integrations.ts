import { api } from './client';
import type {
  TicketingConfigResponse,
  TicketingConfigCreate,
  NotificationConfigResponse,
  NotificationConfigCreate,
  SiemExportConfigResponse,
  SiemExportConfigCreate,
} from '../types/integrations';

export function listTicketingConfigs(): Promise<TicketingConfigResponse[]> {
  return api.get<TicketingConfigResponse[]>('/integrations/ticketing');
}

export function createTicketingConfig(c: TicketingConfigCreate): Promise<TicketingConfigResponse> {
  return api.post<TicketingConfigResponse>('/integrations/ticketing', c);
}

export function deleteTicketingConfig(id: number): Promise<void> {
  return api.delete<void>(`/integrations/ticketing/${id}`);
}

export function listNotificationConfigs(): Promise<NotificationConfigResponse[]> {
  return api.get<NotificationConfigResponse[]>('/integrations/notifications');
}

export function createNotificationConfig(
  c: NotificationConfigCreate,
): Promise<NotificationConfigResponse> {
  return api.post<NotificationConfigResponse>('/integrations/notifications', c);
}

export function deleteNotificationConfig(id: number): Promise<void> {
  return api.delete<void>(`/integrations/notifications/${id}`);
}

// ── SIEM Export API ─────────────────────────────────────────────────────────

export function listSiemConfigs(): Promise<SiemExportConfigResponse[]> {
  return api.get<SiemExportConfigResponse[]>('/integrations/siem');
}

export function createSiemConfig(c: SiemExportConfigCreate): Promise<SiemExportConfigResponse> {
  return api.post<SiemExportConfigResponse>('/integrations/siem', c);
}

export function deleteSiemConfig(id: number): Promise<void> {
  return api.delete<void>(`/integrations/siem/${id}`);
}

export function testSiemConfig(id: number): Promise<{ success: boolean; config_id: number }> {
  return api.post<{ success: boolean; config_id: number }>(`/integrations/siem/${id}/test`);
}
