import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { listDetections } from '../../api/detections';
import { listEvents } from '../../api/events';
import { getActionsVolumeReport } from '../../api/reports';
import {
  getCoverageGrowth,
  getHealthScore,
  getPlatformSecurity,
  getStalePrs,
  getSystemHealth,
  getUnifiedSecurity,
  getUnhealthyHooks,
} from '../../api/healthSignals';
import { getComplianceSummary, getPolicyChecks } from '../../api/compliance';
import { getCopilotAdoption } from '../../api/copilotMetrics';
import { getDevelopers } from '../../api/devActivity';
import { Card, CardHeader } from '../../components/primitives/Card';
import { PageHeader } from '../../components/common/PageHeader';
import { StatPill } from '../../components/widgets/StatPill';
import { StatPillConfigDrawer } from '../../components/widgets/StatPillConfig';
import {
  STAT_PILL_REGISTRY,
  type ThresholdConfig,
} from '../../components/widgets/statPillRegistry';
import {
  loadStatPillConfig,
  saveStatPillConfig,
  type StatPillConfig,
} from '../../components/widgets/statPillConfigStorage';
import { ExecutiveView } from './ExecutiveView';
import { SecurityView } from './SecurityView';
import { CiCdView } from './CiCdView';
import { SecurityOverviewWidget } from '../../components/widgets/SecurityOverviewWidget';
import { useOrg } from '../../hooks/useOrg';
import type { ActionsVolumeBucket } from '../../types/reports';
import type { EventResponse } from '../../types/events';
import { formatRelative } from '../../utils/dates';
import styles from './Dashboard.module.css';

type DashboardView = 'operations' | 'executive' | 'security' | 'cicd';

type MetricVariant = 'default' | 'success' | 'warning' | 'danger';

interface MetricState {
  rawValue: number;
  trend?: number;
  isLoading: boolean;
  hasError: boolean;
}

function ClickableValue({
  children,
  onClick,
  label,
}: {
  children: React.ReactNode;
  onClick: () => void;
  label: string;
}) {
  return (
    <span
      role="button"
      tabIndex={0}
      aria-label={label}
      className={styles.clickableValue}
      onClick={onClick}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onClick();
        }
      }}
    >
      {children}
    </span>
  );
}

function formatCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function average(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function percentChange(current: number, previous: number): number | undefined {
  if (!Number.isFinite(current) || !Number.isFinite(previous) || previous === 0) return undefined;
  return Number((((current - previous) / Math.abs(previous)) * 100).toFixed(1));
}

function latestDelta(values: number[]): number | undefined {
  if (values.length < 2) return undefined;
  const previous = values[values.length - 2];
  const current = values[values.length - 1];
  if (previous == null || current == null) return undefined;
  return percentChange(current, previous);
}

function getThresholdVariant(
  rawValue: number,
  thresholds: ThresholdConfig,
  direction: 'higher-is-worse' | 'lower-is-worse',
): MetricVariant {
  if (!Number.isFinite(rawValue)) return 'default';

  if (direction === 'higher-is-worse') {
    const warning = Math.min(thresholds.warning, thresholds.critical);
    const critical = Math.max(thresholds.warning, thresholds.critical);
    if (rawValue >= critical) return 'danger';
    if (rawValue >= warning) return 'warning';
    return 'success';
  }

  const warning = Math.max(thresholds.warning, thresholds.critical);
  const critical = Math.min(thresholds.warning, thresholds.critical);
  if (rawValue <= critical) return 'danger';
  if (rawValue <= warning) return 'warning';
  return 'success';
}

function computeEventsPerHour(items: readonly EventResponse[] | undefined, total: number | undefined) {
  if (!items || items.length === 0) {
    return { rate: total ? total / 24 : 0, trend: undefined as number | undefined };
  }

  const sorted = [...items].sort((a, b) => a.created_at.localeCompare(b.created_at));
  const oldest = new Date(sorted[0]!.created_at).getTime();
  const newest = new Date(sorted[sorted.length - 1]!.created_at).getTime();
  const spanHours = Math.max((newest - oldest) / 3_600_000, 1);
  const rate = sorted.length / spanHours;

  if (spanHours < 2) {
    return { rate, trend: undefined as number | undefined };
  }

  const midpoint = oldest + (newest - oldest) / 2;
  const previousCount = sorted.filter((event) => new Date(event.created_at).getTime() <= midpoint).length;
  const recentCount = sorted.length - previousCount;
  const halfHours = Math.max(spanHours / 2, 1);

  return {
    rate,
    trend: percentChange(recentCount / halfHours, previousCount / halfHours),
  };
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { selectedOrg } = useOrg();
  const [searchParams, setSearchParams] = useSearchParams();
  const [pillConfig, setPillConfig] = useState<StatPillConfig>(() => loadStatPillConfig());
  const [configOpen, setConfigOpen] = useState(false);
  const [renderTime] = useState(() => Date.now());

  const validViews: DashboardView[] = ['operations', 'executive', 'security', 'cicd'];
  const rawView = searchParams.get('view') ?? 'operations';
  const view: DashboardView = validViews.includes(rawView as DashboardView)
    ? (rawView as DashboardView)
    : 'operations';

  const orgLabel = !selectedOrg || selectedOrg === 'all' ? 'All organizations' : selectedOrg;
  const orgParam = selectedOrg && selectedOrg !== 'all' ? selectedOrg : undefined;

  function setView(nextView: DashboardView) {
    setSearchParams(nextView === 'operations' ? {} : { view: nextView }, { replace: true });
  }

  const openDetectionsQuery = useQuery({
    queryKey: ['detections', 'open', orgParam],
    queryFn: () => listDetections({ status: 'open', org: orgParam, page_size: 100 }),
    staleTime: 5 * 60 * 1000,
  });

  const criticalDetectionsQuery = useQuery({
    queryKey: ['detections', 'open-critical', orgParam],
    queryFn: () => listDetections({ status: 'open', severity: 'critical', org: orgParam, page_size: 100 }),
    staleTime: 5 * 60 * 1000,
  });

  const unresolvedThreatsQuery = useQuery({
    queryKey: ['detections', 'investigating', orgParam],
    queryFn: () => listDetections({ status: 'investigating', org: orgParam, page_size: 100 }),
    staleTime: 5 * 60 * 1000,
  });

  const eventsQuery = useQuery({
    queryKey: ['events', 'dashboard', orgParam],
    queryFn: () => listEvents({ page_size: 500, sort: 'created_at_desc', org: orgParam }),
    staleTime: 5 * 60 * 1000,
  });

  const actionsReportQuery = useQuery({
    queryKey: ['reports', 'actions-volume-dashboard', orgParam],
    queryFn: () => getActionsVolumeReport({ window_days: 7, granularity: 'daily', org: orgParam }),
    staleTime: 5 * 60 * 1000,
  });

  const systemHealthQuery = useQuery({
    queryKey: ['health-signals', 'system-dashboard'],
    queryFn: getSystemHealth,
    staleTime: 5 * 60 * 1000,
  });

  const unifiedSecurityQuery = useQuery({
    queryKey: ['health-signals', 'unified-security-dashboard'],
    queryFn: getUnifiedSecurity,
    staleTime: 5 * 60 * 1000,
  });

  const coverageGrowthQuery = useQuery({
    queryKey: ['health-signals', 'coverage-growth-dashboard'],
    queryFn: () => getCoverageGrowth('90d'),
    staleTime: 5 * 60 * 1000,
  });

  const unhealthyHooksQuery = useQuery({
    queryKey: ['health-signals', 'unhealthy-hooks-dashboard'],
    queryFn: () => getUnhealthyHooks(50),
    staleTime: 5 * 60 * 1000,
  });

  const healthScoreQuery = useQuery({
    queryKey: ['health-signals', 'score-dashboard'],
    queryFn: getHealthScore,
    staleTime: 5 * 60 * 1000,
  });

  const copilotAdoptionQuery = useQuery({
    queryKey: ['copilot', 'adoption-dashboard'],
    queryFn: getCopilotAdoption,
    staleTime: 5 * 60 * 1000,
  });

  const developersQuery = useQuery({
    queryKey: ['dev-activity', 'developers-dashboard'],
    queryFn: () => getDevelopers(30),
    staleTime: 5 * 60 * 1000,
  });

  const stalePrsQuery = useQuery({
    queryKey: ['health-signals', 'stale-prs-dashboard'],
    queryFn: () => getStalePrs(30, 50),
    staleTime: 5 * 60 * 1000,
  });

  const complianceSummaryQuery = useQuery({
    queryKey: ['compliance', 'summary-dashboard', orgParam],
    queryFn: () => getComplianceSummary(orgParam),
    staleTime: 5 * 60 * 1000,
  });

  const policyChecksQuery = useQuery({
    queryKey: ['compliance', 'policy-checks-dashboard', orgParam],
    queryFn: () => getPolicyChecks(orgParam),
    staleTime: 5 * 60 * 1000,
  });

  const platformSecurityQuery = useQuery({
    queryKey: ['health-signals', 'platform-security-dashboard'],
    queryFn: getPlatformSecurity,
    staleTime: 5 * 60 * 1000,
  });

  const actionsBuckets = ((actionsReportQuery.data?.data ?? []) as unknown as ActionsVolumeBucket[]) ?? [];
  const totalWorkflowRuns = actionsBuckets.reduce((sum, bucket) => sum + (bucket.workflow_runs_total ?? 0), 0);
  const succeededWorkflowRuns = actionsBuckets.reduce(
    (sum, bucket) => sum + (bucket.workflow_runs_succeeded ?? 0),
    0,
  );
  const failedWorkflowRuns = actionsBuckets.reduce(
    (sum, bucket) => sum + (bucket.workflow_runs_failed ?? 0),
    0,
  );
  const workflowSuccessRate = totalWorkflowRuns > 0 ? (succeededWorkflowRuns / totalWorkflowRuns) * 100 : 0;

  const recentEvents = eventsQuery.data?.items ?? [];
  const eventsPerHour = computeEventsPerHour(recentEvents, eventsQuery.data?.total);
  const activeOrgsFromEvents = new Set(recentEvents.map((event) => event.org).filter(Boolean)).size;
  const activeOrgs = orgParam ? 1 : Math.max(activeOrgsFromEvents, healthScoreQuery.data?.orgs_monitored ?? 0);
  const uniqueActors = developersQuery.data?.developers.length ?? 0;
  const secretTrend = latestDelta(
    (unifiedSecurityQuery.data?.trend_30d ?? []).map((point) => point.secret_scanning),
  );
  const coveragePoints = coverageGrowthQuery.data?.time_series ?? [];
  const coverageTrend = latestDelta(coveragePoints.map((point) => point.ghas_pct));
  const ghasCoverage =
    coverageGrowthQuery.data?.feature_coverage['ghas']?.pct ??
    coveragePoints[coveragePoints.length - 1]?.ghas_pct ??
    0;
  const syncHealth = systemHealthQuery.data?.gap_detected
    ? Math.max(0, 100 - Math.min(systemHealthQuery.data.gap_duration_minutes ?? 100, 100))
    : 100;
  const webhookLagMinutes = systemHealthQuery.data?.last_event_at
    ? Math.max(
        0,
        Math.round((renderTime - new Date(systemHealthQuery.data.last_event_at).getTime()) / 60_000),
      )
    : 0;
  const copilotAdoption = copilotAdoptionQuery.data?.total_adoption ?? 0;
  const copilotTrend = latestDelta(
    (copilotAdoptionQuery.data?.feature_adoption ?? []).map((entry) => entry.trend_7d),
  );
  const stalePrs = stalePrsQuery.data?.stale_prs ?? [];
  const averageMergeMinutes = average(stalePrs.map((pr) => pr.days_open * 24 * 60));
  const complianceScore = complianceSummaryQuery.data?.overall_score ?? 0;
  const policyViolations = policyChecksQuery.data
    ? policyChecksQuery.data.checks_total - policyChecksQuery.data.checks_passing
    : 0;
  const branchProtectionPct = platformSecurityQuery.data?.orgs.length
    ? (platformSecurityQuery.data.orgs.filter((org) => org.branch_protection_default).length /
        platformSecurityQuery.data.orgs.length) *
      100
    : 0;

  const metricStates = useMemo<Record<string, MetricState>>(
    () => ({
      'open-detections': {
        rawValue: openDetectionsQuery.data?.total ?? 0,
        isLoading: openDetectionsQuery.isLoading,
        hasError: openDetectionsQuery.isError,
      },
      'critical-detections': {
        rawValue: criticalDetectionsQuery.data?.total ?? 0,
        isLoading: criticalDetectionsQuery.isLoading,
        hasError: criticalDetectionsQuery.isError,
      },
      'unresolved-threats': {
        rawValue: unresolvedThreatsQuery.data?.total ?? 0,
        isLoading: unresolvedThreatsQuery.isLoading,
        hasError: unresolvedThreatsQuery.isError,
      },
      'secret-alerts': {
        rawValue: unifiedSecurityQuery.data?.secret_scanning.open ?? 0,
        trend: secretTrend,
        isLoading: unifiedSecurityQuery.isLoading,
        hasError: unifiedSecurityQuery.isError,
      },
      'ghas-coverage': {
        rawValue: ghasCoverage,
        trend: coverageTrend,
        isLoading: coverageGrowthQuery.isLoading,
        hasError: coverageGrowthQuery.isError,
      },
      'sync-health': {
        rawValue: syncHealth,
        isLoading: systemHealthQuery.isLoading,
        hasError: systemHealthQuery.isError,
      },
      'events-per-hour': {
        rawValue: eventsPerHour.rate,
        trend: eventsPerHour.trend,
        isLoading: eventsQuery.isLoading,
        hasError: eventsQuery.isError,
      },
      'failed-syncs': {
        rawValue: unhealthyHooksQuery.data?.unhealthy_hooks.length ?? 0,
        isLoading: unhealthyHooksQuery.isLoading,
        hasError: unhealthyHooksQuery.isError,
      },
      'active-orgs': {
        rawValue: activeOrgs,
        isLoading: eventsQuery.isLoading || healthScoreQuery.isLoading,
        hasError: eventsQuery.isError || healthScoreQuery.isError,
      },
      'webhook-lag': {
        rawValue: webhookLagMinutes,
        isLoading: systemHealthQuery.isLoading,
        hasError: systemHealthQuery.isError,
      },
      'copilot-adoption': {
        rawValue: copilotAdoption,
        trend: copilotTrend,
        isLoading: copilotAdoptionQuery.isLoading,
        hasError: copilotAdoptionQuery.isError,
      },
      'active-developers': {
        rawValue: uniqueActors,
        isLoading: developersQuery.isLoading,
        hasError: developersQuery.isError,
      },
      'pr-merge-time': {
        rawValue: averageMergeMinutes,
        isLoading: stalePrsQuery.isLoading,
        hasError: stalePrsQuery.isError,
      },
      'workflow-success-rate': {
        rawValue: workflowSuccessRate,
        trend: latestDelta(actionsBuckets.map((bucket) => Number(bucket.success_rate_pct ?? 0))),
        isLoading: actionsReportQuery.isLoading,
        hasError: actionsReportQuery.isError,
      },
      'compliance-score': {
        rawValue: complianceScore,
        isLoading: complianceSummaryQuery.isLoading,
        hasError: complianceSummaryQuery.isError,
      },
      'policy-violations': {
        rawValue: policyViolations,
        isLoading: policyChecksQuery.isLoading,
        hasError: policyChecksQuery.isError,
      },
      'overdue-reviews': {
        rawValue: stalePrs.length,
        isLoading: stalePrsQuery.isLoading,
        hasError: stalePrsQuery.isError,
      },
      'branch-protection': {
        rawValue: branchProtectionPct,
        isLoading: platformSecurityQuery.isLoading,
        hasError: platformSecurityQuery.isError,
      },
    }),
    [
      actionsBuckets,
      actionsReportQuery.isError,
      actionsReportQuery.isLoading,
      activeOrgs,
      averageMergeMinutes,
      branchProtectionPct,
      complianceScore,
      complianceSummaryQuery.isError,
      complianceSummaryQuery.isLoading,
      copilotAdoption,
      copilotAdoptionQuery.isError,
      copilotAdoptionQuery.isLoading,
      copilotTrend,
      coverageGrowthQuery.isError,
      coverageGrowthQuery.isLoading,
      coverageTrend,
      criticalDetectionsQuery.data?.total,
      criticalDetectionsQuery.isError,
      criticalDetectionsQuery.isLoading,
      developersQuery.isError,
      developersQuery.isLoading,
      eventsPerHour.rate,
      eventsPerHour.trend,
      eventsQuery.isError,
      eventsQuery.isLoading,
      ghasCoverage,
      healthScoreQuery.isError,
      healthScoreQuery.isLoading,
      openDetectionsQuery.data?.total,
      openDetectionsQuery.isError,
      openDetectionsQuery.isLoading,
      platformSecurityQuery.isError,
      platformSecurityQuery.isLoading,
      policyChecksQuery.isError,
      policyChecksQuery.isLoading,
      policyViolations,
      secretTrend,
      stalePrs,
      stalePrsQuery.isError,
      stalePrsQuery.isLoading,
      syncHealth,
      systemHealthQuery.isError,
      systemHealthQuery.isLoading,
      unhealthyHooksQuery.data?.unhealthy_hooks.length,
      unhealthyHooksQuery.isError,
      unhealthyHooksQuery.isLoading,
      unifiedSecurityQuery.data?.secret_scanning.open,
      unifiedSecurityQuery.isError,
      unifiedSecurityQuery.isLoading,
      unresolvedThreatsQuery.data?.total,
      unresolvedThreatsQuery.isError,
      unresolvedThreatsQuery.isLoading,
      uniqueActors,
      webhookLagMinutes,
      workflowSuccessRate,
    ],
  );

  const orderedPills = pillConfig.order.filter((metricId) => pillConfig.enabledPills.includes(metricId));

  function handleSaveConfig(nextConfig: StatPillConfig) {
    setPillConfig(nextConfig);
    saveStatPillConfig(nextConfig);
    setConfigOpen(false);
  }

  return (
    <div className={styles.page}>
      <PageHeader
        title={`Dashboard · ${orgLabel}`}
        description={
          systemHealthQuery.data?.last_event_at
            ? `Last synced: ${formatRelative(systemHealthQuery.data.last_event_at)}`
            : 'Activity across your organizations'
        }
      />

      <div className={styles.viewToggle}>
        <button
          className={[styles.viewBtn, view === 'operations' && styles.viewActive].filter(Boolean).join(' ')}
          onClick={() => setView('operations')}
        >
          Operations
        </button>
        <button
          className={[styles.viewBtn, view === 'executive' && styles.viewActive].filter(Boolean).join(' ')}
          onClick={() => setView('executive')}
        >
          Executive
        </button>
        <button
          className={[styles.viewBtn, view === 'security' && styles.viewActive].filter(Boolean).join(' ')}
          onClick={() => setView('security')}
        >
          Security Engineering
        </button>
        <button
          className={[styles.viewBtn, view === 'cicd' && styles.viewActive].filter(Boolean).join(' ')}
          onClick={() => setView('cicd')}
        >
          CI/CD
        </button>
      </div>

      {view === 'executive' ? (
        <ExecutiveView />
      ) : view === 'security' ? (
        <SecurityView />
      ) : view === 'cicd' ? (
        <CiCdView />
      ) : (
        <>
          {systemHealthQuery.data != null && (
            <div
              className={[
                styles.systemHealthBar,
                systemHealthQuery.data.gap_detected && styles.healthWarning,
              ]
                .filter(Boolean)
                .join(' ')}
            >
              <span
                className={[
                  styles.systemHealthDot,
                  systemHealthQuery.data.gap_detected ? styles.warn : styles.ok,
                ].join(' ')}
              />
              {systemHealthQuery.data.gap_detected ? (
                <span>
                  Ingestion gap detected
                  {systemHealthQuery.data.gap_duration_minutes != null && (
                    <> — {systemHealthQuery.data.gap_duration_minutes}m of missing data</>
                  )}
                </span>
              ) : (
                <span>
                  System healthy
                  {systemHealthQuery.data.last_event_at && (
                    <> · Last event: {formatRelative(systemHealthQuery.data.last_event_at)}</>
                  )}
                </span>
              )}
            </div>
          )}

          <div className={styles.pillsBar}>
            <div className={styles.pills}>
              {orderedPills.map((metricId) => {
                const metric = STAT_PILL_REGISTRY[metricId];
                const state = metricStates[metricId];
                if (!metric || !state) return null;

                return (
                  <StatPill
                    key={metric.id}
                    id={metric.id}
                    icon={metric.icon}
                    label={metric.label}
                    value={state.rawValue}
                    format={metric.format}
                    trend={state.trend}
                    variant={getThresholdVariant(
                      state.rawValue,
                      pillConfig.thresholds[metric.id] ?? metric.defaultThresholds,
                      metric.thresholdDirection,
                    )}
                    path={metric.path}
                    isLoading={state.isLoading}
                    hasError={state.hasError}
                  />
                );
              })}
            </div>
            <button
              type="button"
              className={styles.configBtn}
              onClick={() => setConfigOpen(true)}
              aria-label="Configure stat pills"
            >
              <span aria-hidden="true">⚙</span>
              <span>Configure</span>
            </button>
          </div>

          <StatPillConfigDrawer
            key={`${configOpen}-${JSON.stringify(pillConfig)}`}
            open={configOpen}
            onClose={() => setConfigOpen(false)}
            config={pillConfig}
            onSave={handleSaveConfig}
          />

          {systemHealthQuery.data != null && systemHealthQuery.data.gap_detected && (
            <div className={styles.ingestionBanner}>
              <span className={styles.ingestionIcon}>⚠</span>
              <span>
                Data ingestion gap detected
                {systemHealthQuery.data.gap_duration_minutes != null && (
                  <> — {systemHealthQuery.data.gap_duration_minutes} minutes of missing data</>
                )}
                . Some health signals may be incomplete.
              </span>
            </div>
          )}

          <div className={styles.grid}>
            <div className={styles.flex1}>
              <SecurityOverviewWidget detections={openDetectionsQuery.data?.items ?? []} />
            </div>

            <div className={styles.sidebar}>
              <Card>
                <CardHeader>Platform alerts</CardHeader>
                <div className={styles.alerts}>
                  <div className={styles.alertRow}>
                    <span
                      className={styles.alertIcon}
                      style={{ color: failedWorkflowRuns > 0 ? 'var(--danger)' : 'var(--success)' }}
                    >
                      {failedWorkflowRuns > 0 ? '⚠' : '✓'}
                    </span>
                    <div>
                      Workflow runs:{' '}
                      <ClickableValue
                        onClick={() => navigate('/velocity')}
                        label={`${succeededWorkflowRuns} succeeded — view velocity`}
                      >
                        <strong>{succeededWorkflowRuns} succeeded</strong>
                      </ClickableValue>
                      ,{' '}
                      <ClickableValue
                        onClick={() => navigate('/velocity')}
                        label={`${failedWorkflowRuns} failed — view velocity`}
                      >
                        <strong>{failedWorkflowRuns} failed</strong>
                      </ClickableValue>
                      {totalWorkflowRuns > 0 ? ` (${workflowSuccessRate.toFixed(1)}% success)` : ''}
                    </div>
                  </div>
                  <div className={`${styles.alertRow} ${styles.alertBorder}`}>
                    <span className={styles.alertIcon} style={{ color: 'var(--attention)' }}>
                      ⚡
                    </span>
                    <div>
                      Events volume:{' '}
                      <ClickableValue
                        onClick={() => navigate('/events')}
                        label={`${formatCount(eventsQuery.data?.total ?? 0)} events — view all events`}
                      >
                        <strong>{formatCount(eventsQuery.data?.total ?? 0)} events</strong>
                      </ClickableValue>{' '}
                      tracked
                    </div>
                  </div>
                  <div className={`${styles.alertRow} ${styles.alertBorder}`}>
                    <span
                      className={styles.alertIcon}
                      style={{
                        color: (openDetectionsQuery.data?.total ?? 0) > 0 ? 'var(--attention)' : 'var(--success)',
                      }}
                    >
                      {(openDetectionsQuery.data?.total ?? 0) > 0 ? '⚠' : '✓'}
                    </span>
                    <div>
                      Active detections:{' '}
                      <ClickableValue
                        onClick={() => navigate('/threats')}
                        label={`${openDetectionsQuery.data?.total ?? 0} investigating — view threats`}
                      >
                        <strong>{openDetectionsQuery.data?.total ?? 0} investigating</strong>
                      </ClickableValue>
                    </div>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
