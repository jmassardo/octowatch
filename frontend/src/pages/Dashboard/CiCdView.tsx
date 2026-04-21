import { useQuery } from '@tanstack/react-query';
import { getActionsVolumeReport } from '../../api/reports';
import {
  getAlwaysFailingWorkflows,
  getAlwaysTimingOutWorkflows,
  type WorkflowFailureSummary,
  type AlwaysFailingResponse,
} from '../../api/workflowMetrics';
import { getMetricsThatMatter } from '../../api/executive';
import type { MetricsThatMatter } from '../../api/executive';
import type { ReportEnvelope, ActionsVolumeBucket } from '../../types/reports';
import { MetricCard } from '../../components/primitives/MetricCard';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { formatRelative } from '../../utils/dates';
import styles from './Dashboard.module.css';

const failingColumns: ColumnDef<WorkflowFailureSummary>[] = [
  {
    key: 'repo',
    header: 'Repo',
    sortable: true,
    filterable: true,
    helpText: 'Repository containing the workflow.',
    render: (row) => row.repo,
    sortValue: (row) => row.repo,
    filterValue: (row) => row.repo,
  },
  {
    key: 'workflow_name',
    header: 'Workflow',
    sortable: true,
    filterable: true,
    helpText: 'Name of the GitHub Actions workflow.',
    render: (row) => row.workflow_name,
    sortValue: (row) => row.workflow_name,
    filterValue: (row) => row.workflow_name,
  },
  {
    key: 'consecutive_count',
    header: 'Consecutive Failures',
    sortable: true,
    filterable: false,
    helpText: 'Number of consecutive failed runs.',
    render: (row) => String(row.consecutive_count),
    sortValue: (row) => row.consecutive_count,
  },
  {
    key: 'last_run_at',
    header: 'Last Run',
    sortable: true,
    filterable: false,
    helpText: 'When the workflow last ran.',
    render: (row) => formatRelative(row.last_run_at),
    sortValue: (row) => row.last_run_at,
  },
];

const timingOutColumns: ColumnDef<WorkflowFailureSummary>[] = [
  {
    key: 'repo',
    header: 'Repo',
    sortable: true,
    filterable: true,
    helpText: 'Repository containing the workflow.',
    render: (row) => row.repo,
    sortValue: (row) => row.repo,
    filterValue: (row) => row.repo,
  },
  {
    key: 'workflow_name',
    header: 'Workflow',
    sortable: true,
    filterable: true,
    helpText: 'Name of the GitHub Actions workflow.',
    render: (row) => row.workflow_name,
    sortValue: (row) => row.workflow_name,
    filterValue: (row) => row.workflow_name,
  },
  {
    key: 'consecutive_count',
    header: 'Consecutive Timeouts',
    sortable: true,
    filterable: false,
    helpText: 'Number of consecutive timed-out runs.',
    render: (row) => String(row.consecutive_count),
    sortValue: (row) => row.consecutive_count,
  },
  {
    key: 'last_run_at',
    header: 'Last Run',
    sortable: true,
    filterable: false,
    helpText: 'When the workflow last ran.',
    render: (row) => formatRelative(row.last_run_at),
    sortValue: (row) => row.last_run_at,
  },
];

