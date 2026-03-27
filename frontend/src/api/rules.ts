import { api } from './client';
import type { RuleResponse, RuleListResponse, RuleCreate } from '../types/detections';

export function listRules(): Promise<RuleListResponse> {
  return api.get<RuleListResponse>('/rules');
}

export function createRule(r: RuleCreate): Promise<RuleResponse> {
  return api.post<RuleResponse>('/rules', r);
}

export function updateRule(id: number, r: Partial<RuleCreate>): Promise<RuleResponse> {
  return api.put<RuleResponse>(`/rules/${id}`, r);
}

export function updateRuleStatus(id: number, status: string, enabled?: boolean): Promise<RuleResponse> {
  return api.patch<RuleResponse>(`/rules/${id}/status`, { status, enabled });
}

export function deleteRule(id: number): Promise<void> {
  return api.delete<void>(`/rules/${id}`);
}
