import { api, apiFetch } from './client';
import type { ReportEnvelope, ReportParams } from '../types/reports';

export function getMauReport(params: ReportParams = {}): Promise<ReportEnvelope> {
  return api.get<ReportEnvelope>('/reports/mau', params as Record<string, string | number | boolean | undefined>);
}

export function getSeatUtilizationReport(params: ReportParams = {}): Promise<ReportEnvelope> {
  return api.get<ReportEnvelope>('/reports/seat-utilization', params as Record<string, string | number | boolean | undefined>);
}

export function getCopilotSeatsReport(params: ReportParams = {}): Promise<ReportEnvelope> {
  return api.get<ReportEnvelope>('/reports/copilot-seats', params as Record<string, string | number | boolean | undefined>);
}

export function getActionsVolumeReport(params: ReportParams = {}): Promise<ReportEnvelope> {
  return api.get<ReportEnvelope>('/reports/actions-volume', params as Record<string, string | number | boolean | undefined>);
}

export async function exportReport(reportType: string, format: 'csv' | 'pdf' = 'csv'): Promise<void> {
  const response = await apiFetch<Response>(`/reports/export/${reportType}?format=${format}`, {
    method: 'GET',
  });
  // Trigger download
  const blob = response instanceof Blob ? response : new Blob([JSON.stringify(response)]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${reportType}.${format}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