export function CiCdView() {
  const {
    data: actionsReport,
    isLoading: loadingActions,
    isError: errorActions,
    refetch: refetchActions,
  } = useQuery<ReportEnvelope>({
    queryKey: ['cicd-view', 'actions-volume'],
    queryFn: () => getActionsVolumeReport({ window_days: 7, granularity: 'daily' }),
    staleTime: 5 * 60 * 1000,
  });

  const {
    data: alwaysFailing,
    isLoading: loadingFailing,
    isError: errorFailing,
    refetch: refetchFailing,
  } = useQuery<AlwaysFailingResponse>({
    queryKey: ['cicd-view', 'always-failing'],
    queryFn: () => getAlwaysFailingWorkflows({ threshold: 3 }),
    staleTime: 5 * 60 * 1000,
  });

  const {
    data: alwaysTimingOut,
    isLoading: loadingTimingOut,
    isError: errorTimingOut,
    refetch: refetchTimingOut,
  } = useQuery<AlwaysFailingResponse>({
    queryKey: ['cicd-view', 'always-timing-out'],
    queryFn: () => getAlwaysTimingOutWorkflows({ threshold: 3 }),
    staleTime: 5 * 60 * 1000,
  });

  const { data: metrics, isLoading: loadingMetrics } = useQuery<MetricsThatMatter>({
    queryKey: ['cicd-view', 'metrics-that-matter'],
    queryFn: () => getMetricsThatMatter(30),
    staleTime: 5 * 60 * 1000,
  });

  const buckets = (actionsReport?.data ?? []) as unknown as ActionsVolumeBucket[];
  const totalRuns = buckets.reduce((s, b) => s + (b.workflow_runs_total ?? 0), 0);
  const succeededRuns = buckets.reduce((s, b) => s + (b.workflow_runs_succeeded ?? 0), 0);
  const failedRuns = buckets.reduce((s, b) => s + (b.workflow_runs_failed ?? 0), 0);
  const successRate = totalRuns > 0 ? ((succeededRuns / totalRuns) * 100).toFixed(1) : null;

  const top10Failing = (alwaysFailing?.items ?? []).slice(0, 10);
  const top10TimingOut = (alwaysTimingOut?.items ?? []).slice(0, 10);

  if (loadingActions) return <Spinner />;

  return (
    <>
      {errorActions && (
        <ErrorBanner message="Could not load actions volume report" onRetry={refetchActions} />
      )}
      {errorFailing && (
        <ErrorBanner message="Could not load always-failing workflows" onRetry={refetchFailing} />
      )}
      {errorTimingOut && (
        <ErrorBanner
          message="Could not load always-timing-out workflows"
          onRetry={refetchTimingOut}
        />
      )}

      {/* Top row: CI/CD metrics */}
      <div className={styles.cardGrid}>
        <MetricCard
          value={String(totalRuns)}
          label="Total Runs (7d)"
          helpText="Total GitHub Actions workflow runs in the last 7 days."
          to="/velocity"
        />
        <MetricCard
          value={String(succeededRuns)}
          label="Succeeded"
          helpText="Total successful workflow runs in the last 7 days."
          to="/velocity"
        />
        <MetricCard
          value={String(failedRuns)}
          label="Failed"
          helpText="Total failed workflow runs in the last 7 days."
          accent={failedRuns > 0}
          to="/velocity"
        />
        <MetricCard
          value={successRate != null ? `${successRate}%` : '—'}
          label="Success Rate"
          helpText="Percentage of workflow runs that succeeded in the last 7 days."
          to="/velocity"
        />
      </div>

      {/* Two side-by-side tables */}
      <div className={styles.twoColTables}>
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Always Failing (top 10)</div>
          {loadingFailing ? (
            <Spinner />
          ) : top10Failing.length === 0 ? (
            <div style={{ color: 'var(--fg-muted)', padding: '12px 0', fontSize: 13 }}>
              No consistently failing workflows 🎉
            </div>
          ) : (
            <DataTable
              columns={failingColumns}
              data={top10Failing}
              rowKey={(row) => `${row.org}/${row.repo}/${row.workflow_name}`}
              emptyMessage="No consistently failing workflows"
            />
          )}
        </div>

        <div className={styles.section}>
          <div className={styles.sectionTitle}>Always Timing Out (top 10)</div>
          {loadingTimingOut ? (
            <Spinner />
          ) : top10TimingOut.length === 0 ? (
            <div style={{ color: 'var(--fg-muted)', padding: '12px 0', fontSize: 13 }}>
              No consistently timing-out workflows 🎉
            </div>
          ) : (
            <DataTable
              columns={timingOutColumns}
              data={top10TimingOut}
              rowKey={(row) => `${row.org}/${row.repo}/${row.workflow_name}`}
              emptyMessage="No consistently timing-out workflows"
            />
          )}
        </div>
      </div>

      {/* DORA quick glance */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>DORA Quick Glance</div>
        {loadingMetrics ? (
          <Spinner />
        ) : (
          <div className={styles.cardGrid}>
            <MetricCard
              value={
                metrics?.shipping_faster.deployment_frequency_per_week != null
                  ? `${metrics.shipping_faster.deployment_frequency_per_week.toFixed(1)}/wk`
                  : '—'
              }
              label="Deployment Frequency"
              helpText="Average deployments per week from Metrics That Matter."
              to="/velocity"
            />
            <MetricCard
              value={
                metrics?.shipping_safer.change_failure_rate_pct != null
                  ? `${metrics.shipping_safer.change_failure_rate_pct.toFixed(1)}%`
                  : '—'
              }
              label="Change Failure Rate"
              helpText="Percentage of deployments causing a failure (from Metrics That Matter)."
              to="/velocity"
            />
            <MetricCard
              value={
                metrics?.shipping_faster.avg_pr_lifecycle_hours != null
                  ? `${metrics.shipping_faster.avg_pr_lifecycle_hours.toFixed(0)}h`
                  : '—'
              }
              label="Lead Time"
              helpText="Average PR lifecycle from open to merge in hours (proxy for lead time)."
              to="/velocity"
            />
          </div>
        )}
      </div>
    </>
  );
}
