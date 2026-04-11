import { api } from './client';

/** Actor profile returned by GET /actors/:login */
export interface ActorProfile {
  readonly login: string;
  readonly avatar_url: string;
  readonly display_name: string | null;
  readonly roles: readonly string[];
  readonly org_memberships: readonly string[];
  readonly detection_count: number;
  readonly event_count: number;
  readonly risk_score: number;
  readonly risk_level: string;
  readonly first_seen: string | null;
  readonly last_seen: string | null;
}

export interface ActorEvent {
  readonly id: number;
  readonly created_at: string;
  readonly action: string;
  readonly namespace: string;
  readonly org: string | null;
  readonly repo: string | null;
  readonly source_ip: string | null;
  readonly geo_country_code: string | null;
  readonly geo_city: string | null;
}

export interface ActorEventListResponse {
  readonly items: readonly ActorEvent[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
  readonly has_next: boolean;
}

export interface ActorDetection {
  readonly id: number;
  readonly title: string;
  readonly severity: string;
  readonly status: string;
  readonly triggered_at: string;
  readonly rule_name: string | null;
  readonly org: string | null;
  readonly repo: string | null;
}

export interface ActorDetectionListResponse {
  readonly items: readonly ActorDetection[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
  readonly has_next: boolean;
}

export interface ActorLocation {
  readonly country_code: string | null;
  readonly city: string | null;
  readonly latitude: number | null;
  readonly longitude: number | null;
  readonly event_count: number;
  readonly last_seen: string | null;
}

export interface ActorLocationsResponse {
  readonly locations: readonly ActorLocation[];
  readonly total_events: number;
}

export function getActorProfile(login: string): Promise<ActorProfile> {
  return api.get<ActorProfile>(`/actors/${encodeURIComponent(login)}`);
}

export function getActorEvents(
  login: string,
  params: { page?: number; page_size?: number } = {},
): Promise<ActorEventListResponse> {
  return api.get<ActorEventListResponse>(
    `/actors/${encodeURIComponent(login)}/events`,
    params as Record<string, string | number | boolean | undefined>,
  );
}

export function getActorDetections(
  login: string,
  params: { page?: number; page_size?: number } = {},
): Promise<ActorDetectionListResponse> {
  return api.get<ActorDetectionListResponse>(
    `/actors/${encodeURIComponent(login)}/detections`,
    params as Record<string, string | number | boolean | undefined>,
  );
}

export function getActorLocations(
  login: string,
): Promise<ActorLocationsResponse> {
  return api.get<ActorLocationsResponse>(
    `/actors/${encodeURIComponent(login)}/locations`,
  );
}
