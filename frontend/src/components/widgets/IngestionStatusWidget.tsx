import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getTelemetrySummary } from '../../api/telemetry';
import { formatRelative } from '../../utils/dates';
import { ErrorBanner } from '../primitives/ErrorBanner';
import { Spinner } from '../primitives/Spinner';
import styles from './Widgets.module.css';

export function IngestionStatusWidget() {
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['widget', 'ingestion-status'],
    queryFn: getTelemetrySummary,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const lastEventAt = data?.last_event_at;
  const minutesSinceLast = useMemo(() => {
    if (!lastEventAt || !dataUpdatedAt) return null;
    return Math.round((dataUpdatedAt - new Date(lastEventAt).getTime()) / 60_000);
  }, [lastEventAt, dataUpdatedAt]);

  if (isLoading) return <Spinner />;
  if (isError) {
    return <ErrorBanner message="Failed to load ingestion status" onRetry={() => void refetch()} />;
  }

  const isStale = minutesSinceLast !== null && minutesSinceLast > 5;
  const isCritical = minutesSinceLast !== null && minutesSinceLast > 30;

  const toneClass = isCritical
    ? styles.statusCritical
    : isStale
      ? styles.statusWarning
      : styles.statusHealthy;

  const toneLabel = isCritical ? 'Ingestion stalled' : isStale ? 'Ingestion delayed' : 'Healthy';

  return (
    <>
      <div className={`${styles.statusPill} ${toneClass}`}>{toneLabel}</div>
      <div className={styles.inlineStats}>
        <div className={styles.inlineStat}>
          <strong>{data?.events_per_second ?? 0}</strong>
          <span>events/sec</span>
        </div>
        <div className={styles.inlineStat}>
          <strong>{data?.events_today?.toLocaleString() ?? 0}</strong>
          <span>today</span>
        </div>
        <div className={styles.inlineStat}>
          <strong>{data?.active_workers ?? 0}</strong>
          <span>workers</span>
        </div>
      </div>
      <div className={styles.list}>
        <div className={styles.listItem}>
          <span className={styles.listLabel}>Last event</span>
          <span className={styles.listValue}>
            {lastEventAt ? formatRelative(lastEventAt) : 'No events'}
          </span>
        </div>
        <div className={styles.listItem}>
          <span className={styles.listLabel}>Error rate</span>
          <span className={styles.listValue}>
            {data?.error_rate !== undefined ? `${(data.error_rate * 100).toFixed(1)}%` : '—'}
          </span>
        </div>
        <div className={styles.listItem}>
          <span className={styles.listLabel}>Queue depth</span>
          <span className={styles.listValue}>{data?.queue_depth?.toLocaleString() ?? '—'}</span>
        </div>
      </div>
      <button
        type="button"
        className={styles.actionLink}
        onClick={() => navigate('/monitoring/telemetry')}
      >
        Open telemetry
      </button>
    </>
  );
}
