import { api } from './client';
import type {
  ReportEnvelope,
  ReportParams,
  ReportCatalogEntry,
  CustomReport,
  CustomReportCreate,
  ReportRunParams,
  ReportRunResult,
  ShareReportRequest,
} from '../types/reports';

function toQueryParams(
  params: ReportParams,
): Record<string, string | number | boolean | undefined> {
  const { window_days, granularity, org } = params;
  return { window_days, granularity, org } as Record<string, string | number | boolean | undefined>;
}

export function getMauReport(params: ReportParams = {}): Promise<ReportEnvelope> {
  return api.get<ReportEnvelope>('/reports/mau', toQueryParams(params));
}

export function getSeatUtilizationReport(params: ReportParams = {}): Promise<ReportEnvelope> {
  return api.get<ReportEnvelope>('/reports/seat-utilization', toQueryParams(params));
}

export function getCopilotSeatsReport(params: ReportParams = {}): Promise<ReportEnvelope> {
  return api.get<ReportEnvelope>('/reports/copilot-seats', toQueryParams(params));
}

export function getActionsVolumeReport(params: ReportParams = {}): Promise<ReportEnvelope> {
  return api.get<ReportEnvelope>('/reports/actions-volume', toQueryParams(params));
}

export function getRepoCreationRateReport(params: ReportParams = {}): Promise<ReportEnvelope> {
  return api.get<ReportEnvelope>('/reports/repo-creation-rate', toQueryParams(params));
}

export function getPatCountsReport(params: ReportParams = {}): Promise<ReportEnvelope> {
  return api.get<ReportEnvelope>('/reports/pat-counts', toQueryParams(params));
}

export function getWebhookCountsReport(params: ReportParams = {}): Promise<ReportEnvelope> {
  return api.get<ReportEnvelope>('/reports/webhook-counts', toQueryParams(params));
}

export function getCodespaceHoursReport(params: ReportParams = {}): Promise<ReportEnvelope> {
  return api.get<ReportEnvelope>('/reports/codespace-hours', toQueryParams(params));
}

export function exportReport(reportType: string, format: 'csv' | 'pdf' = 'csv'): void {
  window.open(`/api/v1/reports/export/${reportType}?format=${format}`, '_blank');
}

export function getReportCatalog(): Promise<ReportCatalogEntry[]> {
  return api.get<ReportCatalogEntry[]>('/reports/catalog');
}

// Custom report API

export function listCustomReports(): Promise<CustomReport[]> {
  return api.get<CustomReport[]>('/reports/custom');
}

export function listSharedReports(): Promise<CustomReport[]> {
  return api.get<CustomReport[]>('/reports/custom/shared');
}

export function getCustomReport(reportId: number): Promise<CustomReport> {
  return api.get<CustomReport>(`/reports/custom/${reportId}`);
}

export function createCustomReport(body: CustomReportCreate): Promise<CustomReport> {
  return api.post<CustomReport>('/reports/custom', body);
}

export function updateCustomReport(
  reportId: number,
  body: Partial<CustomReportCreate>,
): Promise<CustomReport> {
  return api.patch<CustomReport>(`/reports/custom/${reportId}`, body);
}

export function deleteCustomReport(reportId: number): Promise<void> {
  return api.delete<void>(`/reports/custom/${reportId}`);
}

export function runCustomReport(
  reportId: number,
  params: ReportRunParams,
): Promise<ReportRunResult> {
  return api.post<ReportRunResult>(`/reports/custom/${reportId}/run`, params);
}

export function shareCustomReport(
  reportId: number,
  body: ShareReportRequest,
): Promise<CustomReport> {
  return api.post<CustomReport>(`/reports/custom/${reportId}/share`, body);
}

export function exportCustomReport(
  reportId: number,
  format: 'csv' | 'xlsx',
  params: ReportRunParams = {},
): void {
  const queryParts: string[] = [];
  if (params.window_days) queryParts.push(`window_days=${params.window_days}`);
  if (params.org) queryParts.push(`org=${params.org}`);
  const qs = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';
  window.open(`/api/v1/reports/custom/${reportId}/export/${format}${qs}`, '_blank');
}
