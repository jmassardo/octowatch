import { useMemo, useState, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { listDetections } from '../../api/detections';
import { getTeams } from '../../api/healthSignals';
import { getDevelopers } from '../../api/devActivity';
import { useFeatures } from '../../hooks/useFeatures';
import { PageHeader } from '../../components/common/PageHeader';
import { SkeletonChart } from '../../components/common/SkeletonChart';
import { SkeletonCard } from '../../components/common/SkeletonCard';
import { Avatar } from '../../components/primitives/Avatar';
import { Label } from '../../components/primitives/Label';
import { Card, CardHeader } from '../../components/primitives/Card';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { Drawer } from '../../components/primitives/Drawer';
import { Autocomplete } from '../../components/primitives/Autocomplete';
import { MiniBarChart } from '../../components/charts/MiniBarChart';
import { BarChart } from '../../components/charts/BarChart';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { formatRelativeShort } from '../../utils/dates';
import styles from './DevActivity.module.css';
interface ActorStats {
  handle: string;
  eventCount: number;
  repoCount: number;
  topRepos: string[];
  prCount: number;
  reviewCount: number;
  weeklyCounts: number[];
  lastActive: string | null;
}

export function DevActivityPage() {
  const navigate = useNavigate();
  const { features } = useFeatures();
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);
  const [teamFilterText, setTeamFilterText] = useState('');
  const [othersModalOpen, setOthersModalOpen] = useState(false);
  const [concentrationModalOpen, setConcentrationModalOpen] = useState(false);
  const [selectedDev, setSelectedDev] = useState<ActorStats | null>(null);
  const handleCardClick = useCallback((dev: ActorStats) => {
    setSelectedDev(dev);
  }, []);

  const handleDrawerClose = useCallback(() => {
    setSelectedDev(null);
  }, []);

  const {
    data: developersData,
    isLoading: loadingDevelopers,
    isError: developersError,
    refetch,
  } = useQuery({
    queryKey: ['dev-activity', 'developers'],
    queryFn: () => getDevelopers(),
  });

  const { data: detectionData } = useQuery({
    queryKey: ['detections', 'dev-activity'],
    queryFn: () => listDetections({ page_size: 200, status: 'open' }),
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

  // Build actor stats from server-aggregated developer data
  const { actorMap, actorDetections } = useMemo(() => {
    const map = new Map<string, ActorStats>();
    for (const dev of developersData?.developers ?? []) {
      map.set(dev.login, {
        handle: dev.login,
        eventCount: dev.event_count,
        repoCount: dev.repo_count,
        topRepos: dev.top_repos,
        prCount: dev.pr_count,
        reviewCount: dev.review_count,
        weeklyCounts: dev.weekly_counts,
        lastActive: dev.last_active,
      });
    }

    // Build detections-per-actor map
    const detMap = new Map<string, number>();
    for (const d of detectionData?.items ?? []) {
      if (d.actor) {
        detMap.set(d.actor, (detMap.get(d.actor) ?? 0) + 1);
      }
    }

    return { actorMap: map, actorDetections: detMap };
  }, [developersData?.developers, detectionData?.items]);

  // Compute work distribution from real event data
  const {
    prAuthorshipData,
    activityConcentrationData,
    topActorWarning,
    othersInfo,
    othersActors,
    isReviewData,
  } = useMemo(() => {
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
    const othersPct = totalEvents > 0 ? Math.round((othersEventCount / totalEvents) * 100) : 0;

    const colors = [
      'var(--accent-bg)',
      'var(--accent-bg)',
      'var(--success)',
      'var(--success)',
      'var(--accent)',
    ];
    const prAuthorship = top5.map((actor, i) => ({
      handle: actor.handle,
      pct: Math.round((actor.eventCount / totalEvents) * 100),
      color: colors[i] ?? 'var(--accent)',
    }));

    // Review / activity concentration
    const totalReviewEvents = actors.reduce((s, a) => s + a.reviewCount, 0);
    const hasReviewData = totalReviewEvents > 0;

    const concentrationSorted = hasReviewData
      ? [...actors].sort((a, b) => b.reviewCount - a.reviewCount).filter((a) => a.reviewCount > 0)
      : sorted;
    const concentrationTotal = hasReviewData ? totalReviewEvents : totalEvents;
    const concentrationTop = concentrationSorted.slice(0, 5);

    const concentration = concentrationTop.map((actor) => {
      const count = hasReviewData ? actor.reviewCount : actor.eventCount;
      const pct = Math.round((count / concentrationTotal) * 100);
      const color = pct >= 40 ? 'var(--danger)' : pct >= 25 ? 'var(--attention)' : 'var(--success)';
      const textColor = pct >= 40 ? 'var(--danger)' : pct >= 25 ? 'var(--attention)' : undefined;
      return { handle: actor.handle, pct, color, textColor };
    });

    const topActor = concentration[0];
    const warning =
      topActor && topActor.pct > 40 ? { actor: topActor.handle, pct: topActor.pct } : null;

    const othersActorsList = sorted.slice(5).map((a) => ({
      handle: a.handle,
      eventCount: a.eventCount,
    }));

    return {
      prAuthorshipData: prAuthorship,
      activityConcentrationData: concentration,
      topActorWarning: warning,
      othersInfo: othersActorCount > 0 ? { count: othersActorCount, pct: othersPct } : null,
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

  // ── Widget data: Work Breakdown ────────────────────────────────────────
  const workBreakdown = useMemo(() => {
    const actors = [...actorMap.values()];
    const totalPRs = actors.reduce((s, a) => s + a.prCount, 0);
    const totalReviews = actors.reduce((s, a) => s + a.reviewCount, 0);
    const totalEvents = actors.reduce((s, a) => s + a.eventCount, 0);
    const pushOther = Math.max(0, totalEvents - totalPRs - totalReviews);
    return [totalPRs, totalReviews, pushOther];
  }, [actorMap]);

  // ── Widget data: Contribution Trends (weekly) ──────────────────────────
  const { weekLabels, weeklyPrTotals, weeklyReviewTotals, weeklyActiveDevs } = useMemo(() => {
    const actors = [...actorMap.values()];
    const weekCount = actors.length > 0 ? actors[0].weeklyCounts.length : 0;
    const labels: string[] = [];
    for (let i = 0; i < weekCount; i++) {
      labels.push(`W${i + 1}`);
    }

    const prTotals = new Array<number>(weekCount).fill(0);
    const reviewTotals = new Array<number>(weekCount).fill(0);
    const activeDevs = new Array<number>(weekCount).fill(0);

    for (const actor of actors) {
      const totalActivity = actor.prCount + actor.reviewCount;
      const prRatio = totalActivity > 0 ? actor.prCount / totalActivity : 0.5;
      const reviewRatio = totalActivity > 0 ? actor.reviewCount / totalActivity : 0;

      for (let w = 0; w < weekCount; w++) {
        const weekVal = actor.weeklyCounts[w] ?? 0;
        prTotals[w] += Math.round(weekVal * prRatio);
        reviewTotals[w] += Math.round(weekVal * reviewRatio);
        if (weekVal > 0) {
          activeDevs[w] += 1;
        }
      }
    }

    return {
      weekLabels: labels,
      weeklyPrTotals: prTotals,
      weeklyReviewTotals: reviewTotals,
      weeklyActiveDevs: activeDevs,
    };
  }, [actorMap]);

  // ── Widget data: Activity Distribution ─────────────────────────────────
  const activityBuckets = useMemo(() => {
    let active = 0;
    let moderate = 0;
    let inactive = 0;

    for (const actor of actorMap.values()) {
      if (!actor.lastActive) {
        inactive += 1;
        continue;
      }
      const mostRecentWeek = actor.weeklyCounts;
      const recentActivity = mostRecentWeek[mostRecentWeek.length - 1] ?? 0;
      const hasRecentActivity = recentActivity > 0;
      const hasAnyActivity = mostRecentWeek.some((w) => w > 0);

      if (hasRecentActivity) {
        active += 1;
      } else if (hasAnyActivity) {
        moderate += 1;
      } else {
        inactive += 1;
      }
    }
    return { active, moderate, inactive };
  }, [actorMap]);

  // ── Widget data: Top Contributors Table Columns ────────────────────────
  const contributorColumns: ColumnDef<ActorStats>[] = useMemo(
    () => [
      {
        key: 'rank',
        header: '#',
        helpText: 'Rank by total event count',
        width: '40px',
        sortable: true,
        sortValue: (row: ActorStats) => row.eventCount,
        render: (row: ActorStats) => {
          const idx = topActors.findIndex((a) => a.handle === row.handle);
          return <>{idx >= 0 ? idx + 1 : '—'}</>;
        },
      },
      {
        key: 'handle',
        header: 'Developer',
        helpText: 'GitHub login of the contributor',
        filterable: true,
        filterValue: (row: ActorStats) => row.handle,
        render: (row: ActorStats) => (
          <div className={styles.tableDevCell}>
            <Avatar username={row.handle} size={24} />
            <span className={styles.mention}>@{row.handle}</span>
            {(actorDetections.get(row.handle) ?? 0) > 0 && (
              <Label variant="danger" className={styles.flagLabel}>
                flagged
              </Label>
            )}
          </div>
        ),
      },
      {
        key: 'prCount',
        header: 'PRs',
        helpText: 'Pull requests authored in the lookback period',
        sortable: true,
        sortValue: (row: ActorStats) => row.prCount,
        render: (row: ActorStats) => <>{row.prCount}</>,
      },
      {
        key: 'reviewCount',
        header: 'Reviews',
        helpText: 'Code reviews performed in the lookback period',
        sortable: true,
        sortValue: (row: ActorStats) => row.reviewCount,
        render: (row: ActorStats) => <>{row.reviewCount}</>,
      },
      {
        key: 'repoCount',
        header: 'Repos',
        helpText: 'Number of distinct repositories touched',
        sortable: true,
        sortValue: (row: ActorStats) => row.repoCount,
        render: (row: ActorStats) => <>{row.repoCount}</>,
      },
      {
        key: 'lastActive',
        header: 'Last Active',
        helpText: 'When this developer was last seen in audit logs',
        sortable: true,
        sortValue: (row: ActorStats) => (row.lastActive ? new Date(row.lastActive).getTime() : 0),
        render: (row: ActorStats) => (
          <>{row.lastActive ? formatRelativeShort(row.lastActive) : '—'}</>
        ),
      },
      {
        key: 'trend',
        header: 'Trend',
        helpText: 'Weekly activity sparkline over the lookback period',
        render: (row: ActorStats) => (
          <MiniBarChart
            data={row.weeklyCounts}
            color={(actorDetections.get(row.handle) ?? 0) > 0 ? 'var(--danger)' : 'var(--success)'}
            height={20}
          />
        ),
      },
    ],
    [actorDetections, topActors],
  );

  if (!features.dev_activity) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--fg-muted)' }}>
        <h2>Developer Activity is disabled</h2>
        <p style={{ marginTop: '0.75rem' }}>
          Enable it in{' '}
          <Link to="/settings/features" style={{ color: 'var(--accent)' }}>
            Settings → Features
          </Link>
          .
        </p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <PageHeader
        title="Developer Activity"
        description="Track developer engagement and contribution patterns"
      />

      <div className={styles.teamFilters}>
        {teamNames.length > 0 ? (
          <div className={styles.teamAutocomplete}>
            <Autocomplete
              value={teamFilterText}
              onChange={(val) => {
                setTeamFilterText(val);
                if (!val) {
                  setSelectedTeam(null);
                }
              }}
              onCommit={(val) => {
                if (!val || val.toLowerCase() === 'all teams') {
                  setSelectedTeam(null);
                  setTeamFilterText('');
                } else {
                  const match = teamNames.find((t) => t.toLowerCase() === val.toLowerCase());
                  if (match) {
                    setSelectedTeam(match);
                    setTeamFilterText(match);
                  }
                }
              }}
              suggestions={['All teams', ...teamNames]}
              placeholder="Filter by team…"
              ariaLabel="Filter developers by team"
            />
            {selectedTeam && (
              <button
                className={styles.clearFilter}
                onClick={() => {
                  setSelectedTeam(null);
                  setTeamFilterText('');
                }}
                aria-label="Clear team filter"
              >
                ✕
              </button>
            )}
          </div>
        ) : (
          <span
            className={styles.teamNote}
            title="Team data requires Enterprise Sync or team audit events"
          >
            No team data available
          </span>
        )}
      </div>
      {developersError && (
        <ErrorBanner message="Failed to load developer activity" onRetry={refetch} />
      )}
      {loadingDevelopers && (
        <>
          <SkeletonChart />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </>
      )}

      <div className={styles.sectionTitle} style={{ marginBottom: 4 }}>
        Work distribution — last 30 days
      </div>
      <div className={styles.workNote}>
        Uneven distribution can indicate bus factor risk, burnout, or knowledge silos. Use to start
        conversations, not assign blame.
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
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    navigate(`/events?actor=${d.handle}`);
                  }
                }}
              >
                <span className={styles.barHandle}>@{d.handle}</span>
                <div className={styles.barTrack}>
                  <div
                    style={{
                      width: `${d.pct}%`,
                      height: '100%',
                      background: d.color,
                      borderRadius: 4,
                    }}
                  />
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
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setOthersModalOpen(true);
                  }
                }}
              >
                <span
                  className={styles.barHandle}
                  style={{ color: 'var(--fg-subtle)', fontWeight: 400 }}
                >
                  others ({othersInfo.count})
                </span>
                <div className={styles.barTrack}>
                  <div
                    style={{
                      width: `${Math.max(1, othersInfo.pct)}%`,
                      height: '100%',
                      background: 'var(--border)',
                      borderRadius: 4,
                    }}
                  />
                </div>
                <span className={styles.barPct} style={{ color: 'var(--fg-subtle)' }}>
                  {othersInfo.pct}%
                </span>
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
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    navigate(`/events?actor=${d.handle}`);
                  }
                }}
              >
                <span className={styles.barHandle}>@{d.handle}</span>
                <div className={styles.barTrack}>
                  <div
                    style={{
                      width: `${d.pct}%`,
                      height: '100%',
                      background: d.color,
                      borderRadius: 4,
                    }}
                  />
                </div>
                <span
                  className={styles.barPct}
                  style={d.textColor ? { color: d.textColor } : undefined}
                >
                  {d.pct}%
                </span>
              </div>
            ))}
          </div>
          {topActorWarning ? (
            <div className={styles.busWarning}>
              ⚠{' '}
              <strong
                className={styles.clickableText}
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/events?actor=${topActorWarning.actor}`)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    navigate(`/events?actor=${topActorWarning.actor}`);
                  }
                }}
              >
                @{topActorWarning.actor}
              </strong>{' '}
              accounts for{' '}
              <span
                className={styles.clickableText}
                role="button"
                tabIndex={0}
                onClick={() => setConcentrationModalOpen(true)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setConcentrationModalOpen(true);
                  }
                }}
              >
                {topActorWarning.pct}%
              </span>{' '}
              of activity — consider distributing work to reduce bus factor risk
            </div>
          ) : (
            <div className={styles.busWarning} style={{ color: 'var(--success)' }}>
              ✅ Activity is well distributed — no single contributor exceeds 40%
            </div>
          )}
        </Card>
      </div>

      {/* ── Productivity Widgets ─────────────────────────────────────────── */}

      <div className={styles.widgetRow}>
        {/* Widget 1: Work Breakdown */}
        <Card className={styles.widgetCard}>
          <CardHeader>Work breakdown</CardHeader>
          <BarChart
            xAxisData={['PRs authored', 'Reviews', 'Push/Other']}
            series={[
              {
                name: 'Activity',
                data: workBreakdown,
                color: 'var(--accent)',
              },
            ]}
            height={140}
          />
        </Card>

        {/* Widget 4: Activity Distribution */}
        <Card className={styles.widgetCard}>
          <CardHeader>Activity distribution</CardHeader>
          <div className={styles.activityDistribution}>
            <div className={styles.activityBucket}>
              <div className={styles.activityBucketValue} style={{ color: 'var(--success)' }}>
                {activityBuckets.active}
              </div>
              <div className={styles.activityBucketLabel}>Active (≤7d)</div>
            </div>
            <div className={styles.activityBucket}>
              <div className={styles.activityBucketValue} style={{ color: 'var(--attention)' }}>
                {activityBuckets.moderate}
              </div>
              <div className={styles.activityBucketLabel}>Moderate (7–30d)</div>
            </div>
            <div className={styles.activityBucket}>
              <div className={styles.activityBucketValue} style={{ color: 'var(--fg-muted)' }}>
                {activityBuckets.inactive}
              </div>
              <div className={styles.activityBucketLabel}>Inactive (&gt;30d)</div>
            </div>
          </div>
          <div className={styles.activityBar}>
            {activityBuckets.active > 0 && (
              <div
                className={styles.activityBarSegment}
                style={{
                  flex: activityBuckets.active,
                  background: 'var(--success)',
                }}
                title={`${activityBuckets.active} active`}
              />
            )}
            {activityBuckets.moderate > 0 && (
              <div
                className={styles.activityBarSegment}
                style={{
                  flex: activityBuckets.moderate,
                  background: 'var(--attention)',
                }}
                title={`${activityBuckets.moderate} moderate`}
              />
            )}
            {activityBuckets.inactive > 0 && (
              <div
                className={styles.activityBarSegment}
                style={{
                  flex: activityBuckets.inactive,
                  background: 'var(--border)',
                }}
                title={`${activityBuckets.inactive} inactive`}
              />
            )}
          </div>
        </Card>
      </div>

      {/* Widget 2: Contribution Trends */}
      <Card className={styles.trendsCard}>
        <CardHeader>Contribution trends — weekly</CardHeader>
        <LineAreaChart
          xAxisData={weekLabels}
          series={[
            { name: 'PRs', data: weeklyPrTotals, color: 'var(--accent)', areaOpacity: 0.15 },
            {
              name: 'Reviews',
              data: weeklyReviewTotals,
              color: 'var(--success)',
              areaOpacity: 0.1,
            },
            {
              name: 'Active devs',
              data: weeklyActiveDevs,
              color: 'var(--attention)',
              dashed: true,
            },
          ]}
          height={180}
        />
      </Card>

      {/* Widget 3: Top Contributors Table */}
      <div className={styles.sectionTitle} style={{ marginBottom: 16 }}>
        Top contributors
      </div>
      {topActors.length === 0 && !loadingDevelopers && (
        <div style={{ color: 'var(--fg-muted)', padding: '16px 0' }}>
          No developer activity data found.
        </div>
      )}
      <DataTable<ActorStats>
        columns={contributorColumns}
        data={topActors}
        rowKey={(row) => row.handle}
        onRowClick={handleCardClick}
        emptyMessage="No developer activity data found."
        className={styles.contributorsTable}
      />

      <Drawer
        open={othersModalOpen}
        onClose={() => setOthersModalOpen(false)}
        title="Other contributors"
      >
        <DataTable<{ handle: string; eventCount: number }>
          columns={
            [
              {
                key: 'handle',
                header: 'Developer',
                helpText: 'GitHub login handle of the contributor. From audit log actor fields.',
                filterable: true,
                filterValue: (row) => row.handle,
                render: (row) => <>@{row.handle}</>,
              },
              {
                key: 'eventCount',
                header: 'Events',
                helpText:
                  'Total audit log events attributed to this developer in the last 30 days.',
                sortable: true,
                sortValue: (row) => row.eventCount,
                render: (row) => <>{row.eventCount}</>,
              },
            ] satisfies ColumnDef<{ handle: string; eventCount: number }>[]
          }
          data={othersActors}
          rowKey={(a) => a.handle}
          className={styles.othersTable}
        />
      </Drawer>

      <Drawer
        open={concentrationModalOpen}
        onClose={() => setConcentrationModalOpen(false)}
        title="Activity concentration"
      >
        <DataTable<{ handle: string; pct: number; color: string; textColor?: string }>
          columns={
            [
              {
                key: 'handle',
                header: 'Developer',
                helpText: 'GitHub login handle of the contributor. From audit log actor fields.',
                filterable: true,
                filterValue: (row) => row.handle,
                render: (row) => <>@{row.handle}</>,
              },
              {
                key: 'pct',
                header: 'Share',
                helpText:
                  "This developer's share of total activity. High concentration (>40%) in one person may indicate bus factor risk.",
                sortable: true,
                sortValue: (row) => row.pct,
                render: (row) => (
                  <span style={row.textColor ? { color: row.textColor } : undefined}>
                    {row.pct}%
                  </span>
                ),
              },
            ] satisfies ColumnDef<{
              handle: string;
              pct: number;
              color: string;
              textColor?: string;
            }>[]
          }
          data={activityConcentrationData}
          rowKey={(d) => d.handle}
          className={styles.othersTable}
        />
      </Drawer>

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
          <span>
            📊 <strong>{dev.repoCount}</strong> repos
          </span>
          <span>
            🔀 <strong>{dev.prCount}</strong> PRs authored
          </span>
          <span>
            📝 <strong>{dev.eventCount}</strong> events
          </span>
          <span style={flagged ? { color: 'var(--danger)' } : undefined}>
            🚨 <strong>{detections}</strong> detections
          </span>
          {dev.lastActive && <span>🕐 Last active {formatRelativeShort(dev.lastActive)}</span>}
        </div>
      </div>

      {dev.topRepos.length > 0 && (
        <div className={styles.detailSection}>
          <div className={styles.detailSectionTitle}>Most Active Repos</div>
          <div className={styles.detailStatsList}>
            {dev.topRepos.map((repo) => (
              <span key={repo}>📁 {repo}</span>
            ))}
          </div>
        </div>
      )}

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
