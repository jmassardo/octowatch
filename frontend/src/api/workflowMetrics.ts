import { api } from './client';

export interface WorkflowFailureSummary {
  org: string;
  repo: string;
  workflow_name: string;
  consecutive_count: number;
  last_run_at: string;
  last_conclusion: 'failure' | 'timed_out';
}

export interface AlwaysFailingResponse {
  items: WorkflowFailureSummary[];
  total: number;
  threshold: number;
  lookback_days: number;
  cached_at: string | null;
}

export interface WorkflowRunRecord {
  run_id: string | null;
  started_at: string;
  conclusion: string;
  duration_seconds: number | null;
}

export interface RunHistoryResponse {
  org: string;
  repo: string;
  workflow_name: string;
  runs: WorkflowRunRecord[];
}

export function getAlwaysFailingWorkflows(params?: {
  threshold?: number;
  lookback_days?: number;
  org?: string;
}): Promise<AlwaysFailingResponse> {
  return api.get<AlwaysFailingResponse>('/workflow-metrics/always-failing', params);
}

export function getAlwaysTimingOutWorkflows(params?: {
  threshold?: number;
  lookback_days?: number;
  org?: string;
}): Promise<AlwaysFailingResponse> {
  return api.get<AlwaysFailingResponse>('/workflow-metrics/always-timing-out', params);
}

export function getWorkflowRunHistory(params: {
  org: string;
  repo: string;
  workflow_name: string;
  limit?: number;
  lookback_days?: number;
}): Promise<RunHistoryResponse> {
  return api.get<RunHistoryResponse>('/workflow-metrics/run-history', params);
}
