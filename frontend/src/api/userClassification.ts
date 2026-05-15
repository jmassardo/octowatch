import { api } from './client';

/** A single persona bucket in the summary response. */
export interface PersonaSummary {
  persona: string;
  user_count: number;
  avg_confidence: number;
  total_events: number;
}

/** Summary response from GET /user-classification/summary. */
export interface ClassificationSummaryResponse {
  personas: PersonaSummary[];
  total_users: number;
  dormant_count: number;
  dormant_pct: number;
  power_user_count: number;
  power_user_pct: number;
}

/** A single classified user record. */
export interface ClassifiedUser {
  id: number;
  user_login: string;
  org: string;
  persona: string;
  confidence_score: number;
  event_count: number;
  surfaces: string[];
  analysis_window_days: number;
  classified_at: string | null;
}

/** Paginated user list from GET /user-classification/users. */
export interface ClassifiedUsersResponse {
  users: ClassifiedUser[];
  total: number;
  page: number;
  page_size: number;
}

/** Response from POST /user-classification/run. */
export interface ClassificationRunResponse {
  status: string;
  orgs_processed: number;
  users_classified: number;
}

/** Fetch the persona distribution summary. */
export function getClassificationSummary(): Promise<ClassificationSummaryResponse> {
  return api.get<ClassificationSummaryResponse>('/user-classification/summary');
}

/** Fetch paginated classified users with optional filters. */
export function getClassifiedUsers(params?: {
  persona?: string;
  page?: number;
  page_size?: number;
}): Promise<ClassifiedUsersResponse> {
  const queryParams: Record<string, string | number> = {};
  if (params?.persona) queryParams.persona = params.persona;
  if (params?.page) queryParams.page = params.page;
  if (params?.page_size) queryParams.page_size = params.page_size;
  return api.get<ClassifiedUsersResponse>('/user-classification/users', queryParams);
}

/** Trigger a manual classification run. */
export function triggerClassificationRun(windowDays?: number): Promise<ClassificationRunResponse> {
  const params: Record<string, number> = {};
  if (windowDays !== undefined) params.window_days = windowDays;
  return api.post<ClassificationRunResponse>(
    `/user-classification/run${Object.keys(params).length ? `?window_days=${params.window_days}` : ''}`,
  );
}
