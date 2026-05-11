import { api } from './client';

export type MaintenanceSeverity = 'info' | 'warning' | 'critical';

export interface MaintenanceStatus {
  enabled: boolean;
  message: string;
  severity: MaintenanceSeverity;
  block_writes: boolean;
  started_at: string | null;
  estimated_end: string | null;
}

export interface MaintenanceUpdateRequest {
  enabled: boolean;
  message: string;
  severity: MaintenanceSeverity;
  block_writes: boolean;
  estimated_end: string | null;
}

export function getMaintenanceStatus(): Promise<MaintenanceStatus> {
  return api.get<MaintenanceStatus>('/admin/maintenance');
}

export function updateMaintenanceStatus(
  payload: MaintenanceUpdateRequest,
): Promise<MaintenanceStatus> {
  return api.put<MaintenanceStatus>('/admin/maintenance', payload);
}

export function toggleMaintenanceMode(payload?: { enabled?: boolean }): Promise<MaintenanceStatus> {
  return api.post<MaintenanceStatus>('/admin/maintenance/toggle', payload ?? {});
}
