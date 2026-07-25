import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { listEvents } from '../../api/events';
import { MiniBarChart } from '../charts/MiniBarChart';
import { useOrg } from '../../hooks/useOrg';
import { ErrorBanner } from '../primitives/ErrorBanner';
import { Spinner } from '../primitives/Spinner';
import styles from './Widgets.module.css';

function formatCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

export function EventVolumeWidget() {
  const navigate = useNavigate();
  const { selectedOrg } = useOrg();
  const [windowConfig] = useState(() => {
    const now = Date.now();
    const windowMs = 24 * 60 * 60 * 1000;
    const bucketCount = 8;
    return {
      now,
      windowMs,
      bucketCount,
      bucketMs: windowMs / bucketCount,
      since: new Date(now - windowMs).toISOString(),
    };
  });

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['widget', 'event-volume', selectedOrg],
    queryFn: () =>
      listEvents({
        since: windowConfig.since,
        org: selectedOrg || undefined,
        sort: 'created_at_asc',
        page_size: 500,
      }),
    staleTime: 60_000,
  });

  if (isLoading) return <Spinner />;
  if (isError || !data) {
    return <ErrorBanner message="Failed to load event volume" onRetry={() => void refetch()} />;
  }

  const buckets = Array.from({ length: windowConfig.bucketCount }, () => 0);
  for (const event of data.items) {
    const timestamp = Date.parse(event.created_at);
    if (
      Number.isNaN(timestamp) ||
      timestamp < windowConfig.now - windowConfig.windowMs ||
      timestamp > windowConfig.now
    ) {
      continue;
    }

    const index = Math.min(
      windowConfig.bucketCount - 1,
      Math.max(
        0,
        Math.floor(
          (timestamp - (windowConfig.now - windowConfig.windowMs)) / windowConfig.bucketMs,
        ),
      ),
    );
    buckets[index] += 1;
  }

  return (
    <>
      <div className={styles.metricRow}>
        <div>
          <div className={styles.metricValue}>{formatCount(data.total)}</div>
          <div className={styles.metricLabel}>events in the last 24h</div>
        </div>
        <button type="button" className={styles.actionLink} onClick={() => navigate('/events')}>
          Inspect events
        </button>
      </div>
      <MiniBarChart data={buckets} height={84} color="var(--accent)" />
      <div className={styles.listItem}>
        <span className={styles.listLabel}>Peak 3-hour window</span>
        <span className={styles.listValue}>{formatCount(Math.max(...buckets, 0))}</span>
      </div>
    </>
  );
}
