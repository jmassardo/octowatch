import { api } from './client';

export interface AutomationTarget {
  id: number;
  name: string;
  target_type: 'webhook' | 'dispatch';
  webhook_url: string | null;
  dispatch_repo: string | null;
  dispatch_event_type: string | null;
  rule_ids: number[];
  rule_categories: string[];
  severity_filter: string[];
  org_filter: string[];
  is_catch_all: boolean;
  rate_limit_per_minute: number;
  max_retries: number;
  enabled: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AutomationDelivery {
  id: number;
  target_id: number;
  detection_id: number;
  status: 'pending' | 'delivered' | 'failed' | 'retrying';
  attempts: number;
  last_attempt_at: string | null;
  next_retry_at: string | null;
  response_code: number | null;
  error_message: string | null;
  payload_hash: string;
  is_dry_run: boolean;
  created_at: string;
  target_name: string;
  target_type: 'webhook' | 'dispatch';
}

export interface CreateTargetRequest {
  name: string;
  target_type: 'webhook' | 'dispatch';
  webhook_url?: string;
  dispatch_repo?: string;
  dispatch_event_type?: string;
  rule_ids?: number[];
  rule_categories?: string[];
  severity_filter?: string[];
  org_filter?: string[];
  is_catch_all?: boolean;
  rate_limit_per_minute?: number;
  max_retries?: number;
  enabled?: boolean;
}

export interface UpdateTargetRequest {
  name?: string;
  target_type?: 'webhook' | 'dispatch';
  webhook_url?: string;
  dispatch_repo?: string;
  dispatch_event_type?: string;
  rule_ids?: number[];
  rule_categories?: string[];
  severity_filter?: string[];
  org_filter?: string[];
  is_catch_all?: boolean;
  rate_limit_per_minute?: number;
  max_retries?: number;
  enabled?: boolean;
}

export function fetchTargets(): Promise<{ targets: AutomationTarget[] }> {
  return api.get<{ targets: AutomationTarget[] }>('/automation/targets');
}

export function fetchTarget(id: number): Promise<AutomationTarget> {
  return api.get<AutomationTarget>(`/automation/targets/${id}`);
}

export function createTarget(req: CreateTargetRequest): Promise<{ id: number }> {
  return api.post<{ id: number }>('/automation/targets', req);
}

export function updateTarget(id: number, req: UpdateTargetRequest): Promise<{ id: number }> {
  return api.patch<{ id: number }>(`/automation/targets/${id}`, req);
}

export function deleteTarget(id: number): Promise<void> {
  return api.delete<void>(`/automation/targets/${id}`);
}

export function testTarget(
  id: number,
  detectionId?: number,
): Promise<{ status: string; response_code?: number; error?: string }> {
  const body = detectionId !== undefined ? { detection_id: detectionId } : undefined;
  return api.post<{ status: string; response_code?: number; error?: string }>(
    `/automation/targets/${id}/test`,
    body,
  );
}

export function fetchDeliveries(params?: {
  target_id?: number;
  detection_id?: number;
  status?: string;
  limit?: number;
}): Promise<{ deliveries: AutomationDelivery[] }> {
  return api.get<{ deliveries: AutomationDelivery[] }>('/automation/deliveries', params);
}

export function retryDelivery(id: number): Promise<{ id: number }> {
  return api.post<{ id: number }>(`/automation/deliveries/${id}/retry`);
}
