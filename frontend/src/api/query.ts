import { api } from './client';
import type {
  QueryRunRequest,
  QueryRunResponse,
  QueryTemplate,
  QueryTemplateCreate,
} from '../types/query';

export function runQuery(req: QueryRunRequest): Promise<QueryRunResponse> {
  return api.post<QueryRunResponse>('/query/run', req);
}

export function validateQuery(sql: string): Promise<{ valid: boolean; error?: string }> {
  return api.post<{ valid: boolean; error?: string }>('/query/validate', { sql });
}

export function listTemplates(): Promise<QueryTemplate[]> {
  return api.get<QueryTemplate[]>('/query/templates');
}

export function createTemplate(t: QueryTemplateCreate): Promise<QueryTemplate> {
  return api.post<QueryTemplate>('/query/templates', t);
}

export function deleteTemplate(id: number): Promise<void> {
  return api.delete<void>(`/query/templates/${id}`);
}

export function runTemplate(id: number): Promise<QueryRunResponse> {
  return api.post<QueryRunResponse>(`/query/templates/${id}/run`);
}
