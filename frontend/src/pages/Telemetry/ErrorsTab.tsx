import { useQuery } from '@tanstack/react-query';
import { getIngestionErrors } from '../../api/telemetry';
import type { IngestionError, IngestionGap } from '../../api/telemetry';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Telemetry.module.css';

function timeSince(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function ErrorItem({ err }: { err: IngestionError }) {
  const severityClass =
    err.severity === 'critical' ? styles.severityCritical : styles.severityError;

  return (
    <div className={styles.errorCard}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span className={`${styles.errorSeverity} ${severityClass}`}>{err.severity}</span>
        <span style={{ fontSize: 13, fontWeight: 500 }}>{err.signal_type}</span>
        <span style={{ fontSize: 12, color: 'var(--fg-muted)', marginLeft: 'auto' }}>
          {timeSince(err.occurred_at)}
        </span>
      </div>
      {err.org && <div style={{ fontSize: 12, color: 'var(--fg-muted)' }}>Org: {err.org}</div>}
      {Object.keys(err.detail).length > 0 && (
        <div style={{ fontSize: 12, color: 'var(--fg-muted)', marginTop: 4 }}>
          {JSON.stringify(err.detail)}
        </div>
      )}
    </div>
  );
}

function GapItem({ gap }: { gap: IngestionGap }) {
  return (
    <div className={styles.gapCard}>
      <div className={styles.gapOrg}>{gap.org}</div>
      <div className={styles.gapDetail}>
        No events for {gap.minutes_since_last} minutes · Last event:{' '}
        {new Date(gap.last_event_at).toLocaleString()}
      </div>
    </div>
  );
}

export function ErrorsTab() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['telemetry', 'errors'],
    queryFn: () => getIngestionErrors(),
    refetchInterval: 30_000,
  });

  if (isLoading) return <Spinner />;
  if (error)
    return <ErrorBanner message="Failed to load ingestion errors" onRetry={() => refetch()} />;

  const errors = data?.errors ?? [];
  const gaps = data?.gaps ?? [];

  const hasNoData = errors.length === 0 && gaps.length === 0;

  return (
    <div>
      {gaps.length > 0 && (
        <>
          <div className={styles.sectionTitle}>Ingestion Gaps</div>
          {gaps.map((g) => (
            <GapItem key={g.org} gap={g} />
          ))}
        </>
      )}

      <div className={styles.sectionTitle} style={gaps.length > 0 ? { marginTop: 24 } : undefined}>
        Ingestion Errors
      </div>
      {errors.length === 0 ? (
        <div className={styles.emptyState}>
          {hasNoData
            ? 'No ingestion errors or gaps detected. All systems healthy.'
            : 'No ingestion errors found.'}
        </div>
      ) : (
        errors.map((e) => <ErrorItem key={`${e.id}-${e.occurred_at}`} err={e} />)
      )}
    </div>
  );
}
