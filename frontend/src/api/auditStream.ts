import { api } from './client';

export interface AuditStreamConfig {
  configured: boolean;
  stream_user: string;
  s3_endpoint: string;
  bucket: string;
  region: string;
  instructions: Record<string, string>;
}

export interface AuditStreamUpdate {
  stream_user: string;
  stream_password: string;
}

export function getAuditStreamConfig(): Promise<AuditStreamConfig> {
  return api.get<AuditStreamConfig>('/admin/audit-stream/config');
}

export function updateAuditStreamConfig(
  payload: AuditStreamUpdate,
): Promise<{ status: string; message: string }> {
  return api.put<{ status: string; message: string }>('/admin/audit-stream/config', payload);
}
