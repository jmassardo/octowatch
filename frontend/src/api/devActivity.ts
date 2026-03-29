import { api } from './client';

export interface GitActorStat {
  actor: string;
  count: number;
  is_bot?: boolean;
  repos?: string[];
}

export interface DailyGitTrend {
  date: string;
  clones: number;
  pushes: number;
  fetches: number;
}

export interface ApiActorStat {
  actor: string;
  count: number;
}

export interface ApiEndpointStat {
  endpoint: string;
  count: number;
}

export interface DailyApiTrend {
  date: string;
  requests: number;
}

export interface UsageStatsResponse {
  git_stats: {
    total_clones: number;
    total_pushes: number;
    total_fetches: number;
    top_cloners: GitActorStat[];
    top_pushers: GitActorStat[];
    daily_trend: DailyGitTrend[];
  };
  api_stats: {
    total_requests: number;
    top_users: ApiActorStat[];
    top_endpoints: ApiEndpointStat[];
    daily_trend: DailyApiTrend[];
    available: boolean;
  };
  bot_vs_human: {
    bot_events: number;
    human_events: number;
    bot_actors: string[];
    human_actors: string[];
  };
}

export function getUsageStats(): Promise<UsageStatsResponse> {
  return api.get<UsageStatsResponse>('/dev-activity/usage-stats');
}
