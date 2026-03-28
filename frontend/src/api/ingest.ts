import { apiFetch, api } from './client';
import type { ManualIngestJob } from '../types/ingest';

export function uploadFile(file: File, type: string, description?: string): Promise<ManualIngestJob> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('type', type);
  if (description) formData.append('description', description);

  // Use apiFetch directly so FormData is sent as-is (not JSON-stringified).
  // The browser will set the correct multipart/form-data Content-Type header
  // with the boundary automatically.
  return apiFetch<ManualIngestJob>('/admin/ingest/upload', {
    method: 'POST',
    body: formData,
  });
}

export function getIngestJob(jobId: string): Promise<ManualIngestJob> {
  return api.get<ManualIngestJob>(`/admin/ingest/jobs/${jobId}`);
}

export function listIngestJobs(page = 1): Promise<{ items: ManualIngestJob[]; total: number }> {
  return api.get(`/admin/ingest/jobs`, { page });
}
