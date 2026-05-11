import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getSyncStatus, listSyncRuns, getSyncSchedule, getSyncConfig } from '../../api/sync';
import { PageHeader } from '../../components/common/PageHeader';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { usePermissions } from '../../hooks/usePermissions';
import { formatRelativeShort, formatShortDateTime } from '../../utils/dates';
import type {
  SyncRunSummary,
  SyncRunStatus,
  SyncSchedule as SyncScheduleType,
} from '../../types/sync';
import styles from './SyncStatus.module.css';

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

/** Health summary banner displayed at the top of the page. */
function HealthBanner({ health, totalRuns }: { health: HealthLevel; totalRuns: number }) {
  return (
    <div
      className={`${styles.healthBanner} ${healthBannerClass(health)}`}
      data-testid="health-banner"
      role="status"
    >
      <HealthIcon health={health} />
      <div className={styles.bannerText}>
        <span className={styles.bannerTitle}>{healthLabel(health)}</span>
        <span className={styles.bannerDetail}>{healthDetail(health, totalRuns)}</span>
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

/** Schedule information card. */
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

/** Recent runs detail table. */
function RecentRunsTable({ runs }: { runs: SyncRunSummary[] }) {
  if (runs.length === 0) {
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
            <tr key={run.id}>
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
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Main page component                                                */
/* ------------------------------------------------------------------ */

export function SyncStatusPage() {
  const { hasPermission } = usePermissions();
  const canView = hasPermission('admin_settings', 'view');

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
    queryKey: ['sync-runs', 'monitoring'],
    queryFn: () => listSyncRuns(1, 20),
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

      <HealthBanner health={health} totalRuns={totalRuns} />

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

      <div className={styles.detailPanel}>
        <ScheduleCard schedule={schedule} />
      </div>

      <RecentRunsTable runs={runs} />
    </div>
  );
}
