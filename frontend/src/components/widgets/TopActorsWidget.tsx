import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { listEvents } from '../../api/events';
import { useOrg } from '../../hooks/useOrg';
import { ErrorBanner } from '../primitives/ErrorBanner';
import { Spinner } from '../primitives/Spinner';
import styles from './Widgets.module.css';

export function TopActorsWidget() {
  const navigate = useNavigate();
  const { selectedOrg } = useOrg();
  const [since] = useState(() => new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString());

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['widget', 'top-actors', selectedOrg],
    queryFn: () =>
      listEvents({ since, org: selectedOrg || undefined, sort: 'created_at_desc', page_size: 200 }),
    staleTime: 60_000,
  });

  if (isLoading) return <Spinner />;
  if (isError || !data) {
    return <ErrorBanner message="Failed to load top actors" onRetry={() => void refetch()} />;
  }

  const counts = new Map<string, number>();
  for (const event of data.items) {
    if (!event.actor || event.actor_is_bot) continue;
    counts.set(event.actor, (counts.get(event.actor) ?? 0) + 1);
  }

  const topActors = Array.from(counts.entries())
    .sort((left, right) => right[1] - left[1])
    .slice(0, 5);
  const max = Math.max(...topActors.map(([, count]) => count), 1);

  if (topActors.length === 0) {
    return <div className={styles.muted}>No human actor activity recorded in the last 7 days.</div>;
  }

  return (
    <div className={styles.list}>
      {topActors.map(([actor, count]) => (
        <button
          key={actor}
          type="button"
          className={styles.barRow}
          style={{ background: 'transparent', border: 'none', padding: 0, cursor: 'pointer' }}
          onClick={() => navigate(`/events?actor=${encodeURIComponent(actor)}`)}
        >
          <span className={styles.barLabel}>{actor}</span>
          <div className={styles.barTrack}>
            <div
              className={styles.barFill}
              style={{ width: `${Math.max(8, (count / max) * 100)}%`, background: 'var(--done)' }}
            />
          </div>
          <span className={styles.barValue}>{count}</span>
        </button>
      ))}
    </div>
  );
}
