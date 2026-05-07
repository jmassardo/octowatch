import { api } from './client';

/* ── Response types ─────────────────────────────────────────────────────── */

export interface SupplyChainPosture {
  score: number;
  unpinned_actions: number;
  dependency_alerts: number;
  risky_workflows: number;
  rules_active: number;
  total_detections: number;
  critical_detections: number;
  recent_risks: SupplyChainRisk[];
}

export interface SupplyChainRisk {
  id: number;
  title: string;
  severity: string;
  status: string;
  org: string | null;
  repo: string | null;
  triggered_at: string | null;
  rule_slug: string;
}

export interface RiskSummary {
  total_risks: number;
  by_severity: Record<string, number>;
  by_type: Record<string, number>;
  top_repos: { repo: string; count: number }[];
}

export interface SupplyChainRule {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  severity: string;
  confidence: string;
  logic_type: string;
  enabled: boolean;
  detection_count: number;
}

export interface RulesListResponse {
  rules: SupplyChainRule[];
  total: number;
}

export interface WorkflowFinding {
  rule_slug: string;
  title: string;
  severity: string;
  confidence: string;
  line: number | null;
  detail: string;
  recommendation: string;
}

export interface AnalyzeWorkflowResponse {
  findings: WorkflowFinding[];
  total_findings: number;
  risk_level: string;
}

/* ── API functions ──────────────────────────────────────────────────────── */

export function getSupplyChainPosture(): Promise<SupplyChainPosture> {
  return api.get<SupplyChainPosture>('/supply-chain/posture');
}

export function getSupplyChainRisks(): Promise<RiskSummary> {
  return api.get<RiskSummary>('/supply-chain/risks');
}

export function getSupplyChainRules(): Promise<RulesListResponse> {
  return api.get<RulesListResponse>('/supply-chain/rules');
}

export function analyzeWorkflow(content: string): Promise<AnalyzeWorkflowResponse> {
  return api.post<AnalyzeWorkflowResponse>('/supply-chain/analyze-workflow', { content });
}
