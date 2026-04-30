import { api } from './client';

/* ──────────────── Types ──────────────── */

export interface AuthMethodConfig {
  id: number;
  method_name: string;
  display_name: string;
  enabled: boolean;
  config_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AuthMethodUpdate {
  enabled?: boolean;
  config_json?: Record<string, unknown>;
}

export interface SAMLTestResult {
  success: boolean;
  message: string;
  details?: Record<string, unknown>;
}

export interface SessionPolicySetting {
  id: number;
  policy_key: string;
  policy_value: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface SessionPolicyUpdate {
  policy_value: string;
  description?: string;
}

/* ──────────────── Auth Method Endpoints ──────────────── */

export async function listAuthMethods(): Promise<AuthMethodConfig[]> {
  return api.get('/admin/auth/methods');
}

export async function updateAuthMethod(
  methodName: string,
  body: AuthMethodUpdate,
): Promise<AuthMethodConfig> {
  return api.patch(`/admin/auth/methods/${methodName}`, body);
}

export async function testSAMLConnection(): Promise<SAMLTestResult> {
  return api.post('/admin/auth/saml/test', {});
}

export async function getSAMLMetadata(): Promise<string> {
  return api.get('/admin/auth/saml/sp-metadata');
}

/* ──────────────── Session Policy Endpoints ──────────────── */

export async function listSessionPolicies(): Promise<SessionPolicySetting[]> {
  return api.get('/admin/auth/session-policies');
}

export async function updateSessionPolicy(
  key: string,
  body: SessionPolicyUpdate,
): Promise<SessionPolicySetting> {
  return api.patch(`/admin/auth/session-policies/${key}`, body);
}
