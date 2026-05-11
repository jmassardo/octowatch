import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listScanActivity } from '../../api/workflowScanner';
import type { ScanActivity } from '../../api/workflowScanner';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Label } from '../../components/primitives/Label';
import { MetricCard } from '../../components/primitives/MetricCard';
import { formatRelativeShort } from '../../utils/dates';
import styles from './Workflows.module.css';

function statusVariant(status: string) {
  if (status === 'completed') return 'success' as const;
  if (status === 'running') return 'attention' as const;
  if (status === 'failed') return 'danger' as const;
  return 'muted' as const;
}

function findingsVariant(count: number) {
  if (count === 0) return 'success' as const;
  if (count <= 3) return 'attention' as const;
  return 'danger' as const;
}

function formatDuration(ms: number | null): string {
  if (ms === null) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function dataSourceLabel(source: string): string {
  if (source === 'audit_log') return 'Audit Log';
  if (source === 'github_api') return 'GitHub API';
  return source;
}

function scanResultIcon(activity: ScanActivity): string {
  if (activity.status === 'running') return '🔄';
  if (activity.status === 'failed') return '⚠️';
  if (activity.findings_count === 0) return '🟢';
  const hasHighSeverity = activity.checks_performed.some(
    (c) => c.includes('self-hosted') || c.includes('script-injection'),
  );
  if (hasHighSeverity && activity.findings_count > 0) return '🔴';
  return '🟡';
}

function ActivityDetailPanel({
  activity,
  onClose,
}: {
  activity: ScanActivity;
  onClose: () => void;
}) {
  return (
    <div className={styles.panelHeader}>
      <div className={styles.panelTitle}>
        {activity.org}/{activity.repo}
      </div>
      <button className={styles.panelClose} onClick={onClose}>
        &#215;
      </button>
      <div className={styles.panelBody}>
        <div className={styles.panelSection}>
          <div className={styles.panelSectionTitle}>Workflow</div>
          <code>{activity.workflow_path}</code>
        </div>

        <div className={styles.panelSection}>
          <div className={styles.panelSectionTitle}>Trigger Event IDs</div>
          {activity.trigger_event_ids.length > 0 ? (
            <p className={styles.panelText}>{activity.trigger_event_ids.join(', ')}</p>
          ) : (
            <p className={styles.panelText}>Manual trigger</p>
          )}
        </div>

        <div className={styles.panelSection}>
          <div className={styles.panelSectionTitle}>Checks Performed</div>
          {activity.checks_performed.length > 0 ? (
            <ul className={styles.panelGuidance}>
              {activity.checks_performed.map((check) => (
                <li key={check}>{check}</li>
              ))}
            </ul>
          ) : (
            <p className={styles.panelText}>No checks recorded</p>
          )}
        </div>

        <div className={styles.panelSection}>
          <div className={styles.panelSectionTitle}>Results</div>
          <div className={styles.panelKv}>
            <span className={styles.panelLabel}>Status</span>
            <Label variant={statusVariant(activity.status)}>{activity.status}</Label>
          </div>
          <div className={styles.panelKv}>
            <span className={styles.panelLabel}>Findings</span>
            <span>{activity.findings_count}</span>
          </div>
          <div className={styles.panelKv}>
            <span className={styles.panelLabel}>Duration</span>
            <span>{formatDuration(activity.duration_ms)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ScannerActivityTab() {
  const [page, setPage] = useState(1);
  const [selectedActivity, setSelectedActivity] = useState<ScanActivity | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['workflow-scanner', 'activity', page],
    queryFn: () => listScanActivity({ page, page_size: 20 }),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      return items.some((a) => a.status === 'running') ? 5000 : false;
    },
  });

  const stats = useMemo(() => {
    const items = data?.items ?? [];
    const total = data?.total ?? 0;
    const eventDriven = items.filter((a) => a.trigger_event_ids.length > 0).length;
    const totalFindings = items.reduce((sum, a) => sum + a.findings_count, 0);
    const completedItems = items.filter((a) => a.duration_ms !== null);
    const avgDuration =
      completedItems.length > 0
        ? Math.round(
            completedItems.reduce((sum, a) => sum + (a.duration_ms ?? 0), 0) /
              completedItems.length,
          )
        : 0;
    return { total, eventDriven, totalFindings, avgDuration, pageItems: items.length };
  }, [data]);

  if (isLoading) return <Spinner />;
  if (isError) {
    return <ErrorBanner message="Failed to load scanner activity" onRetry={() => void refetch()} />;
  }

  if (!data || data.items.length === 0) {
    return (
      <div className={styles.emptyState}>
        <div className={styles.emptyIcon}>📋</div>
        <div className={styles.emptyTitle}>No scanner activity yet</div>
        <div className={styles.emptyDesc}>
          Scanner activity will appear here when workflows are automatically analyzed from ingested
          events or when you trigger a manual scan.
        </div>
      </div>
    );
  }

  const totalPages = Math.ceil(data.total / 20);

  return (
    <div>
      <div className={styles.activitySummary}>
        <MetricCard
          value={String(stats.total)}
          label="Total Scans"
          helpText="Total number of workflow scans recorded"
        />
        <MetricCard
          value={
            stats.pageItems > 0
              ? `${Math.round((stats.eventDriven / stats.pageItems) * 100)}%`
              : '0%'
          }
          label="Event-Driven"
          helpText="Percentage of scans triggered by audit log events (vs manual)"
        />
        <MetricCard
          value={String(stats.totalFindings)}
          label="Findings (page)"
          helpText="Total findings from scans on this page"
        />
        <MetricCard
          value={formatDuration(stats.avgDuration)}
          label="Avg Duration"
          helpText="Average scan duration for completed scans on this page"
        />
      </div>

      <table className={styles.findingsTable}>
        <thead>
          <tr>
            <th scope="col" style={{ width: '36px' }}></th>
            <th scope="col">Status</th>
            <th scope="col">Workflow</th>
            <th scope="col">Trigger</th>
            <th scope="col">Findings</th>
            <th scope="col">Data Sources</th>
            <th scope="col">Duration</th>
            <th scope="col">When</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((a) => (
            <tr
              key={a.id}
              className={`${styles.findingRow} ${selectedActivity?.id === a.id ? styles.findingRowSelected : ''}`}
              onClick={() => setSelectedActivity(selectedActivity?.id === a.id ? null : a)}
            >
              <td
                title={
                  a.status === 'running'
                    ? 'Scan in progress'
                    : a.findings_count === 0
                      ? 'No findings'
                      : `${a.findings_count} findings`
                }
              >
                {scanResultIcon(a)}
              </td>
              <td>
                <Label variant={statusVariant(a.status)}>
                  {a.status}
                  {a.status === 'running' && ' …'}
                </Label>
              </td>
              <td className={styles.repoPath}>
                {a.org}/{a.repo}
                <br />
                <small>{a.workflow_path}</small>
              </td>
              <td>
                <Label variant={a.trigger_event_ids.length > 0 ? 'accent' : 'muted'}>
                  {a.trigger_event_ids.length > 0 ? 'Event-driven' : 'Manual'}
                </Label>
                {a.trigger_event_ids.length > 0 && (
                  <small className={styles.triggerCount}>
                    {a.trigger_event_ids.length} event{a.trigger_event_ids.length !== 1 ? 's' : ''}
                  </small>
                )}
              </td>
              <td>
                <Label variant={findingsVariant(a.findings_count)}>{a.findings_count}</Label>
              </td>
              <td>
                {a.data_sources.map((ds) => (
                  <Label key={ds} variant="muted">
                    {dataSourceLabel(ds)}
                  </Label>
                ))}
              </td>
              <td>{formatDuration(a.duration_ms)}</td>
              <td className={styles.timeCell}>{formatRelativeShort(a.started_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div className={styles.filters}>
          <button disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
            Previous
          </button>
          <span>
            Page {page} of {totalPages}
          </span>
          <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Next
          </button>
        </div>
      )}

      {selectedActivity && (
        <ActivityDetailPanel
          activity={selectedActivity}
          onClose={() => setSelectedActivity(null)}
        />
      )}
    </div>
  );
}
