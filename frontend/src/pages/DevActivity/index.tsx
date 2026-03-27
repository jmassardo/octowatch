import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listEvents } from '../../api/events';
import { listDetections } from '../../api/detections';
import { Avatar } from '../../components/primitives/Avatar';
import { Label } from '../../components/primitives/Label';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { MiniBarChart } from '../../components/charts/MiniBarChart';
import styles from './DevActivity.module.css';

interface ActorStats {
  handle: string;
  eventCount: number;
  repoSet: Set<string>;
  prCount: number;
  weeklyCounts: number[];
}

/* Static placeholder data for work distribution cards */
const PR_AUTHORSHIP_DATA = [
  { handle: 'alice', pct: 31, color: '#1f6feb' },
  { handle: 'david', pct: 24, color: '#1f6feb' },
  { handle: 'carol', pct: 20, color: '#238636' },
  { handle: 'bob', pct: 16, color: '#238636' },
  { handle: 'eremin', pct: 8, color: '#58a6ff' },
] as const;

const REVIEW_CONCENTRATION_DATA: readonly { handle: string; pct: number; color: string; textColor?: string }[] = [
  { handle: 'alice', pct: 44, color: 'var(--danger)', textColor: 'var(--danger)' },
  { handle: 'carol', pct: 28, color: 'var(--attention)', textColor: 'var(--attention)' },
  { handle: 'david', pct: 18, color: '#238636' },
  { handle: 'bob', pct: 10, color: '#238636' },
];

export function DevActivityPage() {
  const { data: eventData, isLoading: loadingEvents, isError: eventsError, refetch } = useQuery({
    queryKey: ['events', 'dev-activity'],
    queryFn: () => listEvents({ page_size: 500, sort: 'created_at_desc' }),
  });

  const { data: detectionData } = useQuery({
    queryKey: ['detections', 'dev-activity'],
    queryFn: () => listDetections({ page_size: 200, status: 'investigating' }),
  });

  // Build actor stats from events
  const { actorMap, actorDetections } = useMemo(() => {
    const map = new Map<string, ActorStats>();
    const items = eventData?.items ?? [];
    // Use most recent event timestamp as reference (events are sorted desc)
    const refTime = items.length > 0 ? new Date(items[0].created_at).getTime() : 0;
    const weekMs = 7 * 24 * 60 * 60 * 1000;

    for (const event of items) {
      if (!event.actor) continue;
      if (!map.has(event.actor)) {
        map.set(event.actor, {
          handle: event.actor,
          eventCount: 0,
          repoSet: new Set(),
          prCount: 0,
          weeklyCounts: [0, 0, 0, 0, 0, 0, 0],
        });
      }
      const stats = map.get(event.actor)!;
      stats.eventCount++;
      if (event.repo) stats.repoSet.add(event.repo);
      if (event.action.includes('pull_request')) stats.prCount++;

      // Assign to weekly bucket (0 = oldest, 6 = most recent)
      const age = refTime - new Date(event.created_at).getTime();
      const weekIndex = Math.min(6, Math.floor(age / weekMs));
      stats.weeklyCounts[6 - weekIndex]++;
    }

    // Build detections-per-actor map
    const detMap = new Map<string, number>();
    for (const d of detectionData?.items ?? []) {
      if (d.actor) {
        detMap.set(d.actor, (detMap.get(d.actor) ?? 0) + 1);
      }
    }

    return { actorMap: map, actorDetections: detMap };
  }, [eventData?.items, detectionData?.items]);

  // Sort by event count descending, take top 12
  const topActors = [...actorMap.values()]
    .sort((a, b) => b.eventCount - a.eventCount)
    .slice(0, 12);

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Developer Activity</div>
      <div className={styles.pageSub}>Per-developer contribution metrics and security posture</div>

      <div className={styles.teamFilters}>
        <Button
          size="sm"
          style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}
        >
          All teams
        </Button>
      </div>

      {eventsError && <ErrorBanner message="Failed to load developer activity" onRetry={refetch} />}
      {loadingEvents && <Spinner />}

      <div className={styles.sectionTitle} style={{ marginBottom: 4 }}>Work distribution — last 30 days</div>
      <div className={styles.workNote}>
        Uneven distribution can indicate bus factor risk, burnout, or knowledge silos. Use to start conversations, not assign blame.
      </div>

      <div className={styles.workGrid}>
        <Card>
          <CardHeader>PR authorship share</CardHeader>
          <div className={styles.barList}>
            {PR_AUTHORSHIP_DATA.map((d) => (
              <div key={d.handle} className={styles.barRow}>
                <span className={styles.barHandle}>@{d.handle}</span>
                <div className={styles.barTrack}>
                  <div style={{ width: `${d.pct}%`, height: '100%', background: d.color, borderRadius: 4 }} />
                </div>
                <span className={styles.barPct}>{d.pct}%</span>
              </div>
            ))}
            <div className={styles.barRow}>
              <span className={styles.barHandle} style={{ color: 'var(--fg-subtle)', fontWeight: 400 }}>others (7)</span>
              <div className={styles.barTrack}>
                <div style={{ width: '1%', height: '100%', background: 'var(--border)', borderRadius: 4 }} />
              </div>
              <span className={styles.barPct} style={{ color: 'var(--fg-subtle)' }}>1%</span>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader>Review concentration</CardHeader>
          <div className={styles.barList}>
            {REVIEW_CONCENTRATION_DATA.map((d) => (
              <div key={d.handle} className={styles.barRow}>
                <span className={styles.barHandle}>@{d.handle}</span>
                <div className={styles.barTrack}>
                  <div style={{ width: `${d.pct}%`, height: '100%', background: d.color, borderRadius: 4 }} />
                </div>
                <span className={styles.barPct} style={d.textColor ? { color: d.textColor } : undefined}>{d.pct}%</span>
              </div>
            ))}
          </div>
          <div className={styles.busWarning}>
            ⚠ <strong>@alice</strong> performs 44% of all reviews — consider a review rotation to reduce bus factor risk
          </div>
        </Card>
      </div>

      <div className={styles.sectionTitle} style={{ marginBottom: 16 }}>Developer cards</div>
      {topActors.length === 0 && !loadingEvents && (
        <div style={{ color: 'var(--fg-muted)', padding: '16px 0' }}>No developer activity data found.</div>
      )}
      <div className={styles.devGrid}>
        {topActors.map((dev) => {
          const detections = actorDetections.get(dev.handle) ?? 0;
          const flagged = detections > 0;
          return (
            <div
              key={dev.handle}
              className={[styles.devCard, flagged && styles.flagged].filter(Boolean).join(' ')}
            >
              <div className={styles.devTop}>
                <Avatar username={dev.handle} size={36} />
                <div>
                  <div className={styles.devName}>
                    {dev.handle}
                    {flagged && (
                      <Label variant="danger" className={styles.flagLabel}>
                        flagged
                      </Label>
                    )}
                  </div>
                  <div className={styles.devHandle}>
                    <span className={styles.mention}>@{dev.handle}</span>
                  </div>
                </div>
              </div>
              <MiniBarChart data={dev.weeklyCounts} color={flagged ? 'var(--danger)' : 'var(--success)'} />
              <div className={styles.devStats}>
                <span><strong>{dev.repoSet.size}</strong> repos</span>
                <span><strong>{dev.prCount}</strong> PRs</span>
                <span style={{ color: flagged ? 'var(--danger)' : undefined }}>
                  <strong>{detections}</strong> {flagged ? 'detections' : 'flags'}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}



