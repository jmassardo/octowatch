import { api } from './client';

export interface WorkflowFinding {
  id: number;
  org: string;
  repo: string;
  workflow_path: string;
  rule_id: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  title: string;
  description: string;
  recommendation: string;
  snippet: string | null;
  first_seen: string;
  last_seen: string;
  status: 'open' | 'acknowledged' | 'resolved' | 'false_positive';
}

export interface RepoSecurityScore {
  org: string;
  repo: string;
  score: number;
  finding_count: number;
  critical_count: number;
  high_count: number;
}

export interface WorkflowFindingsResponse {
  findings: WorkflowFinding[];
  total: number;
}

export interface ScanActivity {
  id: number;
  trigger_event_ids: number[];
  org: string;
  repo: string;
  workflow_path: string;
  started_at: string;
  completed_at: string | null;
  status: 'pending' | 'running' | 'completed' | 'failed';
  checks_performed: string[];
  findings_count: number;
  data_sources: string[];
  duration_ms: number | null;
}

export interface ScanActivityListResponse {
  items: ScanActivity[];
  total: number;
}

export function listWorkflowFindings(params?: {
  org?: string;
  repo?: string;
  severity?: string;
  status?: string;
  page?: number;
  page_size?: number;
}) {
  return api.get<WorkflowFindingsResponse>('/workflows/findings', params);
}

export function getRepoSecurityScores(params?: {
  org?: string;
  min_score?: number;
  max_score?: number;
}) {
  return api.get<RepoSecurityScore[]>('/workflows/scores', params);
}

export function scanWorkflow(body: { content: string; path?: string }) {
  return api.post<{ findings: WorkflowFinding[] }>('/workflows/scan', body);
}

export function triggerRepoScan() {
  return api.post<{ task_id: string; status: string }>('/workflows/scan-repos', {});
}

export function listScanActivity(params?: { page?: number; page_size?: number }) {
  return api.get<ScanActivityListResponse>('/workflows/activity', params);
}
