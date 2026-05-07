import { api } from './client';

export interface PlaybookStep {
  title: string;
  description: string;
  action_type: string;
  action_url?: string;
  required?: boolean;
  config?: Record<string, unknown>;
}

export interface PlaybookTemplate {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  detection_categories: string[];
  steps: PlaybookStep[];
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface PlaybookStepResult {
  step_index: number;
  title: string;
  completed: boolean;
  notes: string;
  skipped?: boolean;
  skip_reason?: string;
  completed_by?: string;
  completed_at?: string;
}

export interface PlaybookExecution {
  id: number;
  template_id: number;
  detection_id: number;
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
  step_results: PlaybookStepResult[];
  started_by: string;
  started_at: string;
  completed_at: string | null;
}

export interface PlaybookExecutionListResponse {
  items: PlaybookExecution[];
  total: number;
}

export interface CreateTemplatePayload {
  name: string;
  description?: string;
  detection_categories: string[];
  steps: { title: string; description: string; action_type: string; required?: boolean }[];
}

export interface UpdateTemplatePayload {
  name?: string;
  description?: string;
  detection_categories?: string[];
  steps?: { title: string; description: string; action_type: string; required?: boolean }[];
}

export function listPlaybookTemplates(params?: { category?: string }) {
  return api.get<PlaybookTemplate[]>('/playbooks/templates', params);
}

export function getPlaybookTemplate(id: number) {
  return api.get<PlaybookTemplate>(`/playbooks/templates/${id}`);
}

export function createPlaybookTemplate(body: CreateTemplatePayload) {
  return api.post<PlaybookTemplate>('/playbooks/templates', body);
}

export function updatePlaybookTemplate(id: number, body: UpdateTemplatePayload) {
  return api.put<PlaybookTemplate>(`/playbooks/templates/${id}`, body);
}

export function deletePlaybookTemplate(id: number) {
  return api.delete<void>(`/playbooks/templates/${id}`);
}

export function executePlaybook(body: { template_id: number; detection_id: number }) {
  return api.post<PlaybookExecution>('/playbooks/execute', body);
}

export function getPlaybookExecution(executionId: number) {
  return api.get<PlaybookExecution>(`/playbooks/executions/${executionId}`);
}

export function listPlaybookExecutions(params?: { detection_id?: number; status?: string }) {
  return api.get<PlaybookExecutionListResponse>('/playbooks/executions', params);
}

export function completePlaybookStep(
  executionId: number,
  stepIndex: number,
  body: { completed: boolean; notes: string },
) {
  return api.patch<PlaybookExecution>(
    `/playbooks/executions/${executionId}/steps/${stepIndex}`,
    body,
  );
}

export function skipPlaybookStep(executionId: number, stepIndex: number, body: { reason: string }) {
  return api.post<PlaybookExecution>(
    `/playbooks/executions/${executionId}/skip-step?step_index=${stepIndex}`,
    body,
  );
}

export function completePlaybookExecution(executionId: number) {
  return api.post<PlaybookExecution>(`/playbooks/executions/${executionId}/complete`);
}
