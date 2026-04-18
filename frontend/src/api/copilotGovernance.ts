import { api } from './client';

export interface CopilotPolicy {
  id: number;
  name: string;
  description: string | null;
  policy_type: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  enabled: boolean;
  config: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface CopilotPolicyViolation {
  id: number;
  policy_id: number;
  policy_name: string;
  severity: string;
  actor: string | null;
  org: string | null;
  description: string;
  context_data: Record<string, unknown>;
  detected_at: string;
  status: 'open' | 'acknowledged' | 'resolved' | 'false_positive';
}

export interface CopilotPolicyViolationsResponse {
  violations: CopilotPolicyViolation[];
  total: number;
}

export function listCopilotPolicies() {
  return api.get<CopilotPolicy[]>('/copilot-governance/policies');
}

export function createCopilotPolicy(body: {
  name: string;
  policy_type: string;
  severity: string;
  config: Record<string, unknown>;
}) {
  return api.post<CopilotPolicy>('/copilot-governance/policies', body);
}

export function updateCopilotPolicy(
  id: number,
  body: { enabled?: boolean; config?: Record<string, unknown>; severity?: string },
) {
  return api.patch<CopilotPolicy>(`/copilot-governance/policies/${id}`, body);
}

export function deleteCopilotPolicy(id: number) {
  return api.delete<void>(`/copilot-governance/policies/${id}`);
}

export function listCopilotViolations(params?: {
  policy_id?: number;
  severity?: string;
  status?: string;
  page?: number;
  page_size?: number;
}) {
  return api.get<CopilotPolicyViolationsResponse>('/copilot-governance/violations', params);
}
