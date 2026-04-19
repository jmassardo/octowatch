import { api } from './client';

export interface PlaybookStep {
  title: string;
  description: string;
  action_type: string;
  config: Record<string, unknown>;
}

export interface PlaybookTemplate {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  detection_categories: string[];
  steps: PlaybookStep[];
  created_by: string;
  is_builtin: boolean;
  created_at: string;
}

export interface PlaybookExecution {
  id: number;
  template_id: number;
  detection_id: number;
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
  current_step: number;
  step_results: Record<string, unknown>[];
  started_by: string;
  started_at: string;
  completed_at: string | null;
}

export function listPlaybookTemplates(params?: { category?: string }) {
  return api.get<PlaybookTemplate[]>('/playbooks/templates', params);
}

export function getPlaybookTemplate(id: number) {
  return api.get<PlaybookTemplate>(`/playbooks/templates/${id}`);
}

export function startPlaybookExecution(body: { template_id: number; detection_id: number }) {
  return api.post<PlaybookExecution>('/playbooks/executions', body);
}

export function advancePlaybookStep(
  executionId: number,
  body: { result: Record<string, unknown> },
) {
  return api.post<PlaybookExecution>(`/playbooks/executions/${executionId}/advance`, body);
}

export function getPlaybookExecution(executionId: number) {
  return api.get<PlaybookExecution>(`/playbooks/executions/${executionId}`);
}

export function listPlaybookExecutions(params?: { detection_id?: number; status?: string }) {
  return api.get<PlaybookExecution[]>('/playbooks/executions', params);
}
