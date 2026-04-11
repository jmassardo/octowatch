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

export function listWorkflowFindings(params?: {
  org?: string;
  repo?: string;
  severity?: string;
  status?: string;
  page?: number;
  page_size?: number;
}) {
  return api.get<WorkflowFindingsResponse>('/workflow-scanner/findings', params);
}

export function getRepoSecurityScores(params?: {
  org?: string;
  min_score?: number;
  max_score?: number;
}) {
  return api.get<RepoSecurityScore[]>('/workflow-scanner/scores', params);
}

export function scanWorkflow(body: { content: string; path?: string }) {
  return api.post<{ findings: WorkflowFinding[] }>('/workflow-scanner/scan', body);
}
