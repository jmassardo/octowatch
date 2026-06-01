export type MetricCategory = 'security' | 'operations' | 'engineering' | 'compliance';
export type StatPillFormat = 'number' | 'percentage' | 'duration' | 'count';
export type ThresholdDirection = 'higher-is-worse' | 'lower-is-worse';

export interface ThresholdConfig {
  warning: number;
  critical: number;
}

export interface StatPillMetricDefinition {
  id: string;
  category: MetricCategory;
  label: string;
  icon: string;
  path: string;
  format: StatPillFormat;
  defaultThresholds: ThresholdConfig;
  thresholdDirection: ThresholdDirection;
  thresholdUnitLabel?: string;
}

export const STAT_PILL_CATEGORIES: ReadonlyArray<{ id: MetricCategory; label: string }> = [
  { id: 'security', label: 'Security' },
  { id: 'operations', label: 'Operations' },
  { id: 'engineering', label: 'Engineering' },
  { id: 'compliance', label: 'Compliance' },
];

export const STAT_PILL_REGISTRY: Record<string, StatPillMetricDefinition> = {
  'open-detections': {
    id: 'open-detections',
    category: 'security',
    label: 'Open Detections',
    icon: '🔍',
    path: '/threats',
    format: 'count',
    defaultThresholds: { warning: 5, critical: 15 },
    thresholdDirection: 'higher-is-worse',
  },
  'critical-detections': {
    id: 'critical-detections',
    category: 'security',
    label: 'Critical Detections',
    icon: '🚨',
    path: '/threats/open?severity=critical',
    format: 'count',
    defaultThresholds: { warning: 1, critical: 5 },
    thresholdDirection: 'higher-is-worse',
  },
  'unresolved-threats': {
    id: 'unresolved-threats',
    category: 'security',
    label: 'Unresolved Threats',
    icon: '🧯',
    path: '/threats/investigating',
    format: 'count',
    defaultThresholds: { warning: 3, critical: 10 },
    thresholdDirection: 'higher-is-worse',
  },
  'secret-alerts': {
    id: 'secret-alerts',
    category: 'security',
    label: 'Secret Alerts',
    icon: '🔐',
    path: '/advanced-security/secrets',
    format: 'count',
    defaultThresholds: { warning: 1, critical: 5 },
    thresholdDirection: 'higher-is-worse',
  },
  'ghas-coverage': {
    id: 'ghas-coverage',
    category: 'security',
    label: 'GHAS Coverage %',
    icon: '🛡️',
    path: '/advanced-security',
    format: 'percentage',
    defaultThresholds: { warning: 80, critical: 60 },
    thresholdDirection: 'lower-is-worse',
    thresholdUnitLabel: '%',
  },
  'sync-health': {
    id: 'sync-health',
    category: 'operations',
    label: 'Sync Health',
    icon: '💚',
    path: '/health/operations',
    format: 'percentage',
    defaultThresholds: { warning: 95, critical: 80 },
    thresholdDirection: 'lower-is-worse',
    thresholdUnitLabel: '%',
  },
  'events-per-hour': {
    id: 'events-per-hour',
    category: 'operations',
    label: 'Events/hour',
    icon: '⚡',
    path: '/events',
    format: 'number',
    defaultThresholds: { warning: 25, critical: 5 },
    thresholdDirection: 'lower-is-worse',
  },
  'failed-syncs': {
    id: 'failed-syncs',
    category: 'operations',
    label: 'Failed Syncs',
    icon: '❌',
    path: '/health/maintenance-signals',
    format: 'count',
    defaultThresholds: { warning: 1, critical: 5 },
    thresholdDirection: 'higher-is-worse',
  },
  'active-orgs': {
    id: 'active-orgs',
    category: 'operations',
    label: 'Active Orgs',
    icon: '🏢',
    path: '/health/platform-security',
    format: 'count',
    defaultThresholds: { warning: 1, critical: 0 },
    thresholdDirection: 'lower-is-worse',
  },
  'webhook-lag': {
    id: 'webhook-lag',
    category: 'operations',
    label: 'Webhook Lag',
    icon: '⏱️',
    path: '/health/operations',
    format: 'duration',
    defaultThresholds: { warning: 10, critical: 30 },
    thresholdDirection: 'higher-is-worse',
    thresholdUnitLabel: 'm',
  },
  'copilot-adoption': {
    id: 'copilot-adoption',
    category: 'engineering',
    label: 'Copilot Adoption %',
    icon: '🤖',
    path: '/copilot/adoption',
    format: 'percentage',
    defaultThresholds: { warning: 60, critical: 35 },
    thresholdDirection: 'lower-is-worse',
    thresholdUnitLabel: '%',
  },
  'active-developers': {
    id: 'active-developers',
    category: 'engineering',
    label: 'Active Developers',
    icon: '👩‍💻',
    path: '/devactivity',
    format: 'count',
    defaultThresholds: { warning: 5, critical: 2 },
    thresholdDirection: 'lower-is-worse',
  },
  'pr-merge-time': {
    id: 'pr-merge-time',
    category: 'engineering',
    label: 'PR Merge Time',
    icon: '🕒',
    path: '/health/maintenance',
    format: 'duration',
    defaultThresholds: { warning: 24 * 60, critical: 72 * 60 },
    thresholdDirection: 'higher-is-worse',
    thresholdUnitLabel: 'm',
  },
  'workflow-success-rate': {
    id: 'workflow-success-rate',
    category: 'engineering',
    label: 'Workflow Success Rate',
    icon: '✅',
    path: '/velocity',
    format: 'percentage',
    defaultThresholds: { warning: 90, critical: 75 },
    thresholdDirection: 'lower-is-worse',
    thresholdUnitLabel: '%',
  },
  'compliance-score': {
    id: 'compliance-score',
    category: 'compliance',
    label: 'Compliance Score',
    icon: '📊',
    path: '/compliance',
    format: 'percentage',
    defaultThresholds: { warning: 80, critical: 60 },
    thresholdDirection: 'lower-is-worse',
    thresholdUnitLabel: '%',
  },
  'policy-violations': {
    id: 'policy-violations',
    category: 'compliance',
    label: 'Policy Violations',
    icon: '📋',
    path: '/compliance',
    format: 'count',
    defaultThresholds: { warning: 1, critical: 5 },
    thresholdDirection: 'higher-is-worse',
  },
  'overdue-reviews': {
    id: 'overdue-reviews',
    category: 'compliance',
    label: 'Overdue Reviews',
    icon: '📅',
    path: '/health/maintenance',
    format: 'count',
    defaultThresholds: { warning: 5, critical: 10 },
    thresholdDirection: 'higher-is-worse',
  },
  'branch-protection': {
    id: 'branch-protection',
    category: 'compliance',
    label: 'Branch Protection %',
    icon: '🌿',
    path: '/health/platform-security',
    format: 'percentage',
    defaultThresholds: { warning: 85, critical: 70 },
    thresholdDirection: 'lower-is-worse',
    thresholdUnitLabel: '%',
  },
};

export const DEFAULT_ENABLED_PILLS = [
  'open-detections',
  'secret-alerts',
  'ghas-coverage',
  'sync-health',
  'events-per-hour',
  'workflow-success-rate',
  'copilot-adoption',
  'active-developers',
  'compliance-score',
] as const;

export const DEFAULT_PILL_ORDER = Object.keys(STAT_PILL_REGISTRY);

export function getMetricsByCategory(category: MetricCategory): StatPillMetricDefinition[] {
  return DEFAULT_PILL_ORDER.map((id) => STAT_PILL_REGISTRY[id]!).filter(
    (metric) => metric.category === category,
  );
}

export function getAllMetrics(): StatPillMetricDefinition[] {
  return DEFAULT_PILL_ORDER.map((id) => STAT_PILL_REGISTRY[id]!);
}
