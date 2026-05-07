import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listScanActivity } from '../../api/workflowScanner';
import type { ScanActivity } from '../../api/workflowScanner';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Label } from '../../components/primitives/Label';
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

  const {
    data,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['workflow-scanner', 'activity', page],
    queryFn: () => listScanActivity({ page, page_size: 20 }),
  });

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
          Scanner activity will appear here when workflows are automatically analyzed
          from ingested events or when you trigger a manual scan.
        </div>
      </div>
    );
  }

  const totalPages = Math.ceil(data.total / 20);

  return (
    <div>
      <table className={styles.findingsTable}>
        <thead>
          <tr>
            <th>Status</th>
            <th>Workflow</th>
            <th>Trigger</th>
            <th>Findings</th>
            <th>Data Sources</th>
            <th>Duration</th>
            <th>When</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((a) => (
            <tr
              key={a.id}
              className={`${styles.findingRow} ${selectedActivity?.id === a.id ? styles.findingRowSelected : ''}`}
              onClick={() => setSelectedActivity(selectedActivity?.id === a.id ? null : a)}
            >
              <td>
                <Label variant={statusVariant(a.status)}>{a.status}</Label>
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
              </td>
              <td>
                <Label variant={findingsVariant(a.findings_count)}>
                  {a.findings_count}
                </Label>
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
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </button>
          <span>
            Page {page} of {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
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
