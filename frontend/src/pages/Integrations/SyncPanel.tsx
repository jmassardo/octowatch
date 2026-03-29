import { useState, useMemo } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import {
  getSyncStatus,
  triggerSync,
  cancelSyncRun,
  getSyncConfig,
  getSyncSchedule,
  updateSyncSchedule,
} from '../../api/sync';
import { Button } from '../../components/primitives/Button';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import type { SyncRun, SyncRunStatus, EntityStatus } from '../../types/sync';
import styles from './Integrations.module.css';

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const TERMINAL_STATUSES = new Set<SyncRunStatus>(['completed', 'failed', 'cancelled']);

function isTerminal(status: SyncRunStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

function statusVariant(status: string): 'success' | 'danger' | 'attention' | 'muted' {
  switch (status) {
    case 'completed':
      return 'success';
    case 'failed':
      return 'danger';
    case 'running':
    case 'in_progress':
      return 'attention';
    default:
      return 'muted';
  }
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
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

function formatDateTime(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function totalEntityCount(run: SyncRun): number {
  if (run.entity_counts) {
    return Object.values(run.entity_counts).reduce((sum, n) => sum + n, 0);
  }
  return run.cursors.reduce((sum, c) => sum + c.items_synced, 0);
}

/* ------------------------------------------------------------------ */
/*  Entity status table                                                */
/* ------------------------------------------------------------------ */

function EntityTable({ cursors }: { cursors: EntityStatus[] }) {
  if (cursors.length === 0) return null;

  return (
    <table className={styles.entityTable} data-testid="entity-table">
      <thead>
        <tr>
          <th>Entity</th>
          <th>Org</th>
          <th>Status</th>
          <th>Records</th>
        </tr>
      </thead>
      <tbody>
        {cursors.map((c) => (
          <tr key={`${c.entity_type}-${c.org ?? 'global'}`}>
            <td>{c.entity_type}</td>
            <td>{c.org ?? '—'}</td>
            <td>
              <Label variant={statusVariant(c.status)}>{c.status.replace('_', ' ')}</Label>
            </td>
            <td>{c.items_synced.toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ------------------------------------------------------------------ */
/*  Progress bar                                                       */
/* ------------------------------------------------------------------ */

function ProgressBar({ cursors }: { cursors: EntityStatus[] }) {
  const total = cursors.length;
  if (total === 0) return null;

  const completed = cursors.filter(
    (c) => c.status === 'completed' || c.status === 'failed',
  ).length;
  const pct = Math.round((completed / total) * 100);

  return (
    <div className={styles.progressContainer} data-testid="sync-progress">
      <div className={styles.progressBar}>
        <div
          className={styles.progressFill}
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
      <span className={styles.progressLabel}>
        {completed}/{total} entities · {pct}%
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Interval options                                                   */
/* ------------------------------------------------------------------ */

const INTERVAL_OPTIONS = [
  { value: 6, label: 'Every 6 hours' },
  { value: 12, label: 'Every 12 hours' },
  { value: 24, label: 'Daily (24h)' },
  { value: 48, label: 'Every 2 days' },
  { value: 72, label: 'Every 3 days' },
  { value: 168, label: 'Weekly' },
] as const;

const SCOPE_OPTIONS = [
  { value: 'full', label: 'Full' },
  { value: 'orgs', label: 'Organizations' },
  { value: 'enterprise_members', label: 'Enterprise Members' },
  { value: 'org_members', label: 'Org Members' },
  { value: 'repositories', label: 'Repositories' },
  { value: 'teams', label: 'Teams' },
  { value: 'team_members', label: 'Team Members' },
  { value: 'branch_protections', label: 'Branch Protections' },
  { value: 'installations', label: 'Installations' },
] as const;

/* ------------------------------------------------------------------ */
/*  Schedule section                                                   */
/* ------------------------------------------------------------------ */

function ScheduleSection() {
  const queryClient = useQueryClient();

  const {
    data: schedule,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['sync-schedule'],
    queryFn: getSyncSchedule,
  });

  const [localEnabled, setLocalEnabled] = useState<boolean | null>(null);
  const [localInterval, setLocalInterval] = useState<number | null>(null);
  const [localScope, setLocalScope] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);

  // Resolve displayed values: local edits take precedence over server data
  const enabled = localEnabled ?? schedule?.enabled ?? false;
  const intervalHours = localInterval ?? schedule?.interval_hours ?? 24;
  const scope = localScope ?? schedule?.scope ?? 'full';

  const hasChanges =
    schedule != null &&
    (localEnabled !== null || localInterval !== null || localScope !== null);

  const saveMutation = useMutation({
    mutationFn: () => {
      const updates: { enabled?: boolean; interval_hours?: number; scope?: string } = {};
      if (localEnabled !== null) updates.enabled = localEnabled;
      if (localInterval !== null) updates.interval_hours = localInterval;
      if (localScope !== null) updates.scope = localScope;
      return updateSyncSchedule(updates);
    },
    onSuccess: () => {
      setLocalEnabled(null);
      setLocalInterval(null);
      setLocalScope(null);
      setSaveSuccess('Schedule saved successfully.');
      queryClient.invalidateQueries({ queryKey: ['sync-schedule'] });
      queryClient.invalidateQueries({ queryKey: ['sync-status'] });
      setTimeout(() => setSaveSuccess(null), 3000);
    },
  });

  if (isLoading) {
    return (
      <div className={styles.scheduleSection} data-testid="schedule-section">
        <div className={styles.syncLoading}>
          <Spinner />
          <span>Loading schedule…</span>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className={styles.scheduleSection} data-testid="schedule-section">
        <ErrorBanner message="Failed to load schedule" onRetry={() => refetch()} />
      </div>
    );
  }

  return (
    <div className={styles.scheduleSection} data-testid="schedule-section">
      <h3 className={styles.scheduleTitle}>Schedule</h3>

      {/* Enable toggle */}
      <div className={styles.configField}>
        <div className={styles.configToggleRow}>
          <label className={styles.configLabel} htmlFor="schedule-enabled-toggle">
            Enable automatic sync schedule
          </label>
          <input
            id="schedule-enabled-toggle"
            type="checkbox"
            checked={enabled}
            onChange={(e) => setLocalEnabled(e.target.checked)}
          />
        </div>
      </div>

      {/* Interval picker */}
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="schedule-interval-select">
          Schedule interval
        </label>
        <select
          id="schedule-interval-select"
          className={styles.configInput}
          value={intervalHours}
          onChange={(e) => setLocalInterval(Number(e.target.value))}
        >
          {INTERVAL_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Scope selector */}
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="schedule-scope-select">
          Sync scope
        </label>
        <select
          id="schedule-scope-select"
          className={styles.configInput}
          value={scope}
          onChange={(e) => setLocalScope(e.target.value)}
        >
          {SCOPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Schedule info */}
      <div className={styles.scheduleInfo}>
        <div className={styles.scheduleInfoRow}>
          <span className={styles.scheduleInfoLabel}>Next scheduled sync</span>
          <span className={styles.scheduleInfoValue}>
            {schedule?.next_run_at
              ? formatScheduleDate(schedule.next_run_at)
              : 'Not scheduled'}
          </span>
        </div>
        <div className={styles.scheduleInfoRow}>
          <span className={styles.scheduleInfoLabel}>Last completed sync</span>
          <span className={styles.scheduleInfoValue}>
            {schedule?.last_completed_at
              ? formatScheduleDate(schedule.last_completed_at)
              : 'Never'}
          </span>
        </div>
      </div>

      {/* Success / error messages */}
      {saveSuccess && (
        <div className={styles.configSuccess} role="status" aria-live="polite">
          {saveSuccess}
        </div>
      )}
      {saveMutation.isError && (
        <div className={styles.configError}>
          Failed to save schedule. Please try again.
        </div>
      )}

      {/* Save button */}
      <div className={styles.configActions}>
        <Button
          size="sm"
          variant="primary"
          disabled={!hasChanges || saveMutation.isPending}
          onClick={() => saveMutation.mutate()}
        >
          {saveMutation.isPending ? 'Saving…' : 'Save Schedule'}
        </Button>
      </div>
    </div>
  );
}

function formatScheduleDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/* ------------------------------------------------------------------ */
/*  SyncPanel component                                                */
/* ------------------------------------------------------------------ */

export function SyncPanel() {
  const queryClient = useQueryClient();
  const [triggerError, setTriggerError] = useState<string | null>(null);

  const {
    data: syncRun,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['sync-status'],
    queryFn: getSyncStatus,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status && isTerminal(status)) return false;
      return 5000;
    },
  });

  const { data: config } = useQuery({
    queryKey: ['sync-config'],
    queryFn: getSyncConfig,
  });

  const triggerMutation = useMutation({
    mutationFn: () => triggerSync('full'),
    onSuccess: () => {
      setTriggerError(null);
      queryClient.invalidateQueries({ queryKey: ['sync-status'] });
      queryClient.invalidateQueries({ queryKey: ['sync-runs'] });
    },
    onError: (error: Error) => {
      setTriggerError(error.message);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (runId: string) => cancelSyncRun(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sync-status'] });
      queryClient.invalidateQueries({ queryKey: ['sync-runs'] });
    },
  });

  const isActive = syncRun
    ? !isTerminal(syncRun.status)
    : false;

  const nextSync = useMemo(() => {
    if (!config?.sync_enabled || !config.interval_days) return null;
    if (!syncRun?.completed_at) return null;
    const nextDate = new Date(syncRun.completed_at);
    nextDate.setDate(nextDate.getDate() + config.interval_days);
    return nextDate.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }, [config, syncRun]);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>Enterprise Sync</CardHeader>
        <div className={styles.syncLoading}>
          <Spinner />
          <span>Loading sync status…</span>
        </div>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card>
        <CardHeader>Enterprise Sync</CardHeader>
        <ErrorBanner message="Failed to load sync status" onRetry={() => refetch()} />
      </Card>
    );
  }

  return (
    <Card data-testid="sync-panel">
      <CardHeader
        actions={
          <div className={styles.syncActions}>
            {isActive && syncRun && (
              <Button
                size="sm"
                variant="danger"
                disabled={cancelMutation.isPending}
                onClick={() => cancelMutation.mutate(syncRun.id)}
              >
                {cancelMutation.isPending ? 'Cancelling…' : 'Cancel'}
              </Button>
            )}
            <Button
              size="sm"
              variant="primary"
              disabled={isActive || triggerMutation.isPending}
              onClick={() => triggerMutation.mutate()}
            >
              {triggerMutation.isPending ? 'Starting…' : 'Run Sync Now'}
            </Button>
          </div>
        }
      >
        Enterprise Sync
      </CardHeader>

      {/* Status header */}
      <div className={styles.syncStatusRow}>
        <div className={styles.syncStatusItem}>
          <span className={styles.syncStatusLabel}>Last sync</span>
          <span className={styles.syncStatusValue}>
            {syncRun ? formatRelativeTime(syncRun.completed_at ?? syncRun.started_at) : '—'}
          </span>
        </div>
        <div className={styles.syncStatusItem}>
          <span className={styles.syncStatusLabel}>Status</span>
          <span className={styles.syncStatusValue}>
            {syncRun ? (
              <Label variant={statusVariant(syncRun.status)}>{syncRun.status}</Label>
            ) : (
              <Label variant="muted">unknown</Label>
            )}
          </span>
        </div>
        {nextSync && (
          <div className={styles.syncStatusItem}>
            <span className={styles.syncStatusLabel}>Next scheduled</span>
            <span className={styles.syncStatusValue}>{nextSync}</span>
          </div>
        )}
      </div>

      {triggerError && (
        <ErrorBanner message={triggerError} onRetry={() => setTriggerError(null)} />
      )}

      {/* Active run progress */}
      {syncRun && isActive && (
        <div className={styles.syncActiveRun} data-testid="sync-active-run">
          <div className={styles.syncRunMeta}>
            <span>
              <Label variant="attention">
                {syncRun.status === 'pending' ? 'Queued' : 'Syncing'}
              </Label>
            </span>
            <span className={styles.syncRunTimer}>
              Running for {formatDuration(syncRun.started_at, null)}
            </span>
          </div>
          <ProgressBar cursors={syncRun.cursors} />
          <EntityTable cursors={syncRun.cursors} />
        </div>
      )}

      {/* Completion summary */}
      {syncRun && isTerminal(syncRun.status) && (
        <div className={styles.syncSummary} data-testid="sync-summary">
          <div className={styles.syncSummaryRow}>
            <span className={styles.syncSummaryLabel}>Duration</span>
            <span>{formatDuration(syncRun.started_at, syncRun.completed_at)}</span>
          </div>
          <div className={styles.syncSummaryRow}>
            <span className={styles.syncSummaryLabel}>Records synced</span>
            <span>{totalEntityCount(syncRun).toLocaleString()}</span>
          </div>
          <div className={styles.syncSummaryRow}>
            <span className={styles.syncSummaryLabel}>Completed</span>
            <span>{formatDateTime(syncRun.completed_at)}</span>
          </div>
          {syncRun.error_message && (
            <div className={styles.syncError}>
              <span className={styles.syncSummaryLabel}>Error</span>
              <span>{syncRun.error_message}</span>
            </div>
          )}
        </div>
      )}

      {/* Schedule section */}
      <ScheduleSection />
    </Card>
  );
}
