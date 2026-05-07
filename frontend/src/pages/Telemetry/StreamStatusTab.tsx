import { useQuery } from '@tanstack/react-query';
import { getStreamStatus } from '../../api/telemetry';
import type { StreamStatus } from '../../api/telemetry';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Telemetry.module.css';

function statusColor(minutesSinceLast: number): string {
  if (minutesSinceLast <= 1) return 'statusGreen';
  if (minutesSinceLast <= 5) return 'statusYellow';
  return 'statusRed';
}

function statusLabel(minutesSinceLast: number): string {
  if (minutesSinceLast <= 1) return 'Active';
  if (minutesSinceLast <= 5) return 'Stale';
  return 'Error';
}

function formatLatency(seconds: number): string {
  if (seconds < 1) return '<1s';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString();
}

function StreamCard({ stream }: { stream: StreamStatus }) {
  const colorClass = statusColor(stream.minutes_since_last);
  const label = statusLabel(stream.minutes_since_last);

  return (
    <div className={styles.streamCard}>
      <div className={styles.streamCardHeader}>
        <div>
          <span className={`${styles.statusDot} ${styles[colorClass]}`} />
          <span className={styles.streamOrg}>{stream.org}</span>
        </div>
        <span className={styles.streamType}>{stream.ingestion_source}</span>
      </div>
      <div className={styles.streamStats}>
        <div className={styles.streamStat}>
          Status: <span className={styles.streamStatValue}>{label}</span>
        </div>
        <div className={styles.streamStat}>
          Rate: <span className={styles.streamStatValue}>{stream.events_per_minute}/min</span>
        </div>
        <div className={styles.streamStat}>
          Last event:{' '}
          <span className={styles.streamStatValue}>{formatTime(stream.last_event_at)}</span>
        </div>
        <div className={styles.streamStat}>
          Latency:{' '}
          <span className={styles.streamStatValue}>
            {formatLatency(stream.avg_latency_seconds)}
          </span>
        </div>
      </div>
    </div>
  );
}

export function StreamStatusTab() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['telemetry', 'stream-status'],
    queryFn: () => getStreamStatus(),
    refetchInterval: 30_000,
  });

  if (isLoading) return <Spinner />;
  if (error)
    return <ErrorBanner message="Failed to load stream status" onRetry={() => refetch()} />;

  const streams = data?.streams ?? [];

  if (streams.length === 0) {
    return <div className={styles.emptyState}>No active ingestion streams detected.</div>;
  }

  return (
    <div className={styles.statusGrid}>
      {streams.map((s) => (
        <StreamCard key={`${s.org}-${s.ingestion_source}`} stream={s} />
      ))}
    </div>
  );
}
