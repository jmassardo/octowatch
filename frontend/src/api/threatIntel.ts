import { api } from './client';

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ThreatIntelIndicator {
  readonly id: number;
  readonly indicator_type: string;
  readonly value: string;
  readonly source: string;
  readonly confidence: number;
  readonly active: boolean;
  readonly added_at: string;
  readonly added_by: string;
  readonly expires_at: string | null;
  readonly notes: string | null;
  readonly feed_id: number | null;
  readonly metadata_json: Record<string, unknown> | null;
}

export interface IndicatorListResponse {
  readonly items: readonly ThreatIntelIndicator[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
}

export interface IndicatorCreateRequest {
  indicator_type: string;
  value: string;
  source: string;
  confidence?: number;
  expires_at?: string | null;
  notes?: string | null;
}

export interface IndicatorUpdateRequest {
  value?: string;
  source?: string;
  confidence?: number;
  active?: boolean;
  expires_at?: string | null;
  notes?: string | null;
}

export interface ThreatIntelFeed {
  readonly id: number;
  readonly name: string;
  readonly url: string;
  readonly feed_type: string;
  readonly enabled: boolean;
  readonly refresh_interval_minutes: number;
  readonly last_fetched_at: string | null;
  readonly last_fetch_status: string | null;
  readonly last_indicator_count: number | null;
  readonly created_by: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface FeedListResponse {
  readonly items: readonly ThreatIntelFeed[];
}

export interface FeedCreateRequest {
  name: string;
  url: string;
  feed_type?: string;
  refresh_interval_minutes?: number;
}

export interface FeedUpdateRequest {
  name?: string;
  url?: string;
  feed_type?: string;
  refresh_interval_minutes?: number;
  enabled?: boolean;
}

export interface FeedRefreshResponse {
  readonly feed_id: number;
  readonly status: string;
  readonly indicator_count: number | null;
  readonly message: string;
}

export interface BulkIndicatorItem {
  indicator_type: string;
  value: string;
  source?: string;
  confidence?: number;
}

export interface BulkIndicatorResponse {
  readonly created: number;
  readonly duplicates: number;
  readonly errors: number;
}

export interface ThreatIntelMatch {
  readonly detection_id: number;
  readonly title: string;
  readonly severity: string;
  readonly status: string;
  readonly actor: string | null;
  readonly org: string | null;
  readonly repo: string | null;
  readonly triggered_at: string;
  readonly matched_indicator_value: string | null;
  readonly matched_indicator_type: string | null;
  readonly matched_feed_name: string | null;
}

export interface MatchListResponse {
  readonly items: readonly ThreatIntelMatch[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
  readonly total_24h: number;
  readonly unique_indicators: number;
  readonly top_feed: string | null;
}

export interface ThreatIntelAnalytics {
  readonly total_feeds: number;
  readonly active_feeds: number;
  readonly total_indicators: number;
  readonly active_indicators: number;
  readonly matches_30d: number;
  readonly coverage_score: number;
  readonly matches_over_time: readonly { date: string; count: number }[];
  readonly matches_by_feed: readonly { name: string; count: number }[];
  readonly indicator_type_distribution: readonly { type: string; count: number }[];
}

// ─── Indicators API ──────────────────────────────────────────────────────────

export interface IndicatorListParams {
  indicator_type?: string;
  active_only?: boolean;
  search?: string;
  page?: number;
  page_size?: number;
}

export function listIndicators(params: IndicatorListParams = {}): Promise<IndicatorListResponse> {
  return api.get<IndicatorListResponse>(
    '/threat-intel/indicators',
    params as Record<string, string | number | boolean | undefined>,
  );
}

export function createIndicator(body: IndicatorCreateRequest): Promise<ThreatIntelIndicator> {
  return api.post<ThreatIntelIndicator>('/threat-intel/indicators', body);
}

export function updateIndicator(
  id: number,
  body: IndicatorUpdateRequest,
): Promise<ThreatIntelIndicator> {
  return api.patch<ThreatIntelIndicator>(`/threat-intel/indicators/${id}`, body);
}

export function deleteIndicator(id: number): Promise<void> {
  return api.delete<void>(`/threat-intel/indicators/${id}`);
}

export function bulkCreateIndicators(
  indicators: BulkIndicatorItem[],
): Promise<BulkIndicatorResponse> {
  return api.post<BulkIndicatorResponse>('/threat-intel/indicators/bulk', { indicators });
}

// ─── Feeds API ───────────────────────────────────────────────────────────────

export function listFeeds(): Promise<FeedListResponse> {
  return api.get<FeedListResponse>('/threat-intel/feeds');
}

export function createFeed(body: FeedCreateRequest): Promise<ThreatIntelFeed> {
  return api.post<ThreatIntelFeed>('/threat-intel/feeds', body);
}

export function updateFeed(id: number, body: FeedUpdateRequest): Promise<ThreatIntelFeed> {
  return api.patch<ThreatIntelFeed>(`/threat-intel/feeds/${id}`, body);
}

export function deleteFeed(id: number): Promise<void> {
  return api.delete<void>(`/threat-intel/feeds/${id}`);
}

export function refreshFeed(id: number): Promise<FeedRefreshResponse> {
  return api.post<FeedRefreshResponse>(`/threat-intel/feeds/${id}/refresh`);
}

// ─── Matches API ─────────────────────────────────────────────────────────────

export interface MatchListParams {
  page?: number;
  page_size?: number;
}

export function listMatches(params: MatchListParams = {}): Promise<MatchListResponse> {
  return api.get<MatchListResponse>(
    '/threat-intel/matches',
    params as Record<string, string | number | boolean | undefined>,
  );
}

// ─── Analytics API ───────────────────────────────────────────────────────────

export function getAnalytics(): Promise<ThreatIntelAnalytics> {
  return api.get<ThreatIntelAnalytics>('/threat-intel/analytics');
}
