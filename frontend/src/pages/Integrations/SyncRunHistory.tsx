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

interface DrawerTarget {
  runId: string;
  entityType: string;
  org: string | null;
}

/* ------------------------------------------------------------------ */
/*  Run row — clicking inline-expands the entity breakdown            */
/* ------------------------------------------------------------------ */

function RunRow({
  run,
  isExpanded,
  onToggle,
}: {
  run: SyncRunSummary;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <tr
      className={styles.clickableRow}
      onClick={onToggle}
      role="button"
      tabIndex={0}
      aria-expanded={isExpanded}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onToggle();
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

/* Wrapper renders RunRow + optional ExpandedRunContent as a keyed fragment */
function RunRowWithDetail({
  run,
  isExpanded,
  onToggle,
  onEntityClick,
}: {
  run: SyncRunSummary;
  isExpanded: boolean;
  onToggle: () => void;
  onEntityClick: (target: DrawerTarget) => void;
}) {
  return (
    <>
      <RunRow run={run} isExpanded={isExpanded} onToggle={onToggle} />
      {isExpanded && <ExpandedRunContent runId={run.id} onEntityClick={onEntityClick} />}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Expanded row — entity breakdown; each entity row opens the drawer */
/* ------------------------------------------------------------------ */

function ExpandedRunContent({
  runId,
  onEntityClick,
}: {
  runId: string;
  onEntityClick: (target: DrawerTarget) => void;
}) {
  const { data: run, isLoading } = useQuery({
    queryKey: ['sync-run', runId],
    queryFn: () => getSyncRun(runId),
  });

  return (
    <tr className={styles.expandedRow}>
      <td colSpan={4}>
        {isLoading ? (
          <div className={styles.expandedLoading}>
            <Spinner size={16} />
            <span>Loading…</span>
          </div>
        ) : !run ? (
          <div className={styles.expandedLoading}>Failed to load run details</div>
        ) : (
          <div className={styles.expandedContent}>
            {run.error_message && <p className={styles.syncRunError}>{run.error_message}</p>}
            {run.cursors.length > 0 ? (
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
                    <tr
                      key={`${c.entity_type}-${c.org ?? 'global'}`}
                      className={styles.clickableRow}
                      title="Click to view logs"
                      onClick={(e) => {
                        e.stopPropagation();
                        onEntityClick({ runId, entityType: c.entity_type, org: c.org ?? null });
                      }}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          e.stopPropagation();
                          onEntityClick({ runId, entityType: c.entity_type, org: c.org ?? null });
                        }
                      }}
                    >
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
            ) : (
              !run.error_message && <p className={styles.logEmpty}>No entity data for this run</p>
            )}
          </div>
        )}
      </td>
    </tr>
  );
}

/* ------------------------------------------------------------------ */
/*  Log entry line                                                     */
/* ------------------------------------------------------------------ */

function LogLine({ entry, showContext = true }: { entry: SyncLogEntry; showContext?: boolean }) {
  const levelClass =
    entry.level === 'error'
      ? styles.logError
      : entry.level === 'warn'
        ? styles.logWarn
        : styles.logInfo;

  const context =
    showContext && (entry.entity_type || entry.org)
      ? [entry.entity_type, entry.org].filter(Boolean).join(' / ')
      : null;

  return (
    <div className={`${styles.logLine} ${levelClass}`}>
      <div className={styles.logMeta}>
        <span className={styles.logTimestamp}>{formatLogTime(entry.timestamp)}</span>
        <span className={styles.logLevel}>[{entry.level}]</span>
        {context && <span className={styles.logContext}>{context}</span>}
      </div>
      <div className={styles.logMessage}>{entry.message}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Drawer content — logs filtered to a specific entity               */
/* ------------------------------------------------------------------ */

function EntityLogDrawer({ target }: { target: DrawerTarget }) {
  const { data: run } = useQuery({
    queryKey: ['sync-run', target.runId],
    queryFn: () => getSyncRun(target.runId),
  });

  const { data: logsData, isLoading } = useQuery({
    queryKey: ['sync-run-logs', target.runId, target.entityType],
    queryFn: () => getSyncLogs(target.runId, 0),
    refetchInterval: run?.status === 'running' ? 3000 : false,
  });

  const entries = (logsData?.entries ?? []).filter(
    (e: SyncLogEntry) => e.entity_type === target.entityType,
  );

  if (isLoading) {
    return (
      <div className={styles.expandedLoading}>
        <Spinner size={14} />
        <span>Loading logs…</span>
      </div>
    );
  }

  return (
    <div className={styles.expandedContent}>
      {entries.length === 0 ? (
        <p className={styles.logEmpty}>No log entries for this entity</p>
      ) : (
        <div className={styles.logViewerContainer}>
          {entries.map((e) => (
            <LogLine key={e.seq} entry={e} showContext={false} />
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
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [drawerTarget, setDrawerTarget] = useState<DrawerTarget | null>(null);

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

  const drawerTitle = drawerTarget
    ? `${drawerTarget.entityType}${drawerTarget.org ? ` · ${drawerTarget.org}` : ''} — logs`
    : 'Logs';

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
                  <RunRowWithDetail
                    key={run.id}
                    run={run}
                    isExpanded={run.id === expandedRunId}
                    onToggle={() => setExpandedRunId(run.id === expandedRunId ? null : run.id)}
                    onEntityClick={setDrawerTarget}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Drawer open={!!drawerTarget} onClose={() => setDrawerTarget(null)} title={drawerTitle}>
        {drawerTarget && <EntityLogDrawer target={drawerTarget} />}
      </Drawer>
    </>
  );
}
