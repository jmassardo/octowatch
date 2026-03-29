import { useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { listEvents } from '../../api/events';
import { listDetections } from '../../api/detections';
import { getTeams } from '../../api/healthSignals';
import { Avatar } from '../../components/primitives/Avatar';
import { Label } from '../../components/primitives/Label';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Modal } from '../../components/primitives/Modal';
import { Drawer } from '../../components/primitives/Drawer';
import { MiniBarChart } from '../../components/charts/MiniBarChart';
import styles from './DevActivity.module.css';

interface ActorStats {
  handle: string;
  eventCount: number;
  repoSet: Set<string>;
  prCount: number;
  reviewCount: number;
  weeklyCounts: number[];
}

export function DevActivityPage() {
  const navigate = useNavigate();
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);
  const [othersModalOpen, setOthersModalOpen] = useState(false);
  const [concentrationModalOpen, setConcentrationModalOpen] = useState(false);
  const [selectedDev, setSelectedDev] = useState<ActorStats | null>(null);

  const handleCardClick = useCallback((dev: ActorStats) => {
    setSelectedDev(dev);
  }, []);

  const handleDrawerClose = useCallback(() => {
    setSelectedDev(null);
  }, []);

  const { data: eventData, isLoading: loadingEvents, isError: eventsError, refetch } = useQuery({
    queryKey: ['events', 'dev-activity'],
    queryFn: () => listEvents({ page_size: 500, sort: 'created_at_desc' }),
  });

  const { data: detectionData } = useQuery({
    queryKey: ['detections', 'dev-activity'],
    queryFn: () => listDetections({ page_size: 200, status: 'investigating' }),
  });

  const { data: teamsData } = useQuery({
    queryKey: ['teams'],
    queryFn: getTeams,
  });

  const teamNames = useMemo(() => (teamsData?.teams ?? []).map((t) => t.team_name), [teamsData]);
  const teamMembers = useMemo(() => {
    const map: Record<string, readonly string[]> = {};
    for (const t of teamsData?.teams ?? []) {
      map[t.team_name] = t.members;
    }
    return map;
  }, [teamsData]);

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
          reviewCount: 0,
          weeklyCounts: [0, 0, 0, 0, 0, 0, 0],
        });
      }
      const stats = map.get(event.actor)!;
      stats.eventCount++;
      if (event.repo) stats.repoSet.add(event.repo);
      if (event.action.includes('pull_request')) stats.prCount++;
      if (event.action.includes('pull_request_review')) stats.reviewCount++;

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

  // Compute work distribution from real event data
  const { prAuthorshipData, activityConcentrationData, topActorWarning, othersInfo, othersActors, isReviewData } =
    useMemo(() => {
      const actors = [...actorMap.values()];
      const totalEvents = actors.reduce((s, a) => s + a.eventCount, 0);

      if (totalEvents === 0) {
        return {
          prAuthorshipData: [] as { handle: string; pct: number; color: string }[],
          activityConcentrationData: [] as {
            handle: string;
            pct: number;
            color: string;
            textColor?: string;
          }[],
          topActorWarning: null as { actor: string; pct: number } | null,
          othersInfo: null as { count: number; pct: number } | null,
          othersActors: [] as { handle: string; eventCount: number }[],
          isReviewData: false,
        };
      }

      // PR authorship share — top 5 + others
      const sorted = [...actors].sort((a, b) => b.eventCount - a.eventCount);
      const top5 = sorted.slice(0, 5);
      const othersEventCount = sorted.slice(5).reduce((s, a) => s + a.eventCount, 0);
      const othersActorCount = Math.max(0, sorted.length - 5);
      const othersPct =
        totalEvents > 0 ? Math.round((othersEventCount / totalEvents) * 100) : 0;

      const colors = ['#1f6feb', '#1f6feb', '#238636', '#238636', '#58a6ff'];
      const prAuthorship = top5.map((actor, i) => ({
        handle: actor.handle,
        pct: Math.round((actor.eventCount / totalEvents) * 100),
        color: colors[i] ?? '#58a6ff',
      }));

      // Review / activity concentration
      const totalReviewEvents = actors.reduce((s, a) => s + a.reviewCount, 0);
      const hasReviewData = totalReviewEvents > 0;

      const concentrationSorted = hasReviewData
        ? [...actors]
            .sort((a, b) => b.reviewCount - a.reviewCount)
            .filter((a) => a.reviewCount > 0)
        : sorted;
      const concentrationTotal = hasReviewData ? totalReviewEvents : totalEvents;
      const concentrationTop = concentrationSorted.slice(0, 5);

      const concentration = concentrationTop.map((actor) => {
        const count = hasReviewData ? actor.reviewCount : actor.eventCount;
        const pct = Math.round((count / concentrationTotal) * 100);
        const color =
          pct >= 40 ? 'var(--danger)' : pct >= 25 ? 'var(--attention)' : '#238636';
        const textColor =
          pct >= 40 ? 'var(--danger)' : pct >= 25 ? 'var(--attention)' : undefined;
        return { handle: actor.handle, pct, color, textColor };
      });

      const topActor = concentration[0];
      const warning =
        topActor && topActor.pct > 40
          ? { actor: topActor.handle, pct: topActor.pct }
          : null;

      const othersActorsList = sorted.slice(5).map((a) => ({
        handle: a.handle,
        eventCount: a.eventCount,
      }));

      return {
        prAuthorshipData: prAuthorship,
        activityConcentrationData: concentration,
        topActorWarning: warning,
        othersInfo:
          othersActorCount > 0 ? { count: othersActorCount, pct: othersPct } : null,
        othersActors: othersActorsList,
        isReviewData: hasReviewData,
      };
    }, [actorMap]);

  // Sort by event count descending, take top 12
  const topActors = [...actorMap.values()]
    .filter((a) => {
      if (!selectedTeam) return true;
      const members = teamMembers[selectedTeam];
      return members ? members.includes(a.handle) : true;
    })
    .sort((a, b) => b.eventCount - a.eventCount)
    .slice(0, 12);

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Developer Activity</div>
      <div className={styles.pageSub}>Per-developer contribution metrics and security posture</div>

      <div className={styles.teamFilters}>
        <Button
          size="sm"
          style={!selectedTeam ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : undefined}
          onClick={() => setSelectedTeam(null)}
        >
          All teams
        </Button>
        {teamNames.length > 0 ? (
          teamNames.map((team) => (
            <Button
              key={team}
              size="sm"
              style={selectedTeam === team ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : undefined}
              onClick={() => setSelectedTeam(team)}
            >
              {team}
            </Button>
          ))
        ) : (
          <span className={styles.teamNote} title="Team data requires Enterprise Sync or team audit events">
            No team data available
          </span>
        )}
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
            {prAuthorshipData.map((d) => (
              <div
                key={d.handle}
                className={`${styles.barRow} ${styles.clickableBar}`}
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/events?actor=${d.handle}`)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/events?actor=${d.handle}`); } }}
              >
                <span className={styles.barHandle}>@{d.handle}</span>
                <div className={styles.barTrack}>
                  <div style={{ width: `${d.pct}%`, height: '100%', background: d.color, borderRadius: 4 }} />
                </div>
                <span className={styles.barPct}>{d.pct}%</span>
              </div>
            ))}
            {othersInfo && (
              <div
                className={`${styles.barRow} ${styles.clickableBar}`}
                role="button"
                tabIndex={0}
                onClick={() => setOthersModalOpen(true)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOthersModalOpen(true); } }}
              >
                <span className={styles.barHandle} style={{ color: 'var(--fg-subtle)', fontWeight: 400 }}>others ({othersInfo.count})</span>
                <div className={styles.barTrack}>
                  <div style={{ width: `${Math.max(1, othersInfo.pct)}%`, height: '100%', background: 'var(--border)', borderRadius: 4 }} />
                </div>
                <span className={styles.barPct} style={{ color: 'var(--fg-subtle)' }}>{othersInfo.pct}%</span>
              </div>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader>{isReviewData ? 'Review concentration' : 'Event activity share'}</CardHeader>
          <div className={styles.barList}>
            {activityConcentrationData.map((d) => (
              <div
                key={d.handle}
                className={`${styles.barRow} ${styles.clickableBar}`}
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/events?actor=${d.handle}`)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/events?actor=${d.handle}`); } }}
              >
                <span className={styles.barHandle}>@{d.handle}</span>
                <div className={styles.barTrack}>
                  <div style={{ width: `${d.pct}%`, height: '100%', background: d.color, borderRadius: 4 }} />
                </div>
                <span className={styles.barPct} style={d.textColor ? { color: d.textColor } : undefined}>{d.pct}%</span>
              </div>
            ))}
          </div>
          {topActorWarning ? (
            <div className={styles.busWarning}>
              ⚠ <strong className={styles.clickableText} role="button" tabIndex={0} onClick={() => navigate(`/events?actor=${topActorWarning.actor}`)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/events?actor=${topActorWarning.actor}`); } }}>@{topActorWarning.actor}</strong> accounts for <span className={styles.clickableText} role="button" tabIndex={0} onClick={() => setConcentrationModalOpen(true)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setConcentrationModalOpen(true); } }}>{topActorWarning.pct}%</span> of activity — consider distributing work to reduce bus factor risk
            </div>
          ) : (
            <div className={styles.busWarning} style={{ color: 'var(--success)' }}>
              ✅ Activity is well distributed — no single contributor exceeds 40%
            </div>
          )}
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
              role="button"
              tabIndex={0}
              onClick={() => handleCardClick(dev)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleCardClick(dev); } }}
              aria-label={`View details for ${dev.handle}`}
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
                <span className={styles.clickableStat} role="button" tabIndex={0} onClick={(e) => { e.stopPropagation(); navigate(`/events?actor=${dev.handle}`); }} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); navigate(`/events?actor=${dev.handle}`); } }}><strong>{dev.repoSet.size}</strong> repos</span>
                <span className={styles.clickableStat} role="button" tabIndex={0} onClick={(e) => { e.stopPropagation(); navigate(`/events?actor=${dev.handle}`); }} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); navigate(`/events?actor=${dev.handle}`); } }}><strong>{dev.prCount}</strong> PRs</span>
                <span className={styles.clickableStat} role="button" tabIndex={0} style={{ color: flagged ? 'var(--danger)' : undefined }} onClick={(e) => { e.stopPropagation(); navigate(`/threats?actor=${dev.handle}`); }} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); navigate(`/threats?actor=${dev.handle}`); } }}>
                  <strong>{detections}</strong> {flagged ? 'detections' : 'flags'}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <Modal open={othersModalOpen} onClose={() => setOthersModalOpen(false)} title="Other contributors" width={420}>
        <table className={styles.othersTable}>
          <thead>
            <tr><th>Developer</th><th>Events</th></tr>
          </thead>
          <tbody>
            {othersActors.map((a) => (
              <tr key={a.handle}>
                <td>@{a.handle}</td>
                <td>{a.eventCount}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Modal>

      <Modal open={concentrationModalOpen} onClose={() => setConcentrationModalOpen(false)} title="Activity concentration" width={420}>
        <table className={styles.othersTable}>
          <thead>
            <tr><th>Developer</th><th>Share</th></tr>
          </thead>
          <tbody>
            {activityConcentrationData.map((d) => (
              <tr key={d.handle}>
                <td>@{d.handle}</td>
                <td style={d.textColor ? { color: d.textColor } : undefined}>{d.pct}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Modal>

      {/* Developer detail slide-out panel */}
      <Drawer
        open={selectedDev !== null}
        onClose={handleDrawerClose}
        title="Developer details"
        titleId="dev-detail-title"
      >
        {selectedDev && (
          <DevDetailPanel
            dev={selectedDev}
            detections={actorDetections.get(selectedDev.handle) ?? 0}
            team={findTeamForDev(selectedDev.handle, teamMembers)}
          />
        )}
      </Drawer>
    </div>
  );
}

/** Find the team name for a developer from the team members map. */
function findTeamForDev(
  handle: string,
  teamMembers: Record<string, readonly string[]>,
): string | null {
  for (const [teamName, members] of Object.entries(teamMembers)) {
    if (members.includes(handle)) return teamName;
  }
  return null;
}

interface DevDetailPanelProps {
  dev: ActorStats;
  detections: number;
  team: string | null;
}

function DevDetailPanel({ dev, detections, team }: DevDetailPanelProps) {
  const flagged = detections > 0;
  return (
    <div className={styles.detailPanel}>
      <div className={styles.detailHeader}>
        <Avatar username={dev.handle} size={48} />
        <div>
          <div className={styles.detailName}>
            {dev.handle}
            {flagged && (
              <span style={{ marginLeft: 8, display: 'inline-flex' }}>
                <Label variant="danger" className={styles.flagLabel}>
                  flagged
                </Label>
              </span>
            )}
          </div>
          <div className={styles.detailHandle}>
            <span className={styles.mention}>@{dev.handle}</span>
          </div>
          {team && <div className={styles.detailTeam}>Team: {team}</div>}
        </div>
      </div>

      <div className={styles.detailSection}>
        <div className={styles.detailSectionTitle}>Contributions</div>
        <div className={styles.detailStatsList}>
          <span>📊 <strong>{dev.repoSet.size}</strong> repos</span>
          <span>🔀 <strong>{dev.prCount}</strong> PRs authored</span>
          <span>📝 <strong>{dev.eventCount}</strong> events</span>
          <span style={flagged ? { color: 'var(--danger)' } : undefined}>
            🚨 <strong>{detections}</strong> detections
          </span>
        </div>
      </div>

      <div className={styles.detailSection}>
        <div className={styles.detailSectionTitle}>Weekly Activity</div>
        <MiniBarChart
          data={dev.weeklyCounts}
          color={flagged ? 'var(--danger)' : 'var(--success)'}
          height={48}
        />
      </div>

      <div className={styles.detailSection}>
        <a
          href={`https://github.com/${dev.handle}`}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.detailGhLink}
        >
          View GitHub profile ↗
        </a>
      </div>
    </div>
  );
}

