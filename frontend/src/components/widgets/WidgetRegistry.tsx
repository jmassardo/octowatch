import type { ComponentType } from 'react';
import { AlertTrendsWidget } from './AlertTrendsWidget';
import { ComplianceStatusWidget } from './ComplianceStatusWidget';
import { CopilotUsageWidget } from './CopilotUsageWidget';
import { DetectionSummaryWidget } from './DetectionSummaryWidget';
import { EventVolumeWidget } from './EventVolumeWidget';
import { FailureRatesWidget } from './FailureRatesWidget';
import { IngestionStatusWidget } from './IngestionStatusWidget';
import { MttrChartWidget } from './MttrChartWidget';
import { PostureScoreWidget } from './PostureScoreWidget';
import { RecentEventsWidget } from './RecentEventsWidget';
import { SecurityOverviewWidget } from './SecurityOverviewWidget';
import { SyncHealthWidget } from './SyncHealthWidget';
import { TeamHealthWidget } from './TeamHealthWidget';
import { TopActorsWidget } from './TopActorsWidget';
import { UnifiedSecurityWidget } from './UnifiedSecurityWidget';
import { VelocityMetricsWidget } from './VelocityMetricsWidget';
import { WorkflowHealthWidget } from './WorkflowHealthWidget';

export type WidgetSize = 'sm' | 'md' | 'lg';
export type WidgetCategory = 'security' | 'operations' | 'activity' | 'copilot';
export type DashboardPersona =
  | 'security-analyst'
  | 'engineering-manager'
  | 'platform-engineer'
  | 'executive'
  | 'devops-engineer'
  | 'engineering-lead';

export interface WidgetLayoutItem {
  readonly id: string;
  readonly size: WidgetSize;
}

export interface WidgetDefinition {
  readonly id: string;
  readonly title: string;
  readonly description: string;
  readonly defaultSize: WidgetSize;
  readonly category: WidgetCategory;
  readonly component: ComponentType;
}

export const DASHBOARD_LAYOUT_STORAGE_KEY = 'octowatch-dashboard-layout';

export const WIDGET_CATEGORY_LABELS: Record<WidgetCategory, string> = {
  security: 'Security',
  operations: 'Operations',
  activity: 'Activity',
  copilot: 'Copilot',
};

export const WIDGET_REGISTRY: readonly WidgetDefinition[] = [
  {
    id: 'unified-security',
    title: 'Unified Security',
    description: 'Cross-signal security posture with alert trends and severity breakdowns.',
    defaultSize: 'lg',
    category: 'security',
    component: UnifiedSecurityWidget,
  },
  {
    id: 'security-overview',
    title: 'Security Overview',
    description: 'Active detections by severity with direct drill-down into threats.',
    defaultSize: 'md',
    category: 'security',
    component: SecurityOverviewWidget,
  },
  {
    id: 'detection-summary',
    title: 'Detection Summary',
    description: 'Recent detection counts with severity emphasis for fast triage.',
    defaultSize: 'md',
    category: 'security',
    component: DetectionSummaryWidget,
  },
  {
    id: 'sync-health',
    title: 'Sync Health',
    description: 'Current sync status, monitoring coverage, and next scheduled refresh.',
    defaultSize: 'sm',
    category: 'operations',
    component: SyncHealthWidget,
  },
  {
    id: 'ingestion-status',
    title: 'Ingestion Status',
    description: 'Real-time ingestion pipeline health: events/sec, last event time, and worker status.',
    defaultSize: 'sm',
    category: 'operations',
    component: IngestionStatusWidget,
  },
  {
    id: 'event-volume',
    title: 'Event Volume',
    description: '24-hour event activity trend to spot ingestion shifts or spikes.',
    defaultSize: 'md',
    category: 'activity',
    component: EventVolumeWidget,
  },
  {
    id: 'top-actors',
    title: 'Top Actors',
    description: 'Most active humans in recent audit events for investigation context.',
    defaultSize: 'sm',
    category: 'activity',
    component: TopActorsWidget,
  },
  {
    id: 'copilot-usage',
    title: 'Copilot Usage',
    description: 'Adoption snapshot showing overall usage and power-user concentration.',
    defaultSize: 'sm',
    category: 'copilot',
    component: CopilotUsageWidget,
  },
  {
    id: 'alert-trends',
    title: 'Alert Trends',
    description: 'Security alert volume over time grouped by severity.',
    defaultSize: 'md',
    category: 'security',
    component: AlertTrendsWidget,
  },
  {
    id: 'mttr-chart',
    title: 'MTTR Chart',
    description: 'Mean time to resolve security detections by severity band.',
    defaultSize: 'md',
    category: 'security',
    component: MttrChartWidget,
  },
  {
    id: 'posture-score',
    title: 'Posture Score',
    description: 'Overall security posture score across monitored organizations.',
    defaultSize: 'sm',
    category: 'security',
    component: PostureScoreWidget,
  },
  {
    id: 'compliance-status',
    title: 'Compliance Status',
    description: 'Compliance framework adherence summary with pass/fail breakdown.',
    defaultSize: 'sm',
    category: 'security',
    component: ComplianceStatusWidget,
  },
  {
    id: 'workflow-health',
    title: 'Workflow Health',
    description: 'GitHub Actions workflow success rates and health indicators.',
    defaultSize: 'md',
    category: 'operations',
    component: WorkflowHealthWidget,
  },
  {
    id: 'failure-rates',
    title: 'Failure Rates',
    description: 'CI/CD pipeline failure rates by repository and workflow.',
    defaultSize: 'md',
    category: 'operations',
    component: FailureRatesWidget,
  },
  {
    id: 'recent-events',
    title: 'Recent Events',
    description: 'Stream of the latest audit events with action type and actor details.',
    defaultSize: 'lg',
    category: 'activity',
    component: RecentEventsWidget,
  },
  {
    id: 'velocity-metrics',
    title: 'Velocity Metrics',
    description: 'Development velocity tracking including PR throughput and cycle time.',
    defaultSize: 'md',
    category: 'activity',
    component: VelocityMetricsWidget,
  },
  {
    id: 'team-health',
    title: 'Team Health',
    description: 'Aggregated team health indicators across repositories and workflows.',
    defaultSize: 'md',
    category: 'activity',
    component: TeamHealthWidget,
  },
];

