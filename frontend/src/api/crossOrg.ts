import { api } from './client';

export interface CrossOrgTimelineEvent {
  id: number;
  created_at: string;
  action: string;
  actor: string;
  org: string;
  repo: string | null;
  source_ip: string | null;
  country: string | null;
}

export interface CrossOrgCorrelation {
  actor: string;
  orgs: string[];
  org_count: number;
  event_count: number;
  distinct_actions: number;
  first_seen: string;
  last_seen: string;
  risk_score: number;
  top_actions?: string[];
}

export interface CrossOrgTimelineResponse {
  events: CrossOrgTimelineEvent[];
  total: number;
}

export interface CrossOrgCorrelationResponse {
  correlations: CrossOrgCorrelation[];
  total: number;
}

export interface ActorOrgEvent {
  id: number;
  created_at: string;
  action: string;
  repo: string | null;
  source_ip: string | null;
  geo_country_code: string | null;
}

export interface ActorDetailResponse {
  actor: string;
  days: number;
  organizations: string[];
  org_count: number;
  total_events: number;
  timeline_by_org: Record<string, ActorOrgEvent[]>;
}

export function getCrossOrgTimeline(params: {
  actor?: string;
  hours?: number;
  page?: number;
  page_size?: number;
}) {
  return api.get<CrossOrgTimelineResponse>('/cross-org/timeline', params);
}

export function getCrossOrgCorrelations(params?: {
  min_orgs?: number;
  hours?: number;
  page?: number;
  page_size?: number;
}) {
  return api.get<CrossOrgCorrelationResponse>('/cross-org/correlations', params);
}

export function getActorCrossOrgDetail(login: string, days?: number) {
  return api.get<ActorDetailResponse>(`/cross-org/actors/${encodeURIComponent(login)}`, {
    days: days ?? 30,
  });
}
