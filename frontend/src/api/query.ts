import { api } from './client';
import type {
  QueryRunRequest,
  QueryRunResponse,
  QueryTemplate,
  QueryTemplateCreate,
  SavedQuery,
  SavedQueryCreate,
  SavedQueryUpdate,
  SchemaTable,
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

// ── Saved Queries ────────────────────────────────────────────────────────────

export function createSavedQuery(payload: SavedQueryCreate): Promise<SavedQuery> {
  return api.post<SavedQuery>('/query/saved', payload);
}

export function listSavedQueries(): Promise<SavedQuery[]> {
  return api.get<SavedQuery[]>('/query/saved');
}

export function updateSavedQuery(id: number, payload: SavedQueryUpdate): Promise<SavedQuery> {
  return api.put<SavedQuery>(`/query/saved/${id}`, payload);
}

export function deleteSavedQuery(id: number): Promise<void> {
  return api.delete<void>(`/query/saved/${id}`);
}

export function shareQuery(id: number, logins: string[]): Promise<SavedQuery> {
  return api.post<SavedQuery>(`/query/saved/${id}/share`, { logins });
}

export function listSharedQueries(): Promise<SavedQuery[]> {
  return api.get<SavedQuery[]>('/query/shared');
}

export function scheduleQuery(
  id: number,
  payload: { cron: string; enabled: boolean },
): Promise<SavedQuery> {
  return api.post<SavedQuery>(`/query/saved/${id}/schedule`, payload);
}

// ── Schema ──────────────────────────────────────────────────────────────────

export function getQuerySchema(): Promise<SchemaTable[]> {
  return api.get<SchemaTable[]>('/query/schema');
}
