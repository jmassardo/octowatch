import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listSyncRuns, getSyncRun } from '../../api/sync';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import type { SyncRunSummary, SyncRunStatus } from '../../types/sync';
import { formatShortDateTime } from '../../utils/dates';
import styles from './Integrations.module.css';

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function statusVariant(status: SyncRunStatus): 'success' | 'danger' | 'attention' | 'muted' {
  switch (status) {
    case 'completed':
      return 'success';
    case 'failed':
      return 'danger';
    case 'running':
      return 'attention';
    default:
      return 'muted';
  }
}

function formatDuration(startIso: string | null, endIso: string | null): string {
  if (!startIso) return '—';
  const start = new Date(startIso).getTime();
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  const seconds = Math.floor((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

/* ------------------------------------------------------------------ */
/*  Expandable row component                                           */
/* ------------------------------------------------------------------ */

function RunRow({ run }: { run: SyncRunSummary }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <tr
        className={styles.clickableRow}
        onClick={() => setExpanded((v) => !v)}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setExpanded((v) => !v);
          }
        }}
      >
        <td>{run.triggered_by ?? run.trigger_type}</td>
        <td>{formatShortDateTime(run.started_at)}</td>
        <td>{formatDuration(run.started_at, run.completed_at)}</td>
        <td>
          <Label variant={statusVariant(run.status)}>{run.status}</Label>
        </td>
      </tr>
      {expanded && (
        <tr className={styles.expandedRow}>
          <td colSpan={4}>
            <ExpandedRunDetail runId={run.id} />
          </td>
        </tr>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Expanded detail (lazy-loaded)                                      */
/* ------------------------------------------------------------------ */

function ExpandedRunDetail({ runId }: { runId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['sync-run', runId],
    queryFn: () => getSyncRun(runId),
  });

  if (isLoading) {
    return (
      <div className={styles.expandedLoading}>
        <Spinner size={16} />
        <span>Loading details…</span>
      </div>
    );
  }

  if (isError || !data) {
    return <div className={styles.expandedLoading}>Failed to load details</div>;
  }

  return (
    <div className={styles.expandedContent}>
      {data.error_message && (
        <p className={styles.syncRunError}>{data.error_message}</p>
      )}
      {data.cursors.length > 0 ? (
        <table className={styles.entityTableNested}>
          <thead>
            <tr>
              <th>Entity</th>
              <th>Org</th>
              <th>Status</th>
              <th>Records</th>
            </tr>
          </thead>
          <tbody>
            {data.cursors.map((c) => (
              <tr key={`${c.entity_type}-${c.org ?? 'global'}`}>
                <td>{c.entity_type}</td>
                <td>{c.org ?? '—'}</td>
                <td>
                  <Label variant={statusVariant(c.status as SyncRunStatus)}>{c.status.replace('_', ' ')}</Label>
                </td>
                <td>{c.items_synced.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className={styles.expandedEmpty}>No entity-level details available</p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  SyncRunHistory component                                           */
/* ------------------------------------------------------------------ */

export function SyncRunHistory() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['sync-runs'],
    queryFn: () => listSyncRuns(1, 10),
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>Sync History</CardHeader>
        <div className={styles.syncLoading}>
          <Spinner />
          <span>Loading history…</span>
        </div>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card>
        <CardHeader>Sync History</CardHeader>
        <ErrorBanner message="Failed to load sync history" onRetry={() => refetch()} />
      </Card>
    );
  }

  const runs = data?.items ?? [];

  return (
    <Card data-testid="sync-run-history">
      <CardHeader>Sync History</CardHeader>
      {runs.length === 0 ? (
        <p className={styles.emptyText}>No sync runs yet</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.historyTable} data-testid="sync-history-table">
            <thead>
              <tr>
                <th>Triggered by</th>
                <th>Start time</th>
                <th>Duration</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <RunRow key={run.id} run={run} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
