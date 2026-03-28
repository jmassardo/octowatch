import { api } from './client';
import type { SyncRun, SyncRunsResponse, SyncConfig } from '../types/sync';

export function triggerSync(scope: string = 'full'): Promise<{ run_id: string; status: string }> {
  return api.post('/admin/sync/trigger', { scope });
}

export function getSyncStatus(): Promise<SyncRun> {
  return api.get<SyncRun>('/admin/sync/status');
}

export function listSyncRuns(page = 1, pageSize = 20): Promise<SyncRunsResponse> {
  return api.get<SyncRunsResponse>(`/admin/sync/runs`, { page, page_size: pageSize });
}

export function getSyncRun(runId: string): Promise<SyncRun> {
  return api.get<SyncRun>(`/admin/sync/runs/${runId}`);
}

export function cancelSyncRun(runId: string): Promise<void> {
  return api.delete<void>(`/admin/sync/runs/${runId}/cancel`);
}

export function getSyncConfig(): Promise<SyncConfig> {
  return api.get<SyncConfig>('/admin/sync/config');
}
