import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getActionsVolumeReport } from '../../api/reports';
import {
  getWorkflowHealth,
  type WorkflowRow,
  type WorkflowHealthResponse,
} from '../../api/healthSignals';
import { getMetricsThatMatter } from '../../api/executive';
import type { MetricsThatMatter } from '../../api/executive';
import type { ReportEnvelope, ActionsVolumeBucket } from '../../types/reports';
import { MetricCard } from '../../components/primitives/MetricCard';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { formatRelative } from '../../utils/dates';
import styles from './Dashboard.module.css';

const workflowColumns: ColumnDef<WorkflowRow>[] = [
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
    header: 'Workflow Name',
    sortable: true,
    filterable: true,
    helpText: 'Name of the GitHub Actions workflow.',
    render: (row) => row.workflow_name,
    sortValue: (row) => row.workflow_name,
    filterValue: (row) => row.workflow_name,
  },
  {
    key: 'total_runs',
    header: 'Total Runs',
    sortable: true,
    filterable: false,
    helpText: 'Total number of workflow runs.',
    render: (row) => String(row.total_runs),
    sortValue: (row) => row.total_runs,
  },
  {
    key: 'successes',
    header: 'Successes',
    sortable: true,
    filterable: false,
    helpText: 'Number of successful workflow runs.',
    render: (row) => String(row.successes),
    sortValue: (row) => row.successes,
  },
  {
    key: 'failures',
    header: 'Failures',
    sortable: true,
    filterable: false,
    helpText: 'Number of failed workflow runs.',
    render: (row) => String(row.failures),
    sortValue: (row) => row.failures,
  },
  {
    key: 'failure_rate_pct',
    header: 'Failure Rate %',
    sortable: true,
    filterable: false,
    helpText: 'Percentage of runs that failed.',
    render: (row) => `${row.failure_rate_pct.toFixed(1)}%`,
    sortValue: (row) => row.failure_rate_pct,
  },
  {
    key: 'last_run',
    header: 'Last Run',
    sortable: true,
    filterable: false,
    helpText: 'When the workflow last ran.',
    render: (row) => formatRelative(row.last_run),
    sortValue: (row) => row.last_run,
  },
];

export function CiCdView() {
  const navigate = useNavigate();

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
    data: workflowHealth,
    isLoading: loadingWorkflows,
    isError: errorWorkflows,
    refetch: refetchWorkflows,
  } = useQuery<WorkflowHealthResponse>({
    queryKey: ['cicd-view', 'workflow-health'],
    queryFn: getWorkflowHealth,
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

  const unhealthyCount = (workflowHealth?.workflows ?? []).filter(
    (w) => w.failure_rate_pct > 20,
  ).length;

  // Sort workflows by failure rate descending
  const sortedWorkflows = [...(workflowHealth?.workflows ?? [])].sort(
    (a, b) => b.failure_rate_pct - a.failure_rate_pct,
  );

  const isLoading = loadingActions || loadingWorkflows;

  if (isLoading) return <Spinner />;

  return (
    <>
      {errorActions && (
        <ErrorBanner message="Could not load actions volume report" onRetry={refetchActions} />
      )}
      {errorWorkflows && (
        <ErrorBanner message="Could not load workflow health" onRetry={refetchWorkflows} />
      )}

      {/* Top row: CI/CD metrics */}
      <div className={styles.cardGrid}>
        <MetricCard
          value={String(totalRuns)}
          label="Workflow runs (7d)"
          helpText="Total GitHub Actions workflow runs in the last 7 days."
          to="/velocity"
        />
        <MetricCard
          value={successRate != null ? `${successRate}%` : '—'}
          label="Success rate"
          helpText="Percentage of workflow runs that succeeded in the last 7 days."
          to="/velocity"
        />
        <MetricCard
          value={String(failedRuns)}
          label="Failed runs"
          helpText="Total failed workflow runs in the last 7 days."
          accent={failedRuns > 0}
          to="/velocity"
        />
        <MetricCard
          value={String(unhealthyCount)}
          label="Unhealthy workflows"
          helpText="Workflows with failure rate above 20%."
          accent={unhealthyCount > 0}
          to="/workflows"
        />
      </div>

      {/* Middle: top failing workflows */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>Top Failing Workflows</div>
        <DataTable
          columns={workflowColumns}
          data={sortedWorkflows}
          rowKey={(row) => `${row.repo}/${row.workflow_name}`}
          onRowClick={() => navigate('/workflows')}
          emptyMessage="No workflow data available"
        />
      </div>

      {/* Bottom: DORA quick glance */}
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
