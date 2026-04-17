import { api } from './client';

export interface AuditStreamConfig {
  configured: boolean;
  stream_user: string;
  s3_endpoint: string;
  bucket: string;
  region: string;
  hec_endpoint: string;
  hec_configured: boolean;
  instructions: Record<string, string>;
  hec_instructions: Record<string, string>;
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

export function updateHecToken(payload: {
  hec_token: string;
}): Promise<{ status: string; hec_token: string; message: string }> {
  return api.put<{ status: string; hec_token: string; message: string }>(
    '/admin/audit-stream/hec-token',
    payload,
  );
}
