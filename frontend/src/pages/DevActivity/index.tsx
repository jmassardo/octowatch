import { useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { listEvents } from '../../api/events';
import { listDetections } from '../../api/detections';
import { getTeams } from '../../api/healthSignals';
import { getUsageStats, type UsageStatsResponse } from '../../api/devActivity';
import { useFeatures } from '../../hooks/useFeatures';
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
  const { features } = useFeatures();
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
    queryFn: () => listDetections({ page_size: 200, status: 'open' }),
  });

  const { data: teamsData } = useQuery({
    queryKey: ['teams'],
    queryFn: getTeams,
  });

  const { data: usageStats } = useQuery({
    queryKey: ['dev-activity', 'usage-stats'],
    queryFn: getUsageStats,
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

  if (!features.dev_activity) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--fg-muted)' }}>
        <h2>Developer Activity is disabled</h2>
        <p style={{ marginTop: '0.75rem' }}>
          Enable it in <a href="/settings/features" style={{ color: 'var(--accent)' }}>Settings → Features</a>.
        </p>
      </div>
    );
  }

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

      {/* ── Platform usage section ─────────────────────────────── */}
      <div className={styles.sectionTitle} style={{ marginBottom: 4, marginTop: 24 }}>Platform usage — last 30 days</div>
      <div className={styles.workNote}>
        Git operations and API request patterns across your organization.
      </div>

      <div className={styles.usageGrid}>
        <GitOperationsWidget stats={usageStats} navigate={navigate} />
        <ApiUsageWidget stats={usageStats} navigate={navigate} />
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

/* ── Helper: compute bar width percentage from max count ──────────────── */

function barPct(count: number, max: number): number {
  return max > 0 ? Math.round((count / max) * 100) : 0;
}

/* ── Git Operations widget ────────────────────────────────────────────── */

interface WidgetProps {
  stats: UsageStatsResponse | undefined;
  navigate: (path: string) => void;
}

