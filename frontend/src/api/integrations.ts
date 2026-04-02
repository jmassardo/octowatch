import { api } from './client';
import type {
  TicketingConfigResponse,
  TicketingConfigCreate,
  NotificationConfigResponse,
  NotificationConfigCreate,
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
