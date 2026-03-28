import { api } from './client';
import type { ReportEnvelope, ReportParams, ReportCatalogEntry } from '../types/reports';

function toQueryParams(params: ReportParams): Record<string, string | number | boolean | undefined> {
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

export function exportReport(reportType: string, format: 'csv' | 'pdf' = 'csv'): void {
  window.open(`/api/v1/reports/export/${reportType}?format=${format}`, '_blank');
}

export function getReportCatalog(): Promise<ReportCatalogEntry[]> {
  return api.get<ReportCatalogEntry[]>('/reports/catalog');
}
