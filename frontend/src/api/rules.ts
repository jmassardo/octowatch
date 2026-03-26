import { api } from './client';
import type { RuleResponse, RuleCreate } from '../types/detections';

export function listRules(): Promise<RuleResponse[]> {
  return api.get<RuleResponse[]>('/rules');
}

export function createRule(r: RuleCreate): Promise<RuleResponse> {
  return api.post<RuleResponse>('/rules', r);
}

export function updateRule(id: number, r: Partial<RuleCreate>): Promise<RuleResponse> {
  return api.put<RuleResponse>(`/rules/${id}`, r);
}

export function updateRuleStatus(id: number, enabled: boolean): Promise<RuleResponse> {
  return api.patch<RuleResponse>(`/rules/${id}`, { enabled });
}

export function deleteRule(id: number): Promise<void> {
  return api.delete<void>(`/rules/${id}`);
}
