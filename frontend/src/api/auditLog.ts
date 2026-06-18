import { api } from './client';
import type { AuditLogListParams, AuditLogListResponse } from '../types/auditLog';

export function listAuditLog(params: AuditLogListParams): Promise<AuditLogListResponse> {
  return api.get<AuditLogListResponse>('/admin/audit-log', params);
}

export function exportAuditLogCsv(params: AuditLogListParams): void {
  const searchParams = new URLSearchParams();

  if (params.actor) searchParams.set('actor', params.actor);
  if (params.action) searchParams.set('action', params.action);
  if (params.resource_type) searchParams.set('resource_type', params.resource_type);
  if (params.outcome) searchParams.set('outcome', params.outcome);
  if (params.start_date) searchParams.set('start_date', params.start_date);
  if (params.end_date) searchParams.set('end_date', params.end_date);

  const qs = searchParams.toString();
  const url =
    qs.length > 0 ? `/api/v1/admin/audit-log/export?${qs}` : '/api/v1/admin/audit-log/export';
  window.open(url, '_blank');
}
