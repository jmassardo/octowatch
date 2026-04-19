import { api } from './client';

export interface AuditStreamConfig {
  configured: boolean;
  hec_endpoint: string;
  hec_configured: boolean;
  hec_instructions: Record<string, string>;
}

export function getAuditStreamConfig(): Promise<AuditStreamConfig> {
  return api.get<AuditStreamConfig>('/admin/audit-stream/config');
}

export function updateHecToken(payload: {
  hec_token: string;
}): Promise<{ status: string; hec_token: string; message: string }> {
  return api.put<{ status: string; hec_token: string; message: string }>(
    '/admin/audit-stream/hec-token',
    payload,
  );
}
