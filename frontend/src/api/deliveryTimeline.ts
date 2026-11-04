import { api } from './client';

// ── Types ────────────────────────────────────────────────────────────────────

export interface DeliveryTimelineItem {
  id: string;
  pr_number: number;
  repo: string;
  org: string;
  issue_numbers: number[];
  backlog_hours: number | null;
  dev_hours: number | null;
  review_hours: number | null;
  deploy_hours: number | null;
  total_hours: number | null;
  pr_merged_at: string | null;
  created_at: string;
}

export interface DeliveryTimelineStats {
  total_prs: number;
  avg_backlog_hours: number | null;
  avg_dev_hours: number | null;
  avg_review_hours: number | null;
  avg_deploy_hours: number | null;
  avg_total_hours: number | null;
  median_total_hours: number | null;
  p95_total_hours: number | null;
  bottleneck_phase: string | null;
  timelines: DeliveryTimelineItem[];
}

export interface DeliveryTimelineParams {
  org?: string;
  repo?: string;
  days?: number;
  team_id?: number;
}

export function getDeliveryTimeline(
  params: DeliveryTimelineParams = {},
): Promise<DeliveryTimelineStats> {
  return api.get<DeliveryTimelineStats>('/metrics/delivery-timeline', params);
}