function GitOperationsWidget({ stats, navigate }: WidgetProps) {
  const git = stats?.git_stats;
  const bvh = stats?.bot_vs_human;

  const totalGit = (git?.total_clones ?? 0) + (git?.total_pushes ?? 0) + (git?.total_fetches ?? 0);
  const botTotal = (bvh?.bot_events ?? 0) + (bvh?.human_events ?? 0);
  const botPct = botTotal > 0 ? Math.round(((bvh?.bot_events ?? 0) / botTotal) * 100) : 0;

  const trendMax = Math.max(
    ...((git?.daily_trend ?? []).map((d) => d.clones + d.pushes + d.fetches)),
    1,
  );

  const cloneMax = Math.max(...((git?.top_cloners ?? []).map((c) => c.count)), 1);
  const pushMax = Math.max(...((git?.top_pushers ?? []).map((p) => p.count)), 1);

  return (
    <Card>
      <CardHeader>Git operations</CardHeader>
      <div className={styles.metricRow}>
        <div className={styles.metricItem}>
          <div className={styles.metricValue}>{git?.total_clones ?? 0}</div>
          <div className={styles.metricLabel}>Clones</div>
        </div>
        <div className={styles.metricItem}>
          <div className={styles.metricValue}>{git?.total_pushes ?? 0}</div>
          <div className={styles.metricLabel}>Pushes</div>
        </div>
        <div className={styles.metricItem}>
          <div className={styles.metricValue}>{git?.total_fetches ?? 0}</div>
          <div className={styles.metricLabel}>Fetches</div>
        </div>
      </div>

      {totalGit > 0 && (git?.daily_trend ?? []).length > 0 && (
        <>
          <div className={styles.subsectionTitle}>Daily trend</div>
          <div className={styles.trendChart}>
            {git!.daily_trend.map((d) => {
              const total = d.clones + d.pushes + d.fetches;
              const h = Math.max(3, (total / trendMax) * 40);
              return (
                <div
                  key={d.date}
                  title={`${d.date}: ${total} events`}
                  style={{
                    width: 10,
                    height: h,
                    borderRadius: 2,
                    background: '#1f6feb',
                  }}
                />
              );
            })}
          </div>
        </>
      )}

      {(git?.top_cloners ?? []).length > 0 && (
        <>
          <div className={styles.subsectionTitle}>Top cloners</div>
          <div className={styles.barList}>
            {git!.top_cloners.slice(0, 5).map((c) => (
              <div
                key={c.actor}
                className={`${styles.barRow} ${styles.clickableBar}`}
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/events?actor=${c.actor}&action=git.clone`)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/events?actor=${c.actor}&action=git.clone`); } }}
              >
                <span className={styles.barHandle} style={c.is_bot ? { fontStyle: 'italic' } : undefined}>
                  {c.is_bot ? c.actor : `@${c.actor}`}
                </span>
                <div className={styles.barTrack}>
                  <div style={{ width: `${barPct(c.count, cloneMax)}%`, height: '100%', background: '#1f6feb', borderRadius: 4 }} />
                </div>
                <span className={styles.barPct}>{c.count}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {(git?.top_pushers ?? []).length > 0 && (
        <>
          <div className={styles.subsectionTitle}>Top pushers</div>
          <div className={styles.barList}>
            {git!.top_pushers.slice(0, 5).map((p) => (
              <div
                key={p.actor}
                className={`${styles.barRow} ${styles.clickableBar}`}
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/events?actor=${p.actor}&action=git.push`)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/events?actor=${p.actor}&action=git.push`); } }}
              >
                <span className={styles.barHandle}>@{p.actor}</span>
                <div className={styles.barTrack}>
                  <div style={{ width: `${barPct(p.count, pushMax)}%`, height: '100%', background: '#238636', borderRadius: 4 }} />
                </div>
                <span className={styles.barPct}>{p.count}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {botTotal > 0 && (
        <>
          <div className={styles.subsectionTitle}>Bot vs Human</div>
          <div className={styles.botBar}>
            <div className={styles.botSegment} style={{ width: `${botPct}%` }} />
            <div className={styles.humanSegment} style={{ width: `${100 - botPct}%` }} />
          </div>
          <div className={styles.botBarLabels}>
            <span>🤖 Bot {botPct}%</span>
            <span>👤 Human {100 - botPct}%</span>
          </div>
        </>
      )}
    </Card>
  );
}

/* ── API Usage widget ─────────────────────────────────────────────────── */

function ApiUsageWidget({ stats, navigate }: WidgetProps) {
  const apiStats = stats?.api_stats;

  if (!apiStats || !apiStats.available) {
    return (
      <Card>
        <CardHeader>API usage</CardHeader>
        <div className={styles.apiDisabledNote}>
          <p>No API request events found in the last 30 days.</p>
          <p style={{ marginTop: 8 }}>
            To see API usage data, enable <strong>API request events</strong> in your{' '}
            <a
              href="https://docs.github.com/en/enterprise-cloud@latest/admin/monitoring-activity-in-your-enterprise/reviewing-audit-logs-for-your-enterprise/streaming-the-audit-log-for-your-enterprise"
              target="_blank"
              rel="noopener noreferrer"
            >
              GitHub Enterprise audit log streaming settings
            </a>.
          </p>
        </div>
      </Card>
    );
  }

  const uniqueUsers = apiStats.top_users.length;
  const uniqueEndpoints = apiStats.top_endpoints.length;
  const userMax = Math.max(...apiStats.top_users.map((u) => u.count), 1);
  const endpointMax = Math.max(...apiStats.top_endpoints.map((e) => e.count), 1);
  const trendMax = Math.max(...apiStats.daily_trend.map((d) => d.requests), 1);

  return (
    <Card>
      <CardHeader>API usage</CardHeader>
      <div className={styles.metricRow}>
        <div className={styles.metricItem}>
          <div className={styles.metricValue}>{apiStats.total_requests.toLocaleString()}</div>
          <div className={styles.metricLabel}>Total requests</div>
        </div>
        <div className={styles.metricItem}>
          <div className={styles.metricValue}>{uniqueUsers}</div>
          <div className={styles.metricLabel}>Unique users</div>
        </div>
        <div className={styles.metricItem}>
          <div className={styles.metricValue}>{uniqueEndpoints}</div>
          <div className={styles.metricLabel}>Unique endpoints</div>
        </div>
      </div>

      {apiStats.daily_trend.length > 0 && (
        <>
          <div className={styles.subsectionTitle}>Daily trend</div>
          <div className={styles.trendChart}>
            {apiStats.daily_trend.map((d) => {
              const h = Math.max(3, (d.requests / trendMax) * 40);
              return (
                <div
                  key={d.date}
                  title={`${d.date}: ${d.requests} requests`}
                  style={{
                    width: 10,
                    height: h,
                    borderRadius: 2,
                    background: '#58a6ff',
                  }}
                />
              );
            })}
          </div>
        </>
      )}

      {apiStats.top_users.length > 0 && (
        <>
          <div className={styles.subsectionTitle}>Top API users</div>
          <div className={styles.barList}>
            {apiStats.top_users.slice(0, 5).map((u) => (
              <div
                key={u.actor}
                className={`${styles.barRow} ${styles.clickableBar}`}
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/events?actor=${u.actor}`)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/events?actor=${u.actor}`); } }}
              >
                <span className={styles.barHandle}>@{u.actor}</span>
                <div className={styles.barTrack}>
                  <div style={{ width: `${barPct(u.count, userMax)}%`, height: '100%', background: '#58a6ff', borderRadius: 4 }} />
                </div>
                <span className={styles.barPct}>{u.count}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {apiStats.top_endpoints.length > 0 && (
        <>
          <div className={styles.subsectionTitle}>Top endpoints</div>
          <div className={styles.barList}>
            {apiStats.top_endpoints.slice(0, 5).map((ep) => (
              <div key={ep.endpoint} className={styles.barRow}>
                <span className={styles.barHandle} title={ep.endpoint} style={{ width: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {ep.endpoint}
                </span>
                <div className={styles.barTrack}>
                  <div style={{ width: `${barPct(ep.count, endpointMax)}%`, height: '100%', background: '#58a6ff', borderRadius: 4 }} />
                </div>
                <span className={styles.barPct}>{ep.count}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
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

