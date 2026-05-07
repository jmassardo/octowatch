import { api } from './client';

/* ── Types ──────────────────────────────────────────────────────────────── */

export interface ChainMember {
  readonly detection_id: number;
  readonly correlation_type: string;
  readonly confidence: number;
  readonly added_at: string;
  readonly detection_title: string;
  readonly detection_severity: string;
  readonly detection_status: string;
  readonly detection_actor: string | null;
  readonly detection_triggered_at: string;
}

export interface CorrelationChain {
  readonly chain_id: string;
  readonly title: string;
  readonly status: string;
  readonly severity: string;
  readonly assignee: string | null;
  readonly notes: string | null;
  readonly created_at: string;
  readonly updated_at: string;
  readonly resolved_at: string | null;
  readonly members: readonly ChainMember[];
  readonly detection_count: number;
}

export interface CorrelationChainSummary {
  readonly chain_id: string;
  readonly title: string;
  readonly status: string;
  readonly severity: string;
  readonly assignee: string | null;
  readonly created_at: string;
  readonly updated_at: string;
  readonly resolved_at: string | null;
  readonly detection_count: number;
}

export interface CorrelationChainListResponse {
  readonly items: readonly CorrelationChainSummary[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
  readonly has_next: boolean;
}

export interface ChainMetrics {
  readonly active_chains: number;
  readonly avg_chain_size: number;
  readonly chains_resolved_today: number;
  readonly total_chains: number;
}

export interface CorrelationRunResult {
  readonly detection_id: number;
  readonly chain_id: string | null;
  readonly match_count: number;
  readonly created_new_chain: boolean;
}

export interface ChainListParams {
  status?: string;
  severity?: string;
  assignee?: string;
  page?: number;
  page_size?: number;
}

export interface UpdateChainRequest {
  status?: string;
  assignee?: string;
  title?: string;
  notes?: string;
}

export interface MergeChainRequest {
  source_chain_id: string;
}

/* ── API calls ──────────────────────────────────────────────────────────── */

export function listChains(params: ChainListParams = {}): Promise<CorrelationChainListResponse> {
  return api.get<CorrelationChainListResponse>(
    '/correlations/chains',
    params as Record<string, string | number | boolean | undefined>,
  );
}

export function getChainMetrics(): Promise<ChainMetrics> {
  return api.get<ChainMetrics>('/correlations/chains/metrics');
}

export function getChain(chainId: string): Promise<CorrelationChain> {
  return api.get<CorrelationChain>(`/correlations/chains/${chainId}`);
}

export function updateChain(chainId: string, req: UpdateChainRequest): Promise<CorrelationChain> {
  return api.put<CorrelationChain>(`/correlations/chains/${chainId}`, req);
}

export function mergeChain(chainId: string, req: MergeChainRequest): Promise<CorrelationChain> {
  return api.post<CorrelationChain>(`/correlations/chains/${chainId}/merge`, req);
}

export function runCorrelation(detectionId: number): Promise<CorrelationRunResult> {
  return api.post<CorrelationRunResult>(`/correlations/run/${detectionId}`);
}
