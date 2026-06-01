import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getAlwaysFailingWorkflows, getAlwaysTimingOutWorkflows } from '../../api/workflowMetrics';
import type { WorkflowFailureSummary } from '../../api/workflowMetrics';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Pagination } from '../../components/primitives/Pagination';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { WorkflowDetailDrawer } from '../../components/WorkflowDetailDrawer/WorkflowDetailDrawer';
import { formatRelativeShort } from '../../utils/dates';
import styles from './Workflows.module.css';

// ── Helpers ───────────────────────────────────────────────────────────────────

const METRICS_PAGE_SIZE = 10;

function conclusionBadge(conclusion: string): string {
  switch (conclusion) {
    case 'failure':
      return styles.conclusionFailure;
    case 'timed_out':
      return styles.conclusionTimeout;
    case 'success':
      return styles.conclusionSuccess;
    default:
      return styles.conclusionMuted;
  }
}

// ── Metrics Table ─────────────────────────────────────────────────────────────

interface MetricsTableProps {
  title: string;
  items: WorkflowFailureSummary[] | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  onViewRuns: (item: WorkflowFailureSummary) => void;
  emptyMessage: string;
}

const metricsColumns: ColumnDef<WorkflowFailureSummary>[] = [
  {
    key: 'org',
    header: 'Org',
    sortable: true,
    filterable: true,
    render: (row) => row.org,
    helpText: 'GitHub organization that owns the workflow.',
  },
  {
    key: 'repo',
    header: 'Repository',
    sortable: true,
    filterable: true,
    render: (row) => (
      <a
        href={`https://github.com/${row.org}/${row.repo}`}
        target="_blank"
        rel="noopener noreferrer"
        className={styles.ghLink}
        onClick={(e) => e.stopPropagation()}
      >
        {row.repo}
      </a>
    ),
    helpText: 'Repository containing the workflow definition.',
  },
  {
    key: 'workflow_name',
    header: 'Workflow',
    sortable: true,
    filterable: true,
    render: (row) => <span className={styles.repoPath}>{row.workflow_name}</span>,
    helpText: 'GitHub Actions workflow name from the YAML file.',
  },
  {
    key: 'consecutive_count',
    header: 'Consecutive',
    sortable: true,
    render: (row) => (
      <span className={`${styles.conclusionBadge} ${conclusionBadge(row.last_conclusion)}`}>
        {row.consecutive_count}×
      </span>
    ),
    sortValue: (row) => row.consecutive_count,
    helpText: 'Number of consecutive runs with this conclusion.',
  },
  {
    key: 'last_run',
    header: 'Last Run',
    sortable: true,
    render: (row) => (
      <span className={styles.timeCell}>{formatRelativeShort(row.last_run_at)}</span>
    ),
    sortValue: (row) => row.last_run_at,
    helpText: 'When the most recent run completed.',
  },
];

