import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listSyncRuns, getSyncRun, getSyncLogs } from '../../api/sync';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Drawer } from '../../components/primitives/Drawer';
import type { SyncRunSummary, SyncRunStatus, SyncLogEntry } from '../../types/sync';
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

function formatLogTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

/* ------------------------------------------------------------------ */
/*  Run row — clicking opens the detail drawer                        */
/* ------------------------------------------------------------------ */

function RunRow({
  run,
  isSelected,
  onSelect,
}: {
  run: SyncRunSummary;
  isSelected: boolean;
  onSelect: (id: string | null) => void;
}) {
  return (
    <tr
      className={styles.clickableRow}
      onClick={() => onSelect(isSelected ? null : run.id)}
      role="button"
      tabIndex={0}
      aria-expanded={isSelected}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(isSelected ? null : run.id);
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
  );
}

/* ------------------------------------------------------------------ */
/*  Log entry line                                                     */
/* ------------------------------------------------------------------ */

function LogLine({ entry }: { entry: SyncLogEntry }) {
  const levelClass =
    entry.level === 'error'
      ? styles.logError
      : entry.level === 'warn'
        ? styles.logWarn
        : styles.logInfo;

  return (
    <div className={`${styles.logLine} ${levelClass}`}>
      <span className={styles.logTimestamp}>{formatLogTime(entry.timestamp)}</span>
      <span className={styles.logLevel}>[{entry.level}]</span>
      {(entry.entity_type || entry.org) && (
        <span className={styles.logTimestamp}>
          {[entry.entity_type, entry.org].filter(Boolean).join(' / ')}
        </span>
      )}
      <span className={styles.logMessage}>{entry.message}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Drawer content: entity table + log stream                         */
/* ------------------------------------------------------------------ */

function RunDetailDrawer({ runId }: { runId: string }) {
  const { data: run, isLoading: runLoading } = useQuery({
    queryKey: ['sync-run', runId],
    queryFn: () => getSyncRun(runId),
  });

  const { data: logsData, isLoading: logsLoading } = useQuery({
    queryKey: ['sync-run-logs', runId],
    queryFn: () => getSyncLogs(runId, 0),
    refetchInterval: run?.status === 'running' ? 3000 : false,
  });

  if (runLoading) {
    return (
      <div className={styles.expandedLoading}>
        <Spinner size={16} />
        <span>Loading…</span>
      </div>
    );
  }

  if (!run) {
    return <div className={styles.expandedLoading}>Failed to load run details</div>;
  }

  const entries = logsData?.entries ?? [];

  return (
    <div className={styles.expandedContent}>
      {/* Top-level error */}
      {run.error_message && <p className={styles.syncRunError}>{run.error_message}</p>}

      {/* Entity breakdown table */}
      {run.cursors.length > 0 && (
        <>
          <h4
            style={{
              margin: '0 0 8px',
              fontSize: 13,
              fontWeight: 600,
              color: 'var(--color-fg-muted, #666)',
            }}
          >
            Entity breakdown
          </h4>
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
              {run.cursors.map((c) => (
                <tr key={`${c.entity_type}-${c.org ?? 'global'}`}>
                  <td>{c.entity_type}</td>
                  <td>{c.org ?? '—'}</td>
                  <td>
                    <Label variant={statusVariant(c.status as SyncRunStatus)}>
                      {c.status.replace('_', ' ')}
                    </Label>
                  </td>
                  <td>{c.items_synced.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {/* Log stream */}
      <h4
        style={{
          margin: '16px 0 8px',
          fontSize: 13,
          fontWeight: 600,
          color: 'var(--color-fg-muted, #666)',
        }}
      >
        Log
      </h4>
      {logsLoading ? (
        <div className={styles.expandedLoading}>
          <Spinner size={14} />
          <span>Loading logs…</span>
        </div>
      ) : entries.length === 0 ? (
        <p className={styles.logEmpty}>No log entries for this run</p>
      ) : (
        <div className={styles.logViewerContainer}>
          {entries.map((e) => (
            <LogLine key={e.seq} entry={e} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  SyncRunHistory component                                           */
/* ------------------------------------------------------------------ */

export function SyncRunHistory() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

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
  const selectedRun = runs.find((r) => r.id === selectedRunId);

  return (
    <>
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
                  <RunRow
                    key={run.id}
                    run={run}
                    isSelected={run.id === selectedRunId}
                    onSelect={setSelectedRunId}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Drawer
        open={!!selectedRunId}
        onClose={() => setSelectedRunId(null)}
        title={selectedRun ? `Run · ${formatShortDateTime(selectedRun.started_at)}` : 'Run Details'}
      >
        {selectedRunId && <RunDetailDrawer runId={selectedRunId} />}
      </Drawer>
    </>
  );
}
