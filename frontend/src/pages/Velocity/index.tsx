import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getActionsVolumeReport } from '../../api/reports';
import { listEvents } from '../../api/events';
import { ContributionCalendar } from '../../components/charts/ContributionCalendar';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { BarChart } from '../../components/charts/BarChart';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import type { ActionsVolumeBucket } from '../../types/reports';
import styles from './Velocity.module.css';


export function VelocityPage() {
  const changeFailureRef = useRef<HTMLDivElement>(null);
  const workflowSuccessRef = useRef<HTMLDivElement>(null);
  const dailyRunsRef = useRef<HTMLDivElement>(null);
  const reposRef = useRef<HTMLDivElement>(null);
  const calendarRef = useRef<HTMLDivElement>(null);
  const failuresRef = useRef<HTMLDivElement>(null);

  const { data: actionsData, isLoading, isError, refetch } = useQuery({
    queryKey: ['reports', 'actions-volume'],
    queryFn: () => getActionsVolumeReport({ window_days: 30, granularity: 'daily' }),
  });

  const { data: prEvents } = useQuery({
    queryKey: ['events', 'pr-events'],
    queryFn: () => listEvents({ action: 'pull_request', page_size: 500, sort: 'created_at_desc' }),
  });

  const { data: repoEvents } = useQuery({
    queryKey: ['events', 'velocity-repos'],
    queryFn: () => listEvents({ page_size: 500, sort: 'created_at_desc' }),
  });

  const buckets = (actionsData?.data ?? []) as unknown as ActionsVolumeBucket[];

  // Aggregate totals from actions volume data
  const totalRuns = buckets.reduce((sum, b) => sum + (b.workflow_runs_total ?? 0), 0);
  const totalSucceeded = buckets.reduce((sum, b) => sum + (b.workflow_runs_succeeded ?? 0), 0);
  const overallSuccessRate = totalRuns > 0 ? ((totalSucceeded / totalRuns) * 100).toFixed(1) : null;

  const totalFailed = buckets.reduce((sum, b) => sum + (b.workflow_runs_failed ?? 0), 0);
  const changeFailureRate = totalRuns > 0 ? ((totalFailed / totalRuns) * 100).toFixed(1) : null;

  const prMerged = prEvents?.total ?? null;

  // Derive chart data from API buckets
  const chartLabels = buckets.map((b) => {
    const d = new Date(b.bucket);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  });
  const workflowSuccessChartData = buckets.map((b) => b.success_rate_pct ?? 0);
  const changeFailureChartData = buckets.map((b) =>
    b.workflow_runs_total > 0
      ? Math.round((b.workflow_runs_failed / b.workflow_runs_total) * 1000) / 10
      : 0,
  );
  const dailyRunsChartData = buckets.map((b) => b.workflow_runs_total ?? 0);
  const chartDaysLabel = buckets.length > 0 ? `${buckets.length} days` : '—';

  // Derive active repos from events data
  const activeRepos = (() => {
    if (!repoEvents?.items.length) return [];
    const repoMap = new Map<string, { events: number; actors: Set<string> }>();
    for (const e of repoEvents.items) {
      if (!e.repo) continue;
      const existing = repoMap.get(e.repo) ?? { events: 0, actors: new Set<string>() };
      existing.events++;
      if (e.actor) existing.actors.add(e.actor);
      repoMap.set(e.repo, existing);
    }
    return [...repoMap.entries()]
      .sort(([, a], [, b]) => b.events - a.events)
      .slice(0, 5)
      .map(([name, { events, actors }]) => ({
        name,
        events,
        contributors: actors.size,
      }));
  })();

  const metrics = [
    { value: prMerged != null ? prMerged.toLocaleString() : '—', label: 'PRs merged (30d)', delta: 'last 30 days', dir: 'neutral' as const, scrollRef: 'calendar' as const },
    { value: '—', label: 'Lead time for changes', delta: 'Requires GitHub API integration', dir: 'neutral' as const, scrollRef: null },
    { value: '—', label: 'PR cycle time (median)', delta: 'Requires GitHub API integration', dir: 'neutral' as const, scrollRef: null },
    { value: changeFailureRate != null ? `${changeFailureRate}%` : '—', label: 'Change failure rate', delta: changeFailureRate != null ? (parseFloat(changeFailureRate) < 5 ? '< 5% target ✓' : '≥ 5% target') : '—', dir: changeFailureRate != null && parseFloat(changeFailureRate) < 5 ? 'up' as const : 'down' as const, scrollRef: 'changeFailure' as const },
    { value: '—', label: 'Deployments (30d)', delta: 'Requires GitHub API integration', dir: 'neutral' as const, scrollRef: null },
    { value: overallSuccessRate != null ? `${overallSuccessRate}%` : '—', label: 'Workflow success', delta: '30-day average', dir: overallSuccessRate != null && parseFloat(overallSuccessRate) >= 90 ? 'up' as const : 'down' as const, scrollRef: 'workflowSuccess' as const },
    { value: '—', label: 'WIP (items in flight)', delta: 'Requires GitHub API integration', dir: 'neutral' as const, scrollRef: null },
    { value: '—', label: 'Planned work ratio', delta: 'Requires GitHub API integration', dir: 'neutral' as const, scrollRef: null },
  ];

  const refMap = {
    calendar: calendarRef,
    changeFailure: changeFailureRef,
    workflowSuccess: workflowSuccessRef,
    dailyRuns: dailyRunsRef,
    repos: reposRef,
    failures: failuresRef,
  } as const;

  // Most recent failing buckets (last 7 days of failed runs > 0)
  const recentFailingBuckets = buckets
    .filter((b) => (b.workflow_runs_failed ?? 0) > 0)
    .slice(-7)
    .reverse();

  return (
    <div className={styles.page}>
      <div className={styles.titleRow}>
        <div className={styles.pageTitle}>Engineering Velocity</div>
        <div className={styles.doraGroup}>
          <span className={styles.doraLabel}>DORA tier</span>
          <span className={styles.doraBadge}>★ Elite</span>
        </div>
      </div>
      <div className={styles.pageSub}>
        Flow metrics, DORA indicators, and delivery throughput — use as conversation starters, not scorecards
      </div>

      <div className={styles.contextCard}>
        <svg width="14" height="14" fill="var(--accent)" viewBox="0 0 16 16" style={{ flexShrink: 0, marginTop: 1 }}>
          <path d="M0 8a8 8 0 1116 0A8 8 0 010 8zm8-6.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM6.5 7.75A.75.75 0 017.25 7h1a.75.75 0 01.75.75v2.75h.25a.75.75 0 010 1.5h-2a.75.75 0 010-1.5h.25v-2h-.25a.75.75 0 01-.75-.75zM8 6a1 1 0 110-2 1 1 0 010 2z" />
        </svg>
        <span>
          Metrics here measure <strong>system behavior</strong>, not individual performance. A metric moving in an
          unexpected direction is a question to investigate, not a judgment to make.
        </span>
      </div>

      {isError && <ErrorBanner message="Failed to load metrics" onRetry={refetch} />}

      <div className={styles.metricStrip}>
        {metrics.map((m, i) => (
          <MetricCard
            key={i}
            value={m.value}
            label={m.label}
            delta={m.delta}
            deltaDir={m.dir}
            onClick={m.scrollRef ? () => { refMap[m.scrollRef].current?.scrollIntoView({ behavior: 'smooth' }); } : undefined}
          />
        ))}
      </div>

      {isLoading && <Spinner />}

      <div ref={calendarRef}>
        <Card style={{ marginBottom: 20 }}>
          <CardHeader actions={<span style={{ fontWeight: 400 }}>commit + PR + deploy activity</span>}>
            Team contribution calendar — last 13 weeks
          </CardHeader>
          <ContributionCalendar />
        </Card>
      </div>

      <div className={styles.chartsGrid}>
        <div className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Lead time for changes <span className={styles.chartSub}>— requires integration</span>
          </div>
          <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-muted)', fontSize: 13 }}>
            No data available — requires GitHub deployment API integration
          </div>
        </div>

        <div ref={changeFailureRef} className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Change failure rate <span className={styles.chartSub}>— {chartDaysLabel}</span>
          </div>
          {chartLabels.length > 0 ? (
            <LineAreaChart
              xAxisData={chartLabels}
              series={[
                { name: 'CFR', data: changeFailureChartData, color: 'rgb(248, 81, 73)', areaOpacity: 0.15 },
                { name: 'Threshold (5%)', data: Array.from({ length: chartLabels.length }, () => 5), color: 'rgb(248, 81, 73)', dashed: true },
              ]}
              yAxisFormatter={(v: number) => `${v}%`}
            />
          ) : (
            <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-muted)', fontSize: 13 }}>
              No workflow data available
            </div>
          )}
        </div>

        <div ref={workflowSuccessRef} className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Workflow success rate <span className={styles.chartSub}>— {chartDaysLabel}</span>
          </div>
          {chartLabels.length > 0 ? (
            <LineAreaChart
              xAxisData={chartLabels}
              series={[
                { name: 'Success rate', data: workflowSuccessChartData, color: 'rgb(63, 185, 80)', areaOpacity: 0.15 },
              ]}
              yAxisFormatter={(v: number) => `${v}%`}
            />
          ) : (
            <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-muted)', fontSize: 13 }}>
              No workflow data available
            </div>
          )}
        </div>

        <div ref={dailyRunsRef} className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Daily workflow runs <span className={styles.chartSub}>— {chartDaysLabel}</span>
          </div>
          {chartLabels.length > 0 ? (
            <BarChart
              xAxisData={chartLabels}
              series={[
                { name: 'Workflow runs', data: dailyRunsChartData, color: '#58a6ff' },
              ]}
            />
          ) : (
            <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-muted)', fontSize: 13 }}>
              No workflow data available
            </div>
          )}
        </div>
      </div>

      {recentFailingBuckets.length > 0 && (
        <div ref={failuresRef}>
          <div className={styles.sectionTitle}>Recent workflow failures — last 30 days</div>
          <div className={styles.tableWrap} style={{ marginBottom: 20 }}>
            <table>
              <thead><tr><th>Date bucket</th><th>Total runs</th><th>Failed</th><th>Success rate</th></tr></thead>
              <tbody>
                {recentFailingBuckets.map((b, i) => (
                  <tr key={i}>
                    <td>{new Date(b.bucket).toLocaleDateString()}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{b.workflow_runs_total ?? 0}</td>
                    <td><Label variant={(b.workflow_runs_failed ?? 0) > 10 ? 'danger' : 'attention'}>{b.workflow_runs_failed ?? 0}</Label></td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{b.success_rate_pct != null ? `${Math.round(b.success_rate_pct)}%` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div ref={reposRef} className={styles.sectionTitle}>Most active repositories — last 30 days</div>
      <div className={styles.tableWrap} style={{ marginBottom: 20 }}>
        <table>
          <thead>
            <tr>
              <th>Repository</th>
              <th>Events</th>
              <th>Contributors</th>
            </tr>
          </thead>
          <tbody>
            {activeRepos.length > 0 ? (
              activeRepos.map((r) => (
                <tr key={r.name}>
                  <td style={{ fontWeight: 500 }}>{r.name}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{r.events}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{r.contributors}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={3} style={{ color: 'var(--fg-muted)', textAlign: 'center' }}>
                  No repository activity data available
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {buckets.length === 0 && !isLoading && (
        <div style={{ color: 'var(--fg-muted)', padding: '16px 0' }}>No workflow run data for the selected period.</div>
      )}
    </div>
  );
}