export const PERSONA_WIDGET_PRESETS: Record<DashboardPersona, readonly string[]> = {
  'security-analyst': [
    'unified-security',
    'detection-summary',
    'alert-trends',
    'mttr-chart',
    'security-overview',
    'posture-score',
    'top-actors',
    'recent-events',
  ],
  'engineering-manager': [
    'velocity-metrics',
    'team-health',
    'copilot-usage',
    'event-volume',
    'workflow-health',
    'failure-rates',
  ],
  'platform-engineer': [
    'sync-health',
    'ingestion-status',
    'workflow-health',
    'failure-rates',
    'event-volume',
    'top-actors',
    'copilot-usage',
    'recent-events',
  ],
  executive: [
    'posture-score',
    'compliance-status',
    'unified-security',
    'velocity-metrics',
    'copilot-usage',
    'team-health',
  ],
  // Legacy presets kept for backward compatibility
  'devops-engineer': ['sync-health', 'event-volume', 'top-actors', 'copilot-usage'],
  'engineering-lead': ['copilot-usage', 'event-volume', 'unified-security', 'sync-health'],
};

const WIDGET_REGISTRY_BY_ID = Object.fromEntries(
  WIDGET_REGISTRY.map((widget) => [widget.id, widget]),
);

function isWidgetSize(value: unknown): value is WidgetSize {
  return value === 'sm' || value === 'md' || value === 'lg';
}

export function getWidgetDefinition(id: string): WidgetDefinition | null {
  return WIDGET_REGISTRY_BY_ID[id] ?? null;
}

export function createDashboardLayout(widgetIds: readonly string[]): WidgetLayoutItem[] {
  const seen = new Set<string>();
  return widgetIds.flatMap((widgetId) => {
    const widget = getWidgetDefinition(widgetId);
    if (!widget || seen.has(widgetId)) return [];
    seen.add(widgetId);
    return [{ id: widget.id, size: widget.defaultSize }];
  });
}

export function loadDashboardLayout(): WidgetLayoutItem[] {
  try {
    const raw = localStorage.getItem(DASHBOARD_LAYOUT_STORAGE_KEY);
    if (!raw) return [];

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    return parsed.flatMap((item) => {
      if (
        item &&
        typeof item === 'object' &&
        typeof item.id === 'string' &&
        getWidgetDefinition(item.id) &&
        isWidgetSize((item as { size?: unknown }).size)
      ) {
        return [{ id: item.id, size: item.size } satisfies WidgetLayoutItem];
      }
      return [];
    });
  } catch {
    return [];
  }
}

export function saveDashboardLayout(layout: readonly WidgetLayoutItem[]): void {
  localStorage.setItem(DASHBOARD_LAYOUT_STORAGE_KEY, JSON.stringify(layout));
}
