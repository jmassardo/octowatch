import { api } from './client';
import type {
  ComplianceSummary,
  FrameworkDetail,
  PolicyCheckResults,
  GDPRSummary,
} from '../types/compliance';

export function getComplianceSummary(org?: string): Promise<ComplianceSummary> {
  return api.get<ComplianceSummary>('/compliance/summary', { org });
}

export function getFrameworkDetail(name: string, org?: string): Promise<FrameworkDetail> {
  return api.get<FrameworkDetail>(`/compliance/framework/${name}`, { org });
}

export function getPolicyChecks(org?: string): Promise<PolicyCheckResults> {
  return api.get<PolicyCheckResults>('/compliance/policy-checks', { org });
}

export function runPolicyChecks(org?: string): Promise<PolicyCheckResults> {
  return api.post<PolicyCheckResults>('/compliance/policy-checks/run', { org });
}

export function getGDPRSummary(org?: string): Promise<GDPRSummary> {
  return api.get<GDPRSummary>('/compliance/gdpr/summary', { org });
}
