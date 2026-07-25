import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { getSyncConfig, getSyncSchedule, getSyncStatus } from '../../api/sync';
import { formatRelative } from '../../utils/dates';
import { ErrorBanner } from '../primitives/ErrorBanner';
import { Spinner } from '../primitives/Spinner';
import styles from './Widgets.module.css';

export function SyncHealthWidget() {
  const navigate = useNavigate();
  const statusQuery = useQuery({
    queryKey: ['widget', 'sync-status'],
    queryFn: getSyncStatus,
    staleTime: 60_000,
  });
  const scheduleQuery = useQuery({
    queryKey: ['widget', 'sync-schedule'],
    queryFn: getSyncSchedule,
    staleTime: 60_000,
  });
  const configQuery = useQuery({
    queryKey: ['widget', 'sync-config'],
    queryFn: getSyncConfig,
    staleTime: 60_000,
  });

  if (statusQuery.isLoading || scheduleQuery.isLoading || configQuery.isLoading) {
    return <Spinner />;
  }

  if (statusQuery.isError || scheduleQuery.isError || configQuery.isError) {
    return (
      <ErrorBanner
        message="Failed to load sync health"
        onRetry={() => {
          void statusQuery.refetch();
          void scheduleQuery.refetch();
          void configQuery.refetch();
        }}
      />
    );
  }

  const status = statusQuery.data;
  const schedule = scheduleQuery.data;
  const config = configQuery.data;

  const toneClass =
    status?.status === 'failed'
      ? styles.statusCritical
      : status?.status === 'running' || schedule?.enabled === false
        ? styles.statusWarning
        : styles.statusHealthy;

  const toneLabel =
    status?.status === 'failed'
      ? 'Attention needed'
      : status?.status === 'running'
        ? 'Sync running'
        : schedule?.enabled === false
          ? 'Schedule paused'
          : 'Healthy';

  const entitiesSynced = Object.values(status?.entity_counts ?? {}).reduce(
    (total, count) => total + (typeof count === 'number' ? count : 0),
    0,
  );

  return (
    <>
      <div className={`${styles.statusPill} ${toneClass}`}>{toneLabel}</div>
      <div className={styles.inlineStats}>
        <div className={styles.inlineStat}>
          <strong>{config?.orgs.length ?? 0}</strong>
          <span>orgs monitored</span>
        </div>
        <div className={styles.inlineStat}>
          <strong>{entitiesSynced}</strong>
          <span>entities in latest run</span>
        </div>
        <div className={styles.inlineStat}>
          <strong>{schedule?.interval_hours ?? 0}h</strong>
          <span>refresh cadence</span>
        </div>
      </div>
      <div className={styles.list}>
        <div className={styles.listItem}>
          <span className={styles.listLabel}>Last completed</span>
          <span className={styles.listValue}>
            {status?.completed_at ? formatRelative(status.completed_at) : 'Pending'}
          </span>
        </div>
        <div className={styles.listItem}>
          <span className={styles.listLabel}>Next scheduled run</span>
          <span className={styles.listValue}>
            {schedule?.next_run_at ? formatRelative(schedule.next_run_at) : 'Not scheduled'}
          </span>
        </div>
      </div>
      <button
        type="button"
        className={styles.actionLink}
        onClick={() => navigate('/monitoring/sync-status')}
      >
        Open sync status
      </button>
    </>
  );
}
