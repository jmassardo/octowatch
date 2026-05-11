import { api } from './client';
import type {
  NotificationListResponse,
  NotificationItem,
  NotificationPreferences,
  NotificationPreferencesUpdate,
  MarkReadResponse,
  NotificationListParams,
} from '../types/notifications';

export function listNotifications(
  params?: NotificationListParams,
): Promise<NotificationListResponse> {
  const query: Record<string, string | number | boolean | undefined> = {};
  if (params?.page !== undefined) query.page = params.page;
  if (params?.page_size !== undefined) query.page_size = params.page_size;
  if (params?.severity !== undefined) query.severity = params.severity;
  if (params?.read !== undefined) query.read = params.read;
  if (params?.source !== undefined) query.source = params.source;
  return api.get<NotificationListResponse>('/notifications', query);
}

export function markNotificationRead(id: number): Promise<NotificationItem> {
  return api.put<NotificationItem>(`/notifications/${id}/read`);
}

export function markAllNotificationsRead(): Promise<MarkReadResponse> {
  return api.post<MarkReadResponse>('/notifications/read-all');
}

export function getNotificationPreferences(): Promise<NotificationPreferences> {
  return api.get<NotificationPreferences>('/notifications/preferences');
}

export function updateNotificationPreferences(
  data: NotificationPreferencesUpdate,
): Promise<NotificationPreferences> {
  return api.put<NotificationPreferences>('/notifications/preferences', data);
}