function MetricsTable({
  title,
  items,
  isLoading,
  isError,
  onRetry,
  onViewRuns,
  emptyMessage,
}: MetricsTableProps) {
  const [page, setPage] = useState(1);

  const paginatedItems = useMemo(() => {
    if (!items) return [];
    const start = (page - 1) * METRICS_PAGE_SIZE;
    return items.slice(start, start + METRICS_PAGE_SIZE);
  }, [items, page]);

  return (
    <div className={styles.metricsSection}>
      <div className={styles.metricsSectionTitle}>{title}</div>
      {isLoading && <Spinner />}
      {isError && (
        <ErrorBanner message={`Failed to load ${title.toLowerCase()}`} onRetry={onRetry} />
      )}
      {!isLoading && !isError && items && items.length === 0 && (
        <div className={styles.metricsEmptyState}>
          <span className={styles.metricsEmptyIcon}>✅</span>
          <span>{emptyMessage}</span>
        </div>
      )}
      {!isLoading && !isError && items && items.length > 0 && (
        <>
          <DataTable
            columns={metricsColumns}
            data={paginatedItems}
            rowKey={(row) => `${row.org}/${row.repo}/${row.workflow_name}`}
            onRowClick={(row) => onViewRuns(row)}
            emptyMessage={emptyMessage}
          />
          <Pagination
            page={page}
            pageSize={METRICS_PAGE_SIZE}
            total={items.length}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

interface WorkflowMetricsTabProps {
  orgFilter?: string;
}

export function WorkflowMetricsTab({ orgFilter }: WorkflowMetricsTabProps) {
  const [lookbackDays, setLookbackDays] = useState(30);
  const [failThreshold, setFailThreshold] = useState(5);
  const [timeoutThreshold, setTimeoutThreshold] = useState(3);
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowFailureSummary | null>(null);

  const {
    data: failingData,
    isLoading: failingLoading,
    isError: failingError,
    refetch: refetchFailing,
  } = useQuery({
    queryKey: ['workflow-metrics', 'failing', failThreshold, lookbackDays, orgFilter ?? 'all'],
    queryFn: () =>
      getAlwaysFailingWorkflows({
        threshold: failThreshold,
        lookback_days: lookbackDays,
        org: orgFilter,
      }),
    staleTime: 5 * 60 * 1000,
  });

  const {
    data: timingOutData,
    isLoading: timingOutLoading,
    isError: timingOutError,
    refetch: refetchTimingOut,
  } = useQuery({
    queryKey: [
      'workflow-metrics',
      'timing-out',
      timeoutThreshold,
      lookbackDays,
      orgFilter ?? 'all',
    ],
    queryFn: () =>
      getAlwaysTimingOutWorkflows({
        threshold: timeoutThreshold,
        lookback_days: lookbackDays,
        org: orgFilter,
      }),
    staleTime: 5 * 60 * 1000,
  });

  return (
    <div>
      {/* Controls */}
      <div className={styles.metricsControls}>
        <div className={styles.metricsControlGroup}>
          <label className={styles.metricsLabel}>Lookback period</label>
          <div className={styles.statusChips}>
            {([7, 14, 30, 60, 90] as const).map((days) => (
              <button
                key={days}
                className={[styles.statusChip, lookbackDays === days ? styles.statusChipActive : '']
                  .filter(Boolean)
                  .join(' ')}
                onClick={() => setLookbackDays(days)}
              >
                {days}d
              </button>
            ))}
          </div>
        </div>

        <div className={styles.metricsControlGroup}>
          <label className={styles.metricsLabel}>Failure threshold (consecutive runs)</label>
          <select
            className={styles.filterSelect}
            value={failThreshold}
            onChange={(e) => setFailThreshold(Number(e.target.value))}
          >
            {[2, 3, 5, 7, 10, 15, 20].map((n) => (
              <option key={n} value={n}>
                {n} runs
              </option>
            ))}
          </select>
        </div>

        <div className={styles.metricsControlGroup}>
          <label className={styles.metricsLabel}>Timeout threshold (consecutive runs)</label>
          <select
            className={styles.filterSelect}
            value={timeoutThreshold}
            onChange={(e) => setTimeoutThreshold(Number(e.target.value))}
          >
            {[2, 3, 5, 7, 10].map((n) => (
              <option key={n} value={n}>
                {n} runs
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Tables */}
      <div className={styles.metricsGrid}>
        <MetricsTable
          title="Always Failing"
          items={failingData?.items}
          isLoading={failingLoading}
          isError={failingError}
          onRetry={() => void refetchFailing()}
          onViewRuns={setSelectedWorkflow}
          emptyMessage="No persistently failing workflows in this period"
        />
        <MetricsTable
          title="Always Timing Out"
          items={timingOutData?.items}
          isLoading={timingOutLoading}
          isError={timingOutError}
          onRetry={() => void refetchTimingOut()}
          onViewRuns={setSelectedWorkflow}
          emptyMessage="No persistently timing-out workflows in this period"
        />
      </div>

      {/* Workflow detail drawer */}
      <WorkflowDetailDrawer
        workflow={selectedWorkflow}
        lookbackDays={lookbackDays}
        onClose={() => setSelectedWorkflow(null)}
      />
    </div>
  );
}
