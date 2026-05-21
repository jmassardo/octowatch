import { useMemo, useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getSyncStatus,
  listSyncRuns,
  getSyncSchedule,
  getSyncConfig,
  getSyncRun,
} from '../../api/sync';
import { PageHeader } from '../../components/common/PageHeader';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Drawer } from '../../components/primitives/Drawer';
import { Pagination } from '../../components/primitives/Pagination';
import { usePermissions } from '../../hooks/usePermissions';
import { formatRelativeShort, formatShortDateTime } from '../../utils/dates';
import type {
  SyncRun,
  SyncRunSummary,
  SyncRunStatus,
  SyncSchedule as SyncScheduleType,
  EntityStatus,
} from '../../types/sync';
import styles from './SyncStatus.module.css';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const RUNS_PAGE_SIZE = 5;

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type HealthLevel = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';

interface SyncTypeCard {
  readonly title: string;
  readonly description: string;
  readonly health: HealthLevel;
  readonly lastRun: string | null;
  readonly lastStatus: SyncRunStatus | null;
  readonly itemCount: number;
}

/** Error detail extracted from the most recent failed run. */
interface FailureDetail {
  readonly errorMessage: string;
  readonly failedEntity: string | null;
  readonly failedCursor: string | null;
  readonly remediation: string;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function deriveHealth(runs: SyncRunSummary[]): HealthLevel {
  if (runs.length === 0) return 'unknown';
  const recent = runs.slice(0, 5);
  const failures = recent.filter((r) => r.status === 'failed').length;
  if (failures === 0) return 'healthy';
  if (failures <= 2) return 'degraded';
  return 'unhealthy';
}

function overallHealth(cards: SyncTypeCard[]): HealthLevel {
  if (cards.length === 0) return 'unknown';
  if (cards.some((c) => c.health === 'unhealthy')) return 'unhealthy';
  if (cards.some((c) => c.health === 'degraded')) return 'degraded';
  if (cards.every((c) => c.health === 'unknown')) return 'unknown';
  return 'healthy';
}

function healthBannerClass(health: HealthLevel): string {
  switch (health) {
    case 'healthy':
      return styles.bannerHealthy;
    case 'degraded':
      return styles.bannerDegraded;
    case 'unhealthy':
      return styles.bannerUnhealthy;
    default:
      return styles.bannerUnknown;
  }
}

function healthLabel(health: HealthLevel): string {
  switch (health) {
    case 'healthy':
      return 'All Syncs Healthy';
    case 'degraded':
      return 'Sync Degraded';
    case 'unhealthy':
      return 'Sync Unhealthy';
    default:
      return 'No Sync Data';
  }
}

function healthDetail(health: HealthLevel, totalRuns: number): string {
  switch (health) {
    case 'healthy':
      return `All recent sync runs completed successfully (${totalRuns} total runs)`;
    case 'degraded':
      return 'Some recent sync runs have failed — check individual sync types below';
    case 'unhealthy':
      return 'Multiple recent sync failures detected — immediate attention required';
    default:
      return 'No sync runs have been recorded yet';
  }
}

/**
 * Extract actionable failure details from the most recent failed run.
 * Returns null if there is no failure to report.
 */
function extractFailureDetail(
  currentRun: SyncRun | null | undefined,
  runs: SyncRunSummary[],
): FailureDetail | null {
  // Use currentRun if it's failed, otherwise look for the most recent failed run
  if (currentRun?.status === 'failed' && currentRun.error_message) {
    const failedCursor = currentRun.cursors?.find((c: EntityStatus) => c.status === 'failed');
    return {
      errorMessage: currentRun.error_message,
      failedEntity: failedCursor?.entity_type ?? null,
      failedCursor: failedCursor?.last_cursor ?? null,
      remediation: deriveRemediation(currentRun.error_message),
    };
  }

  // Check last failed run from summaries — no detail available without full run data
  const lastFailed = runs.find((r) => r.status === 'failed');
  if (!lastFailed) return null;

  return {
    errorMessage: 'Last sync run failed — click the run in the table below for details',
    failedEntity: null,
    failedCursor: null,
    remediation: 'Review the failed run details and check GitHub App credentials and permissions',
  };
}

/** Derive a remediation suggestion from error text. */
function deriveRemediation(errorMessage: string): string {
  const lower = errorMessage.toLowerCase();
  if (lower.includes('rate limit')) {
    return 'Wait for the rate limit window to reset, or reduce sync frequency in Settings → GitHub';
  }
  if (lower.includes('401') || lower.includes('unauthorized') || lower.includes('credential')) {
    return 'Verify GitHub App credentials in Settings → GitHub and re-authenticate if needed';
  }
  if (lower.includes('403') || lower.includes('forbidden') || lower.includes('permission')) {
    return 'Check GitHub App installation permissions — ensure required scopes are granted';
  }
  if (lower.includes('timeout') || lower.includes('timed out')) {
    return 'The sync timed out — consider reducing scope or triggering a manual retry';
  }
  if (lower.includes('auto-expired') || lower.includes('no progress')) {
    return 'The worker process may be down — check backend service health and restart if needed';
  }
  return 'Review the error details and check GitHub App configuration in Settings → GitHub';
}

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
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

/** Health summary banner displayed at the top of the page with specific error details. */
function HealthBanner({
  health,
  totalRuns,
  failureDetail,
}: {
  health: HealthLevel;
  totalRuns: number;
  failureDetail: FailureDetail | null;
}) {
  const showErrorDetails = (health === 'unhealthy' || health === 'degraded') && failureDetail;

  return (
    <div
      className={`${styles.healthBanner} ${healthBannerClass(health)}`}
      data-testid="health-banner"
      role="status"
    >
      <HealthIcon health={health} />
      <div className={styles.bannerText}>
        <span className={styles.bannerTitle}>{healthLabel(health)}</span>
        {showErrorDetails ? (
          <div className={styles.bannerErrorDetails} data-testid="health-banner-error-details">
            <span className={styles.bannerDetail}>{failureDetail.errorMessage}</span>
            {failureDetail.failedEntity && (
              <span className={styles.bannerMeta}>
                Failed entity: <strong>{failureDetail.failedEntity}</strong>
                {failureDetail.failedCursor && (
                  <>
                    {' '}
                    — cursor: <code>{failureDetail.failedCursor}</code>
                  </>
                )}
              </span>
            )}
            <span className={styles.bannerRemediation}>💡 {failureDetail.remediation}</span>
          </div>
        ) : (
          <span className={styles.bannerDetail}>{healthDetail(health, totalRuns)}</span>
        )}
      </div>
    </div>
  );
}

/** SVG icon matching the health level. */
function HealthIcon({ health }: { health: HealthLevel }) {
  if (health === 'healthy') {
    return (
      <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
        <path d="M8 16A8 8 0 108 0a8 8 0 000 16zm3.78-9.72a.75.75 0 00-1.06-1.06L7 8.94 5.28 7.22a.75.75 0 00-1.06 1.06l2.25 2.25a.75.75 0 001.06 0l4.25-4.25z" />
      </svg>
    );
  }
  if (health === 'unhealthy') {
    return (
      <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
        <path d="M2.343 13.657A8 8 0 1113.657 2.343 8 8 0 012.343 13.657zM6.03 4.97a.75.75 0 00-1.06 1.06L6.94 8 4.97 9.97a.75.75 0 101.06 1.06L8 9.06l1.97 1.97a.75.75 0 101.06-1.06L9.06 8l1.97-1.97a.75.75 0 10-1.06-1.06L8 6.94 6.03 4.97z" />
      </svg>
    );
  }
  if (health === 'degraded') {
    return (
      <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
        <path d="M6.457 1.047c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0114.082 15H1.918a1.75 1.75 0 01-1.543-2.575zM8 5a.75.75 0 00-.75.75v2.5a.75.75 0 001.5 0v-2.5A.75.75 0 008 5zm1 6a1 1 0 11-2 0 1 1 0 012 0z" />
      </svg>
    );
  }
  return (
    <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M0 8a8 8 0 1116 0A8 8 0 010 8zm8-6.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM6.5 7.75A.75.75 0 017.25 7h1a.75.75 0 01.75.75v2.75h.25a.75.75 0 010 1.5h-2a.75.75 0 010-1.5h.25v-2h-.25a.75.75 0 01-.75-.75zM8 6a1 1 0 100-2 1 1 0 000 2z" />
    </svg>
  );
}

/** Mini sparkline showing recent run statuses as bars. */
function Sparkline({ runs }: { runs: SyncRunSummary[] }) {
  const bars = useMemo(() => {
    const recent = runs.slice(0, 10).reverse();
    if (recent.length === 0) {
      return Array.from({ length: 10 }, (_, i) => ({
        key: `empty-${i}`,
        status: 'empty' as const,
        height: 30,
      }));
    }
    return recent.map((r) => ({
      key: r.id,
      status: r.status,
      height: r.status === 'completed' ? 100 : r.status === 'failed' ? 60 : 40,
    }));
  }, [runs]);

  return (
    <div className={styles.sparklineContainer} aria-label="Recent sync run results" role="img">
      {bars.map((bar) => {
        const barClass =
          bar.status === 'completed'
            ? styles.sparklineBarSuccess
            : bar.status === 'failed'
              ? styles.sparklineBarFailed
              : bar.status === 'running'
                ? styles.sparklineBarRunning
                : styles.sparklineBarEmpty;
        return (
          <div
            key={bar.key}
            className={`${styles.sparklineBar} ${barClass}`}
            style={{ height: `${bar.height}%` }}
          />
        );
      })}
    </div>
  );
}

/** Individual sync type card with status indicator and sparkline. */
function SyncTypeCardComponent({ card, runs }: { card: SyncTypeCard; runs: SyncRunSummary[] }) {
  return (
    <Card className={styles.syncCard}>
      <CardHeader>{card.title}</CardHeader>
      <div className={styles.cardBody}>
        <div className={styles.cardStatusRow}>
          <span className={styles.statusDot} data-status={card.health} />
          <span className={styles.statusText}>{card.health}</span>
          {card.lastStatus && (
            <Label variant={statusVariant(card.lastStatus)}>{card.lastStatus}</Label>
          )}
        </div>
        <Sparkline runs={runs} />
        <div className={styles.cardMeta}>
          <div className={styles.cardMetaRow}>
            <span>Last run</span>
            <strong>{card.lastRun ? formatRelativeShort(card.lastRun) : '—'}</strong>
          </div>
          <div className={styles.cardMetaRow}>
            <span>Items synced</span>
            <strong>{card.itemCount.toLocaleString()}</strong>
          </div>
        </div>
      </div>
    </Card>
  );
}

/** Overall sync status summary card (left half of top row). */
function OverallStatusCard({
  health,
  totalRuns,
  currentRun,
}: {
  health: HealthLevel;
  totalRuns: number;
  currentRun: SyncRun | null | undefined;
}) {
  return (
    <Card>
      <CardHeader>Overall Status</CardHeader>
      <div className={styles.scheduleSection}>
        <div className={styles.scheduleRow}>
          <span>Health</span>
          <strong>
            <Label
              variant={
                health === 'healthy'
                  ? 'success'
                  : health === 'unhealthy'
                    ? 'danger'
                    : health === 'degraded'
                      ? 'attention'
                      : 'muted'
              }
            >
              {health}
            </Label>
          </strong>
        </div>
        <div className={styles.scheduleRow}>
          <span>Total runs</span>
          <strong>{totalRuns}</strong>
        </div>
        <div className={styles.scheduleRow}>
          <span>Current status</span>
          <strong>
            {currentRun ? (
              <Label variant={statusVariant(currentRun.status)}>{currentRun.status}</Label>
            ) : (
              'Idle'
            )}
          </strong>
        </div>
        {currentRun?.started_at && (
          <div className={styles.scheduleRow}>
            <span>Running since</span>
            <strong>{formatRelativeShort(currentRun.started_at)}</strong>
          </div>
        )}
      </div>
    </Card>
  );
}

/** Schedule information card (right half of top row). */
function ScheduleCard({ schedule }: { schedule: SyncScheduleType | undefined }) {
  if (!schedule) return null;

  return (
    <Card>
      <CardHeader>Sync Schedule</CardHeader>
      <div className={styles.scheduleSection}>
        <div className={styles.scheduleRow}>
          <span>Scheduling</span>
          <strong>
            <Label variant={schedule.enabled ? 'success' : 'muted'}>
              {schedule.enabled ? 'Enabled' : 'Disabled'}
            </Label>
          </strong>
        </div>
        <div className={styles.scheduleRow}>
          <span>Interval</span>
          <strong>Every {schedule.interval_hours} hours</strong>
        </div>
        <div className={styles.scheduleRow}>
          <span>Scope</span>
          <strong>{schedule.scope}</strong>
        </div>
        <div className={styles.scheduleRow}>
          <span>Next run</span>
          <strong>{schedule.next_run_at ? formatShortDateTime(schedule.next_run_at) : '—'}</strong>
        </div>
        <div className={styles.scheduleRow}>
          <span>Last completed</span>
          <strong>
            {schedule.last_completed_at ? formatRelativeShort(schedule.last_completed_at) : '—'}
          </strong>
        </div>
      </div>
    </Card>
  );
}

/** Run detail slide-out drawer content. */
function RunDetailDrawer({
  runId,
  open,
  onClose,
}: {
  runId: string | null;
  open: boolean;
  onClose: () => void;
}) {
  const { data: runDetail, isLoading } = useQuery({
    queryKey: ['sync-run-detail', runId],
    queryFn: () => getSyncRun(runId!),
    enabled: open && runId !== null,
  });

  return (
    <Drawer open={open} onClose={onClose} title="Sync Run Details">
      {isLoading && (
        <div className={styles.loadingState}>
          <Spinner />
          <span>Loading run details…</span>
        </div>
      )}
      {!isLoading && runDetail && (
        <div className={styles.drawerContent} data-testid="run-detail-drawer-content">
          <div className={styles.drawerSection}>
            <h4 className={styles.drawerSectionTitle}>Overview</h4>
            <dl className={styles.drawerDl}>
              <dt>Status</dt>
              <dd>
                <Label variant={statusVariant(runDetail.status)}>{runDetail.status}</Label>
              </dd>
              <dt>Trigger</dt>
              <dd>{runDetail.triggered_by ?? runDetail.trigger_type}</dd>
              <dt>Scope</dt>
              <dd>{runDetail.scope}</dd>
              <dt>Started</dt>
              <dd>{runDetail.started_at ? formatShortDateTime(runDetail.started_at) : '—'}</dd>
              <dt>Completed</dt>
              <dd>{runDetail.completed_at ? formatShortDateTime(runDetail.completed_at) : '—'}</dd>
              <dt>Duration</dt>
              <dd>{formatDuration(runDetail.started_at, runDetail.completed_at)}</dd>
            </dl>
          </div>

          {runDetail.error_message && (
            <div className={styles.drawerSection}>
              <h4 className={styles.drawerSectionTitle}>Error</h4>
              <p className={styles.drawerError}>{runDetail.error_message}</p>
            </div>
          )}

          {runDetail.entity_counts && Object.keys(runDetail.entity_counts).length > 0 && (
            <div className={styles.drawerSection}>
              <h4 className={styles.drawerSectionTitle}>Entities Synced</h4>
              <dl className={styles.drawerDl}>
                {Object.entries(runDetail.entity_counts).map(([entity, count]) => (
                  <div key={entity} className={styles.drawerDlRow}>
                    <dt>{entity}</dt>
                    <dd>{(count as number).toLocaleString()}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          {runDetail.cursors && runDetail.cursors.length > 0 && (
            <div className={styles.drawerSection}>
              <h4 className={styles.drawerSectionTitle}>Cursor Progress</h4>
              <table className={styles.drawerTable}>
                <thead>
                  <tr>
                    <th>Entity</th>
                    <th>Org</th>
                    <th>Status</th>
                    <th>Items</th>
                  </tr>
                </thead>
                <tbody>
                  {runDetail.cursors.map((cursor: EntityStatus, idx: number) => (
                    <tr key={`${cursor.entity_type}-${cursor.org ?? 'all'}-${idx}`}>
                      <td>{cursor.entity_type}</td>
                      <td>{cursor.org ?? '—'}</td>
                      <td>
                        <Label
                          variant={
                            cursor.status === 'completed'
                              ? 'success'
                              : cursor.status === 'failed'
                                ? 'danger'
                                : cursor.status === 'in_progress'
                                  ? 'attention'
                                  : 'muted'
                          }
                        >
                          {cursor.status}
                        </Label>
                      </td>
                      <td>{cursor.items_synced.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {runDetail.post_processing_status && (
            <div className={styles.drawerSection}>
              <h4 className={styles.drawerSectionTitle}>Post-Processing</h4>
              <Label
                variant={
                  runDetail.post_processing_status === 'completed'
                    ? 'success'
                    : runDetail.post_processing_status === 'failed'
                      ? 'danger'
                      : 'attention'
                }
              >
                {runDetail.post_processing_status}
              </Label>
            </div>
          )}
        </div>
      )}
      {!isLoading && !runDetail && runId && (
        <div className={styles.emptyState}>Run details not found.</div>
      )}
    </Drawer>
  );
}

/** Recent runs detail table with pagination and row click to open drawer. */
function RecentRunsTable({
  runs,
  total,
  page,
  onPageChange,
  onRowClick,
}: {
  runs: SyncRunSummary[];
  total: number;
  page: number;
  onPageChange: (p: number) => void;
  onRowClick: (runId: string) => void;
}) {
  if (total === 0 && runs.length === 0) {
    return (
      <Card>
        <CardHeader>Recent Sync Runs</CardHeader>
        <div className={styles.emptyState}>No sync runs recorded yet</div>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>Recent Sync Runs</CardHeader>
      <table className={styles.detailTable} data-testid="recent-runs-table">
        <thead>
          <tr>
            <th>Triggered by</th>
            <th>Started</th>
            <th>Duration</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr
              key={run.id}
              className={styles.clickableRow}
              onClick={() => onRowClick(run.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onRowClick(run.id);
                }
              }}
            >
              <td>{run.triggered_by ?? run.trigger_type}</td>
              <td>{run.started_at ? formatShortDateTime(run.started_at) : '—'}</td>
              <td>{formatDuration(run.started_at, run.completed_at)}</td>
              <td>
                <Label variant={statusVariant(run.status)}>{run.status}</Label>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className={styles.paginationWrapper}>
        <Pagination
          page={page}
          pageSize={RUNS_PAGE_SIZE}
          total={total}
          onPageChange={onPageChange}
        />
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Main page component                                                */
/* ------------------------------------------------------------------ */

export function SyncStatusPage() {
  const { hasPermission } = usePermissions();
  const canView = hasPermission('admin_settings', 'view');

  const [runsPage, setRunsPage] = useState(1);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const handleRowClick = useCallback((runId: string) => {
    setSelectedRunId(runId);
    setDrawerOpen(true);
  }, []);

  const handleDrawerClose = useCallback(() => {
    setDrawerOpen(false);
  }, []);

  const {
    data: currentRun,
    isLoading: statusLoading,
    isError: statusError,
    refetch: refetchStatus,
  } = useQuery({
    queryKey: ['sync-status'],
    queryFn: getSyncStatus,
    enabled: canView,
    refetchInterval: 15_000,
  });

  const {
    data: runsData,
    isLoading: runsLoading,
    isError: runsError,
    refetch: refetchRuns,
  } = useQuery({
    queryKey: ['sync-runs', 'monitoring', runsPage],
    queryFn: () => listSyncRuns(runsPage, RUNS_PAGE_SIZE),
    enabled: canView,
    refetchInterval: 30_000,
  });

  const { data: schedule } = useQuery({
    queryKey: ['sync-schedule'],
    queryFn: getSyncSchedule,
    enabled: canView,
    staleTime: 60_000,
  });

  const { data: config } = useQuery({
    queryKey: ['sync-config'],
    queryFn: getSyncConfig,
    enabled: canView,
    staleTime: 60_000,
  });

  const runs = runsData?.items ?? [];
  const totalRuns = runsData?.total ?? 0;

  const syncCards: SyncTypeCard[] = useMemo(() => {
    if (runs.length === 0 && !currentRun) return [];

    const fullRuns = runs.filter(
      (r) => r.trigger_type === 'scheduled' || r.trigger_type === 'manual',
    );
    const health = deriveHealth(fullRuns);
    const lastRun = fullRuns[0] ?? null;
    const totalItems = currentRun?.entity_counts
      ? Object.values(currentRun.entity_counts).reduce((sum, v) => sum + v, 0)
      : 0;

    const cards: SyncTypeCard[] = [
      {
        title: 'Full Sync',
        description: 'Complete data synchronization across all configured organizations',
        health,
        lastRun: lastRun?.started_at ?? null,
        lastStatus: lastRun?.status ?? null,
        itemCount: totalItems,
      },
    ];

    if (config?.orgs && config.orgs.length > 0) {
      for (const org of config.orgs) {
        cards.push({
          title: `Org: ${org}`,
          description: `Sync status for the ${org} organization`,
          health,
          lastRun: lastRun?.started_at ?? null,
          lastStatus: lastRun?.status ?? null,
          itemCount: 0,
        });
      }
    }

    return cards;
  }, [runs, currentRun, config]);

  const health = overallHealth(syncCards);
  const failureDetail = extractFailureDetail(currentRun, runs);

  const isLoading = statusLoading || runsLoading;
  const isError = statusError || runsError;

  if (!canView) {
    return (
      <div className={styles.page}>
        <PageHeader
          title="Sync Status"
          description="Monitor data synchronization health"
          breadcrumbs={[{ label: 'Monitoring' }, { label: 'Sync Status' }]}
        />
        <ErrorBanner message="You do not have permission to view sync status." />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className={styles.page}>
        <PageHeader
          title="Sync Status"
          description="Monitor data synchronization health"
          breadcrumbs={[{ label: 'Monitoring' }, { label: 'Sync Status' }]}
        />
        <div className={styles.loadingState}>
          <Spinner />
          <span>Loading sync status…</span>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className={styles.page}>
        <PageHeader
          title="Sync Status"
          description="Monitor data synchronization health"
          breadcrumbs={[{ label: 'Monitoring' }, { label: 'Sync Status' }]}
        />
        <ErrorBanner
          message="Failed to load sync status"
          onRetry={() => {
            refetchStatus();
            refetchRuns();
          }}
        />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <PageHeader
        title="Sync Status"
        description="Monitor data synchronization health and recent activity"
        breadcrumbs={[{ label: 'Monitoring' }, { label: 'Sync Status' }]}
      />

      <HealthBanner health={health} totalRuns={totalRuns} failureDetail={failureDetail} />

      <div className={styles.statusRow}>
        <OverallStatusCard health={health} totalRuns={totalRuns} currentRun={currentRun} />
        <ScheduleCard schedule={schedule} />
      </div>

      {syncCards.length > 0 ? (
        <div className={styles.cardsGrid}>
          {syncCards.map((card) => (
            <SyncTypeCardComponent key={card.title} card={card} runs={runs} />
          ))}
        </div>
      ) : (
        <Card>
          <div className={styles.emptyState}>
            No sync data available yet. Configure sync in{' '}
            <a href="/settings/github">Settings → GitHub</a>.
          </div>
        </Card>
      )}

      <RecentRunsTable
        runs={runs}
        total={totalRuns}
        page={runsPage}
        onPageChange={setRunsPage}
        onRowClick={handleRowClick}
      />

      <RunDetailDrawer runId={selectedRunId} open={drawerOpen} onClose={handleDrawerClose} />
    </div>
  );
}
