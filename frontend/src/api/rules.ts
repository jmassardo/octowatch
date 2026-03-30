import { api } from './client';
import type { RuleResponse, RuleListResponse, RuleCreate } from '../types/detections';

export function listRules(params?: { limit?: number; offset?: number; search?: string }): Promise<RuleListResponse> {
  return api.get<RuleListResponse>('/rules', params as Record<string, string | number>);
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

export interface ValidateConfigResponse {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export function validateRuleConfig(
  logicType: string,
  logicConfig: Record<string, unknown>,
): Promise<ValidateConfigResponse> {
  return api.post<ValidateConfigResponse>('/rules/validate-config', {
    logic_type: logicType,
    logic_config: logicConfig,
  });
}

export interface RuleVersionResponse {
  id: number;
  rule_id: number;
  version: number;
  logic_config: Record<string, unknown>;
  change_summary: string | null;
  changed_by: string;
  git_commit_sha: string | null;
  created_at: string;
}

export function listRuleVersions(ruleId: number): Promise<RuleVersionResponse[]> {
  return api.get<RuleVersionResponse[]>(`/rules/${ruleId}/versions`);
}

export interface RuleTestEventRequest {
  event: Record<string, unknown>;
}

export interface RuleTestEventResponse {
  matched: boolean;
  reason: string;
  matched_fields: string[];
}

export function testRule(ruleId: number, event: Record<string, unknown>): Promise<RuleTestEventResponse> {
  return api.post<RuleTestEventResponse>(`/rules/${ruleId}/test`, { event });
}
