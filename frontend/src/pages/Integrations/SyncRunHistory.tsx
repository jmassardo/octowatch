import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listSyncRuns, getSyncRun, getSyncLogs } from '../../api/sync';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Drawer } from '../../components/primitives/Drawer';
import type { SyncRunSummary, SyncRunStatus, SyncLogEntry, EntityStatus } from '../../types/sync';
import { formatShortDateTime } from '../../utils/dates';
import styles from './Integrations.module.css';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

/**
 * Discriminated union describing which view is currently shown in the
 * right-hand drawer.
 *
 * - `org-categories`: category list for a specific org inside a run
 * - `entity-logs`:    log entries for a specific org + entity_type
 */
type DrawerView =
  | { kind: 'org-categories'; runId: string; org: string | null }
  | { kind: 'entity-logs'; runId: string; org: string | null; entityType: string };

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

/** Returns a human-readable label for an org value (null → "Enterprise"). */
function orgDisplayName(org: string | null): string {
  return org ?? 'Enterprise';
}

/**
 * Extracts the ordered list of unique org values from a cursor list.
 * Preserves first-seen insertion order.
 */
function extractOrgs(cursors: EntityStatus[]): (string | null)[] {
  const seen = new Set<string>();
  const result: (string | null)[] = [];
  for (const c of cursors) {
    const key = c.org ?? '__null__';
    if (!seen.has(key)) {
      seen.add(key);
      result.push(c.org);
    }
  }
  return result;
}

/** Builds the drawer title string for the current view. */
function buildDrawerTitle(view: DrawerView): string {
  if (view.kind === 'org-categories') {
    return `${orgDisplayName(view.org)} — categories`;
  }
  return `${view.entityType} · ${orgDisplayName(view.org)} — logs`;
}

/* ------------------------------------------------------------------ */
/*  Run row — clicking inline-expands the org breakdown               */
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

/* ------------------------------------------------------------------ */
/*  Expanded row — org breakdown; each org row opens the drawer       */
/* ------------------------------------------------------------------ */

function OrgBreakdown({
  runId,
  onOrgClick,
}: {
  runId: string;
  onOrgClick: (view: DrawerView) => void;
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
              <table className={styles.entityTableNested} data-testid="org-breakdown-table">
                <thead>
                  <tr>
                    <th scope="col">Organisation</th>
                    <th scope="col">Categories</th>
                    <th scope="col">Records</th>
                  </tr>
                </thead>
                <tbody>
                  {extractOrgs(run.cursors).map((org) => {
                    const orgCursors = run.cursors.filter((c) => c.org === org);
                    const totalRecords = orgCursors.reduce((s, c) => s + c.items_synced, 0);
                    return (
                      <tr
                        key={org ?? '__enterprise__'}
                        className={styles.clickableRow}
                        title="Click to view categories"
                        onClick={(e) => {
                          e.stopPropagation();
                          onOrgClick({ kind: 'org-categories', runId, org });
                        }}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            e.stopPropagation();
                            onOrgClick({ kind: 'org-categories', runId, org });
                          }
                        }}
                      >
                        <td>{orgDisplayName(org)}</td>
                        <td>{orgCursors.length}</td>
                        <td>{totalRecords.toLocaleString()}</td>
                      </tr>
                    );
                  })}
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

