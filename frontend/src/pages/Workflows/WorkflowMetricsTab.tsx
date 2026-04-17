import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getAlwaysFailingWorkflows,
  getAlwaysTimingOutWorkflows,
  getWorkflowRunHistory,
} from '../../api/workflowMetrics';
import type { WorkflowFailureSummary } from '../../api/workflowMetrics';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Button } from '../../components/primitives/Button';
import { formatRelativeShort } from '../../utils/dates';
import styles from './Workflows.module.css';

// ── Helpers ───────────────────────────────────────────────────────────────────

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

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—';
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

// ── Run History Modal ─────────────────────────────────────────────────────────

interface RunHistoryModalProps {
  workflow: WorkflowFailureSummary;
  lookbackDays: number;
  onClose: () => void;
}

function RunHistoryModal({ workflow, lookbackDays, onClose }: RunHistoryModalProps) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: [
      'workflow-metrics',
      'run-history',
      workflow.org,
      workflow.repo,
      workflow.workflow_name,
      lookbackDays,
    ],
    queryFn: () =>
      getWorkflowRunHistory({
        org: workflow.org,
        repo: workflow.repo,
        workflow_name: workflow.workflow_name,
        lookback_days: lookbackDays,
        limit: 20,
      }),
    staleTime: 60_000,
  });

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modalPanel} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <div>
            <div className={styles.modalTitle}>Run History</div>
            <div className={styles.modalSub}>
              {workflow.org}/{workflow.repo} — {workflow.workflow_name}
            </div>
          </div>
          <button className={styles.panelClose} onClick={onClose}>
            &#215;
          </button>
        </div>
        <div className={styles.modalBody}>
          {isLoading && <Spinner />}
          {isError && (
            <ErrorBanner
              message="Failed to load run history"
              onRetry={() => void refetch()}
            />
          )}
          {data && data.runs.length === 0 && (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon}>📭</div>
              <div className={styles.emptyTitle}>No runs found</div>
              <div className={styles.emptyDesc}>
                No workflow runs found in the last {lookbackDays} days.
              </div>
            </div>
          )}
          {data && data.runs.length > 0 && (
            <table className={styles.findingsTable}>
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Started</th>
                  <th>Conclusion</th>
                  <th>Duration</th>
                </tr>
              </thead>
              <tbody>
                {data.runs.map((run, idx) => (
                  <tr key={run.run_id ?? idx}>
                    <td className={styles.repoPath}>{run.run_id ?? '—'}</td>
                    <td className={styles.timeCell}>{formatRelativeShort(run.started_at)}</td>
                    <td>
                      <span className={`${styles.conclusionBadge} ${conclusionBadge(run.conclusion)}`}>
                        {run.conclusion}
                      </span>
                    </td>
                    <td className={styles.timeCell}>{formatDuration(run.duration_seconds)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
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

function MetricsTable({
  title,
  items,
  isLoading,
  isError,
  onRetry,
  onViewRuns,
  emptyMessage,
}: MetricsTableProps) {
  return (
    <div className={styles.metricsSection}>
      <div className={styles.metricsSectionTitle}>{title}</div>
      {isLoading && <Spinner />}
      {isError && <ErrorBanner message={`Failed to load ${title.toLowerCase()}`} onRetry={onRetry} />}
      {!isLoading && !isError && items && items.length === 0 && (
        <div className={styles.metricsEmptyState}>
          <span className={styles.metricsEmptyIcon}>✅</span>
          <span>{emptyMessage}</span>
        </div>
      )}
      {!isLoading && !isError && items && items.length > 0 && (
        <table className={styles.findingsTable}>
          <thead>
            <tr>
              <th>Org</th>
              <th>Repository</th>
              <th>Workflow</th>
              <th>Consecutive</th>
              <th>Last Run</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={`${item.org}/${item.repo}/${item.workflow_name}`}>
                <td>{item.org}</td>
                <td className={styles.repoPath}>{item.repo}</td>
                <td className={styles.repoPath}>{item.workflow_name}</td>
                <td>
                  <span className={`${styles.conclusionBadge} ${conclusionBadge(item.last_conclusion)}`}>
                    {item.consecutive_count}×
                  </span>
                </td>
                <td className={styles.timeCell}>{formatRelativeShort(item.last_run_at)}</td>
                <td>
                  <Button size="sm" variant="default" onClick={() => onViewRuns(item)}>
                    View Runs
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
    queryKey: [
      'workflow-metrics',
      'failing',
      failThreshold,
      lookbackDays,
      orgFilter ?? 'all',
    ],
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
                className={[
                  styles.statusChip,
                  lookbackDays === days ? styles.statusChipActive : '',
                ]
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

      {/* Run history modal */}
      {selectedWorkflow && (
        <RunHistoryModal
          workflow={selectedWorkflow}
          lookbackDays={lookbackDays}
          onClose={() => setSelectedWorkflow(null)}
        />
      )}
    </div>
  );
}