/* Wrapper renders RunRow + optional OrgBreakdown as a keyed fragment */
function RunRowWithDetail({
  run,
  isExpanded,
  onToggle,
  onOrgClick,
}: {
  run: SyncRunSummary;
  isExpanded: boolean;
  onToggle: () => void;
  onOrgClick: (view: DrawerView) => void;
}) {
  return (
    <>
      <RunRow run={run} isExpanded={isExpanded} onToggle={onToggle} />
      {isExpanded && <OrgBreakdown runId={run.id} onOrgClick={onOrgClick} />}
    </>
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
/*  Drawer content — category list for a specific org                 */
/* ------------------------------------------------------------------ */

function OrgCategoriesContent({
  runId,
  org,
  onCategoryClick,
}: {
  runId: string;
  org: string | null;
  onCategoryClick: (entityType: string) => void;
}) {
  const { data: run, isLoading } = useQuery({
    queryKey: ['sync-run', runId],
    queryFn: () => getSyncRun(runId),
  });

  if (isLoading) {
    return (
      <div className={styles.expandedLoading}>
        <Spinner size={14} />
        <span>Loading…</span>
      </div>
    );
  }

  if (!run) {
    return <div className={styles.expandedLoading}>Failed to load run details</div>;
  }

  const cursors = run.cursors.filter((c) => c.org === org);

  return (
    <div className={styles.expandedContent}>
      {cursors.length === 0 ? (
        <p className={styles.logEmpty}>No categories for this organisation</p>
      ) : (
        <table className={styles.entityTableNested} data-testid="org-categories-table">
          <thead>
            <tr>
              <th scope="col">Category</th>
              <th scope="col">Status</th>
              <th scope="col">Records</th>
            </tr>
          </thead>
          <tbody>
            {cursors.map((c) => (
              <tr
                key={c.entity_type}
                className={styles.clickableRow}
                title="Click to view logs"
                onClick={() => onCategoryClick(c.entity_type)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onCategoryClick(c.entity_type);
                  }
                }}
              >
                <td>{c.entity_type}</td>
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
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Drawer content — logs for a specific org + entity_type            */
/* ------------------------------------------------------------------ */

function EntityLogContent({
  runId,
  org,
  entityType,
  onBack,
}: {
  runId: string;
  org: string | null;
  entityType: string;
  onBack: () => void;
}) {
  const { data: run } = useQuery({
    queryKey: ['sync-run', runId],
    queryFn: () => getSyncRun(runId),
  });

  const { data: logsData, isLoading } = useQuery({
    queryKey: ['sync-run-logs', runId, entityType, org],
    queryFn: () => getSyncLogs(runId, 0),
    refetchInterval: run?.status === 'running' ? 3000 : false,
  });

  const entries = (logsData?.entries ?? []).filter(
    (e: SyncLogEntry) => e.entity_type === entityType && e.org === org,
  );

  return (
    <div className={styles.expandedContent}>
      <button
        type="button"
        className={styles.drawerBackBtn}
        onClick={onBack}
        aria-label="Back to categories"
      >
        ← Back
      </button>
      {isLoading ? (
        <div className={styles.expandedLoading}>
          <Spinner size={14} />
          <span>Loading logs…</span>
        </div>
      ) : entries.length === 0 ? (
        <p className={styles.logEmpty}>No log entries for this category</p>
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
/*  Drawer view switcher                                               */
/* ------------------------------------------------------------------ */

function DrawerContent({
  view,
  onViewChange,
}: {
  view: DrawerView;
  onViewChange: (next: DrawerView) => void;
}) {
  if (view.kind === 'org-categories') {
    return (
      <OrgCategoriesContent
        runId={view.runId}
        org={view.org}
        onCategoryClick={(entityType) =>
          onViewChange({ kind: 'entity-logs', runId: view.runId, org: view.org, entityType })
        }
      />
    );
  }

  return (
    <EntityLogContent
      runId={view.runId}
      org={view.org}
      entityType={view.entityType}
      onBack={() => onViewChange({ kind: 'org-categories', runId: view.runId, org: view.org })}
    />
  );
}

/* ------------------------------------------------------------------ */
/*  SyncRunHistory component                                           */
/* ------------------------------------------------------------------ */

export function SyncRunHistory() {
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [drawerView, setDrawerView] = useState<DrawerView | null>(null);

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
                  <th scope="col">Triggered by</th>
                  <th scope="col">Start time</th>
                  <th scope="col">Duration</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <RunRowWithDetail
                    key={run.id}
                    run={run}
                    isExpanded={run.id === expandedRunId}
                    onToggle={() => setExpandedRunId(run.id === expandedRunId ? null : run.id)}
                    onOrgClick={setDrawerView}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Drawer
        open={!!drawerView}
        onClose={() => setDrawerView(null)}
        title={drawerView ? buildDrawerTitle(drawerView) : ''}
      >
        {drawerView && <DrawerContent view={drawerView} onViewChange={setDrawerView} />}
      </Drawer>
    </>
  );
}
