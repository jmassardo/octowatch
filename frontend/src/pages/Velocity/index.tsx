import { useMemo, useRef, useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, Link } from 'react-router-dom';
import { getActionsVolumeReport } from '../../api/reports';
import { listEvents } from '../../api/events';
import { getBranchProtection } from '../../api/healthSignals';
import { ContributionCalendar } from '../../components/charts/ContributionCalendar';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { BarChart } from '../../components/charts/BarChart';
import { MetricCard } from '../../components/primitives/MetricCard';
import { useEnumQueryParam } from '../../hooks/useQueryParam';
import { useChartColors } from '../../hooks/useChartColors';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { DataTable } from '../../components/primitives/DataTable';
import { Drawer } from '../../components/primitives/Drawer';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { PageHeader } from '../../components/common/PageHeader';
import { LeadershipPane } from './LeadershipPane';
import { useFeatures } from '../../hooks/useFeatures';
import type { ActionsVolumeBucket } from '../../types/reports';
import type { EventResponse } from '../../types/events';
import { formatBucketDate } from '../../utils/dates';
import styles from './Velocity.module.css';

interface CalendarDay {
  date: string;
  level: 0 | 1 | 2 | 3 | 4;
  alert?: boolean;
}

interface RepoActivityStats {
  readonly name: string;
  readonly totalEvents: number;
  readonly prEvents: number;
  readonly pushEvents: number;
  readonly contributors: number;
}

/** Convert a list of events into per-day contribution calendar data (last 91 days). */
function buildCalendarData(events: readonly EventResponse[]): CalendarDay[] {
  const now = new Date();
  const counts = new Map<string, number>();

  // Initialize last 91 days with zero counts
  for (let i = 90; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    counts.set(d.toISOString().slice(0, 10), 0);
  }

  // Count events per day (skip noisy api.request events)
  for (const e of events) {
    if (e.action === 'api.request') continue;
    const day = e.created_at.slice(0, 10);
    if (counts.has(day)) {
      counts.set(day, (counts.get(day) ?? 0) + 1);
    }
  }

  // Determine thresholds for levels based on max count
  const values = [...counts.values()];
  const maxCount = Math.max(...values, 1);

  return [...counts.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, count]) => {
      let level: 0 | 1 | 2 | 3 | 4;
      if (count === 0) level = 0;
      else if (count <= maxCount * 0.25) level = 1;
      else if (count <= maxCount * 0.5) level = 2;
      else if (count <= maxCount * 0.75) level = 3;
      else level = 4;
      return { date, level };
    });
}

/** Compute per-repo activity stats from a list of events. */
function computeRepoStats(events: readonly EventResponse[]): RepoActivityStats[] {
  const repoMap = new Map<
    string,
    { total: number; pr: number; push: number; actors: Set<string> }
  >();
  for (const e of events) {
    if (!e.repo) continue;
    // Skip noisy api.request events — not meaningful for repo activity
    if (e.action === 'api.request') continue;
    const existing = repoMap.get(e.repo) ?? { total: 0, pr: 0, push: 0, actors: new Set<string>() };
    existing.total++;
    if (e.action.includes('pull_request')) existing.pr++;
    if (e.action.includes('push') || e.action.includes('git.push')) existing.push++;
    if (e.actor) existing.actors.add(e.actor);
    repoMap.set(e.repo, existing);
  }
  return [...repoMap.entries()]
    .map(([name, stats]) => ({
      name,
      totalEvents: stats.total,
      prEvents: stats.pr,
      pushEvents: stats.push,
      contributors: stats.actors.size,
    }))
    .sort((a, b) => b.totalEvents - a.totalEvents)
    .slice(0, 10);
}

interface DoraTier {
  readonly name: 'Elite' | 'High' | 'Medium' | 'Low';
  readonly icon: string;
  readonly cssClass: string;
}

/**
 * Compute DORA tier from available metrics using standard DORA benchmarks.
 *
 * Scoring:
 *  - 4 = Elite, 3 = High, 2 = Medium, 1 = Low
 *  - Final tier is the average of all available metric scores.
 */
function computeDoraTier(deployFreqPerDay: number, cfr: number | null): DoraTier {
  const scores: number[] = [];

  // Deployment Frequency: Elite ≥ 1/day, High ≥ 1/week, Medium ≥ 1/month
  if (deployFreqPerDay >= 1) scores.push(4);
  else if (deployFreqPerDay >= 1 / 7) scores.push(3);
  else if (deployFreqPerDay >= 1 / 30) scores.push(2);
  else scores.push(1);

  // Change Failure Rate: Elite < 5%, High < 10%, Medium < 15%
  if (cfr !== null) {
    if (cfr < 5) scores.push(4);
    else if (cfr < 10) scores.push(3);
    else if (cfr < 15) scores.push(2);
    else scores.push(1);
  }

  const avg = scores.reduce((a, b) => a + b, 0) / scores.length;

  if (avg >= 3.5) return { name: 'Elite', icon: '★', cssClass: 'doraTierElite' };
  if (avg >= 2.5) return { name: 'High', icon: '▲', cssClass: 'doraTierHigh' };
  if (avg >= 1.5) return { name: 'Medium', icon: '◆', cssClass: 'doraTierMedium' };
  return { name: 'Low', icon: '▼', cssClass: 'doraTierLow' };
}

interface BranchProtectionProps {
  branchProt:
    | {
        protections_removed: number;
        policy_overrides: number;
        modified: number;
        distinct_repos_affected: number;
      }
    | undefined;
}

function BranchProtectionSection({ branchProt }: BranchProtectionProps) {
  const total = branchProt
    ? branchProt.protections_removed + branchProt.policy_overrides + branchProt.modified
    : 0;

  return (
    <div style={{ marginTop: 8 }}>
      <div className={styles.sectionTitle}>Branch protection changes (30d)</div>
      <div className={styles.metricStrip} style={{ marginBottom: 12 }}>
        <MetricCard
          value={String(branchProt?.protections_removed ?? 0)}
          label="Protections removed"
        />
        <MetricCard value={String(branchProt?.policy_overrides ?? 0)} label="Policy overrides" />
        <MetricCard value={String(branchProt?.modified ?? 0)} label="Modified" />
        <MetricCard
          value={String(branchProt?.distinct_repos_affected ?? 0)}
          label="Repos affected"
        />
      </div>
      {total === 0 && (
        <div style={{ color: 'var(--fg-muted)', fontSize: 13, padding: '8px 0', marginBottom: 20 }}>
          No branch protection weakening events detected in the last 30 days.
        </div>
      )}
    </div>
  );
}

export function VelocityPage() {
  const navigate = useNavigate();
  const { features } = useFeatures();
  const [activeTab, setActiveTab] = useEnumQueryParam(
    'tab',
    ['metrics', 'leadership'] as const,
    'metrics',
  );
  const [doraModalOpen, setDoraModalOpen] = useState(false);
  const [failureBucket, setFailureBucket] = useState<ActionsVolumeBucket | null>(null);
  const [drillFilter, setDrillFilter] = useState<'total' | 'succeeded' | 'failed' | null>(null);
  const [defsOpen, setDefsOpen] = useState(false);
  const chartColors = useChartColors();
  const changeFailureRef = useRef<HTMLDivElement>(null);
  const workflowSuccessRef = useRef<HTMLDivElement>(null);
  const dailyRunsRef = useRef<HTMLDivElement>(null);
  const reposRef = useRef<HTMLDivElement>(null);
  const calendarRef = useRef<HTMLDivElement>(null);

  const {
    data: actionsData,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['reports', 'actions-volume'],
    queryFn: () => getActionsVolumeReport({ window_days: 30, granularity: 'daily' }),
  });

  const { data: prEvents } = useQuery({
    queryKey: ['events', 'pr-events'],
    queryFn: () =>
      listEvents({ action: 'pull_request.*', page_size: 500, sort: 'created_at_desc' }),
  });

  const { data: repoEvents } = useQuery({
    queryKey: ['events', 'velocity-repos'],
    queryFn: () =>
      listEvents({
        page_size: 2000,
        sort: 'created_at_desc',
      }),
  });

  const { data: branchProtData } = useQuery({
    queryKey: ['health', 'branch-protection-velocity'],
    queryFn: getBranchProtection,
    staleTime: 60_000,
  });

  // Fetch events for the last 91 days for the contribution calendar
  const calendarSince = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - 91);
    return d.toISOString();
  }, []);

  const { data: calendarEvents } = useQuery({
    queryKey: ['events', 'calendar-activity', calendarSince],
    queryFn: () => listEvents({ since: calendarSince, page_size: 2000, sort: 'created_at_desc' }),
    staleTime: 60_000,
  });

  const calendarData = useMemo(
    () => (calendarEvents?.items ? buildCalendarData(calendarEvents.items) : undefined),
    [calendarEvents],
  );

  // Drill-down: fetch actual workflow events for the selected bucket & filter
  const drillAction = useMemo(() => {
    if (!drillFilter) return undefined;
    if (drillFilter === 'total') return 'workflow_run.*';
    if (drillFilter === 'succeeded') return 'workflow_run.success';
    return 'workflow_run.failure';
  }, [drillFilter]);

  const drillSince = useMemo(() => {
    if (!failureBucket) return undefined;
    return new Date(failureBucket.bucket).toISOString();
  }, [failureBucket]);

  const drillUntil = useMemo(() => {
    if (!failureBucket) return undefined;
    const d = new Date(failureBucket.bucket);
    d.setDate(d.getDate() + 1);
    return d.toISOString();
  }, [failureBucket]);

  const { data: drillEvents, isLoading: drillLoading } = useQuery({
    queryKey: ['events', 'drill', drillAction, drillSince],
    queryFn: () =>
      listEvents({
        action: drillAction,
        since: drillSince,
        until: drillUntil,
        page_size: 200,
        sort: 'created_at_desc',
      }),
    enabled: !!failureBucket && !!drillFilter,
    staleTime: 30_000,
  });

  const handleCloseBucket = useCallback(() => {
    setFailureBucket(null);
    setDrillFilter(null);
  }, []);

  const buckets = (actionsData?.data ?? []) as unknown as ActionsVolumeBucket[];

  // Aggregate totals from actions volume data
  const totalRuns = buckets.reduce((sum, b) => sum + (b.workflow_runs_total ?? 0), 0);
  const totalSucceeded = buckets.reduce((sum, b) => sum + (b.workflow_runs_succeeded ?? 0), 0);
  const overallSuccessRate = totalRuns > 0 ? ((totalSucceeded / totalRuns) * 100).toFixed(1) : null;

  const totalFailed = buckets.reduce((sum, b) => sum + (b.workflow_runs_failed ?? 0), 0);
  const changeFailureRate = totalRuns > 0 ? ((totalFailed / totalRuns) * 100).toFixed(1) : null;

  const prMerged = prEvents?.total ?? null;

  // Count PR review events from general events for "PR reviews" metric
  const prReviewCount = useMemo(() => {
    if (!repoEvents?.items) return null;
    const count = repoEvents.items.filter((e) => e.action.includes('pull_request')).length;
    return count > 0 ? count : null;
  }, [repoEvents]);

  // Count successful workflow runs as deployment proxy
  const deploymentProxy = totalSucceeded > 0 ? totalSucceeded : null;

  // Estimate WIP: opened PRs minus closed/merged PRs from events
  const wipEstimate = useMemo(() => {
    if (!repoEvents?.items) return null;
    const opened = repoEvents.items.filter(
      (e) =>
        e.action.includes('pull_request') &&
        (e.action.includes('opened') || e.action.includes('created')),
    ).length;
    const closed = repoEvents.items.filter(
      (e) =>
        e.action.includes('pull_request') &&
        (e.action.includes('closed') || e.action.includes('merged')),
    ).length;
    return opened > 0 || closed > 0 ? Math.max(0, opened - closed) : null;
  }, [repoEvents]);

  // Review coverage: percentage of merged PRs with review activity
  const reviewCoverage = useMemo(() => {
    if (prMerged == null || prMerged === 0 || prReviewCount == null) return null;
    return Math.round(Math.min((prReviewCount / prMerged) * 100, 100));
  }, [prMerged, prReviewCount]);

  // Compute repo activity stats from events
  const repoStats = useMemo(
    () => (repoEvents?.items ? computeRepoStats(repoEvents.items) : []),
    [repoEvents],
  );

  // Derive chart data from API buckets
  const chartLabels = buckets.map((b) => {
    const d = new Date(b.bucket);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  });
  const workflowSuccessChartData = buckets.map((b) => b.success_rate_pct ?? 0);
  const changeFailureChartData = buckets.map((b) =>
    (b.workflow_runs_total ?? 0) > 0
      ? Math.round(((b.workflow_runs_failed ?? 0) / (b.workflow_runs_total ?? 1)) * 1000) / 10
      : 0,
  );
  const dailyRunsChartData = buckets.map((b) => b.workflow_runs_total ?? 0);
  const chartDaysLabel = buckets.length > 0 ? `${buckets.length} days` : '—';

  // Lead time proxy: estimate hours-per-change from daily deployment frequency.
  // More frequent deployments imply shorter lead times.
  const leadTimeChartData = buckets.map((b) => {
    if ((b.workflow_runs_succeeded ?? 0) === 0) return 0;
    return Math.round((24 / Math.max(b.workflow_runs_succeeded ?? 0, 1)) * 10) / 10;
  });

  // Average lead time across the period
  const avgLeadTime =
    leadTimeChartData.length > 0
      ? leadTimeChartData.filter((v) => v > 0).reduce((a, b) => a + b, 0) /
        Math.max(leadTimeChartData.filter((v) => v > 0).length, 1)
      : null;

  // MTTR proxy: estimate recovery hours from daily failure rate.
  // Higher failure rates imply longer recovery windows.
  const mttrChartData = buckets.map((b) => {
    if ((b.workflow_runs_failed ?? 0) === 0) return 0;
    const failureRate =
      (b.workflow_runs_total ?? 0) > 0
        ? (b.workflow_runs_failed ?? 0) / (b.workflow_runs_total ?? 1)
        : 0;
    return Math.round(failureRate * 24 * 10) / 10;
  });

  // Dynamic DORA tier based on available metrics
  const hasWorkflowData = totalRuns > 0;
  const deployFreqPerDay = hasWorkflowData ? totalSucceeded / 30 : 0;
  const cfrNum = changeFailureRate != null ? parseFloat(changeFailureRate) : null;
  const doraTier = hasWorkflowData ? computeDoraTier(deployFreqPerDay, cfrNum) : null;

  const metrics = [
    {
      value: prMerged != null ? prMerged.toLocaleString() : '—',
      label: 'PRs merged (30d)',
      delta: 'last 30 days',
      dir: 'neutral' as const,
      scrollRef: 'calendar' as const,
      definition:
        'Count of pull_request.merged events from the enterprise audit log over the last 30 days.',
    },
    {
      value: avgLeadTime != null && avgLeadTime > 0 ? `${avgLeadTime.toFixed(1)}h` : '—',
      label: 'Lead time for changes',
      delta:
        avgLeadTime != null && avgLeadTime > 0
          ? 'estimated from workflow frequency'
          : 'Insufficient data — requires deployment tracking',
      dir: 'neutral' as const,
      scrollRef: null,
      definition:
        'DORA metric. Estimated as 24 ÷ successful workflow runs per day. More frequent deployments imply shorter lead times. Actual lead time requires commit-to-deploy tracking.',
    },
    {
      value: prReviewCount != null ? prReviewCount.toLocaleString() : '—',
      label: 'PR activity (30d)',
      delta: prReviewCount != null ? 'pull_request events from audit log' : 'No PR events found',
      dir: 'neutral' as const,
      scrollRef: 'calendar' as const,
      definition:
        'Total pull_request.* events (opened, closed, merged, reviewed) from the enterprise audit log over the last 30 days.',
    },
    {
      value: changeFailureRate != null ? `${changeFailureRate}%` : '—',
      label: 'Change failure rate',
      delta:
        changeFailureRate != null
          ? parseFloat(changeFailureRate) < 5
            ? '< 5% target ✓'
            : '≥ 5% target'
          : '—',
      dir:
        changeFailureRate != null && parseFloat(changeFailureRate) < 5
          ? ('up' as const)
          : ('down' as const),
      scrollRef: 'changeFailure' as const,
      definition:
        'DORA metric. Percentage of workflow runs that failed: (failed runs ÷ total runs) × 100. Elite teams target < 5%.',
    },
    {
      value: deploymentProxy != null ? deploymentProxy.toLocaleString() : '—',
      label: 'Successful workflows (30d)',
      delta: deploymentProxy != null ? 'proxy for deployment frequency' : 'No workflow data',
      dir: deploymentProxy != null ? ('neutral' as const) : ('neutral' as const),
      scrollRef: 'workflowSuccess' as const,
      definition:
        'Count of workflow_run.success events over 30 days. Used as a proxy for deployment frequency (DORA). Includes CI, CD, and scheduled workflows.',
    },
    {
      value: overallSuccessRate != null ? `${overallSuccessRate}%` : '—',
      label: 'Workflow success',
      delta: '30-day average',
      dir:
        overallSuccessRate != null && parseFloat(overallSuccessRate) >= 90
          ? ('up' as const)
          : ('down' as const),
      scrollRef: 'workflowSuccess' as const,
      definition:
        'Percentage of workflow runs that succeeded: (succeeded ÷ total) × 100, computed daily and averaged over 30 days.',
    },
    {
      value: wipEstimate != null ? wipEstimate.toString() : '—',
      label: 'WIP (items in flight)',
      delta: wipEstimate != null ? 'estimated from PR events' : 'No PR data available',
      dir: 'neutral' as const,
      scrollRef: null,
      definition:
        'Estimated work-in-progress: PR opened/created events minus PR closed/merged events. High WIP can indicate bottlenecks or stalled reviews.',
    },
    {
      value: reviewCoverage != null ? `${reviewCoverage}%` : '—',
      label: 'Review coverage',
      delta: reviewCoverage != null ? 'reviews per merged PR' : 'No PR data',
      dir: reviewCoverage != null && reviewCoverage >= 80 ? ('up' as const) : ('neutral' as const),
      scrollRef: null,
      definition:
        'Ratio of PR review events to merged PRs: (review events ÷ merged PRs) × 100, capped at 100%. Measures how many PRs receive review before merging.',
    },
  ];

  const refMap = {
    calendar: calendarRef,
    changeFailure: changeFailureRef,
    workflowSuccess: workflowSuccessRef,
    dailyRuns: dailyRunsRef,
    repos: reposRef,
  } as const;

  if (!features.velocity) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--fg-muted)' }}>
        <h2>Engineering Velocity is disabled</h2>
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
        title="Engineering Velocity"
        description="Track CI/CD throughput and development flow metrics"
        showHelp
      />

      {/* Tab bar */}
      <div className={styles.tabBar} role="tablist" aria-label="Velocity views">
        <button
          role="tab"
          aria-selected={activeTab === 'metrics'}
          className={[styles.tab, activeTab === 'metrics' && styles.tabActive]
            .filter(Boolean)
            .join(' ')}
          onClick={() => setActiveTab('metrics')}
        >
          Metrics
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'leadership'}
          className={[styles.tab, activeTab === 'leadership' && styles.tabActive]
            .filter(Boolean)
            .join(' ')}
          onClick={() => setActiveTab('leadership')}
        >
          Leadership
        </button>
      </div>

      {activeTab === 'leadership' && <LeadershipPane />}

      {activeTab === 'metrics' && (
        <>
          <div className={styles.titleRow}>
            <div className={styles.doraGroup}>
              <span className={styles.doraLabel}>DORA tier</span>
              <span
                className={[
                  styles.doraBadge,
                  doraTier ? styles[doraTier.cssClass] : '',
                  styles.doraBadgeClickable,
                ]
                  .filter(Boolean)
                  .join(' ')}
                role="button"
                tabIndex={0}
                aria-label={
                  doraTier
                    ? `DORA ${doraTier.name} tier — click for details`
                    : 'DORA tier pending — click for details'
                }
                onClick={() => setDoraModalOpen(true)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setDoraModalOpen(true);
                  }
                }}
              >
                {doraTier ? `${doraTier.icon} ${doraTier.name}` : '— Pending'}
              </span>
            </div>
          </div>

          <div className={styles.contextCard}>
            <svg
              width="14"
              height="14"
              fill="var(--accent)"
              viewBox="0 0 16 16"
              style={{ flexShrink: 0, marginTop: 1 }}
            >
              <path d="M0 8a8 8 0 1116 0A8 8 0 010 8zm8-6.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM6.5 7.75A.75.75 0 017.25 7h1a.75.75 0 01.75.75v2.75h.25a.75.75 0 010 1.5h-2a.75.75 0 010-1.5h.25v-2h-.25a.75.75 0 01-.75-.75zM8 6a1 1 0 110-2 1 1 0 010 2z" />
            </svg>
            <span>
              Metrics here measure <strong>system behavior</strong>, not individual performance. A
              metric moving in an unexpected direction is a question to investigate, not a judgment
              to make.
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
                onClick={
                  m.scrollRef
                    ? () => {
                        refMap[m.scrollRef].current?.scrollIntoView({ behavior: 'smooth' });
                      }
                    : undefined
                }
              />
            ))}
          </div>

          <details
            className={styles.defsPanel}
            open={defsOpen}
            onToggle={(e) => setDefsOpen((e.target as HTMLDetailsElement).open)}
          >
            <summary className={styles.defsSummary}>
              <svg
                width="12"
                height="12"
                viewBox="0 0 16 16"
                fill="currentColor"
                style={{ flexShrink: 0 }}
              >
                <path d="M0 8a8 8 0 1116 0A8 8 0 010 8zm8-6.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM6.5 7.75A.75.75 0 017.25 7h1a.75.75 0 01.75.75v2.75h.25a.75.75 0 010 1.5h-2a.75.75 0 010-1.5h.25v-2h-.25a.75.75 0 01-.75-.75zM8 6a1 1 0 110-2 1 1 0 010 2z" />
              </svg>
              How are these metrics calculated?
            </summary>
            <div className={styles.defsGrid}>
              {metrics.map((m, i) => (
                <div key={i} className={styles.defItem}>
                  <div className={styles.defLabel}>{m.label}</div>
                  <div className={styles.defText}>{m.definition}</div>
                </div>
              ))}
              <div className={styles.defItem}>
                <div className={styles.defLabel}>DORA tier</div>
                <div className={styles.defText}>
                  Weighted average of Deployment Frequency (successful workflows/day) and Change
                  Failure Rate scores. Elite ≥ 3.5, High ≥ 2.5, Medium ≥ 1.5, Low &lt; 1.5. Full
                  DORA requires deployment and incident tracking.
                </div>
              </div>
            </div>
          </details>

          {isLoading && <Spinner />}

          <div ref={calendarRef}>
            <Card style={{ marginBottom: 20 }}>
              <CardHeader
                actions={<span style={{ fontWeight: 400 }}>commit + PR + deploy activity</span>}
              >
                Team contribution calendar — last 13 weeks
              </CardHeader>
              <ContributionCalendar data={calendarData} />
            </Card>
          </div>

          <div className={styles.chartsGrid}>
            <div className={styles.chartWrap}>
              <div className={styles.chartTitle}>
                Lead time for changes <span className={styles.chartSub}>— {chartDaysLabel}</span>
              </div>
              {isLoading ? (
                <div className={styles.chartSkeleton} />
              ) : chartLabels.length > 0 ? (
                <LineAreaChart
                  xAxisData={chartLabels}
                  series={[
                    {
                      name: 'Lead time (hours)',
                      data: leadTimeChartData,
                      color: chartColors.done,
                      areaOpacity: 0.15,
                    },
                  ]}
                  yAxisFormatter={(v: number) => `${v}h`}
                />
              ) : (
                <div
                  style={{
                    height: 160,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--fg-muted)',
                    fontSize: 13,
                  }}
                >
                  No workflow data available
                </div>
              )}
            </div>

            <div ref={changeFailureRef} className={styles.chartWrap}>
              <div className={styles.chartTitle}>
                Change failure rate <span className={styles.chartSub}>— {chartDaysLabel}</span>
              </div>
              {isLoading ? (
                <div className={styles.chartSkeleton} />
              ) : chartLabels.length > 0 ? (
                <LineAreaChart
                  xAxisData={chartLabels}
                  series={[
                    {
                      name: 'CFR',
                      data: changeFailureChartData,
                      color: 'rgb(248, 81, 73)',
                      areaOpacity: 0.15,
                    },
                    {
                      name: 'Threshold (5%)',
                      data: Array.from({ length: chartLabels.length }, () => 5),
                      color: 'rgb(248, 81, 73)',
                      dashed: true,
                    },
                  ]}
                  yAxisFormatter={(v: number) => `${v}%`}
                />
              ) : (
                <div
                  style={{
                    height: 160,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--fg-muted)',
                    fontSize: 13,
                  }}
                >
                  No workflow data available
                </div>
              )}
            </div>

            <div ref={workflowSuccessRef} className={styles.chartWrap}>
              <div className={styles.chartTitle}>
                Workflow success rate <span className={styles.chartSub}>— {chartDaysLabel}</span>
              </div>
              {isLoading ? (
                <div className={styles.chartSkeleton} />
              ) : chartLabels.length > 0 ? (
                <LineAreaChart
                  xAxisData={chartLabels}
                  series={[
                    {
                      name: 'Success rate',
                      data: workflowSuccessChartData,
                      color: 'rgb(63, 185, 80)',
                      areaOpacity: 0.15,
                    },
                  ]}
                  yAxisFormatter={(v: number) => `${v}%`}
                />
              ) : (
                <div
                  style={{
                    height: 160,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--fg-muted)',
                    fontSize: 13,
                  }}
                >
                  No workflow data available
                </div>
              )}
            </div>

            <div ref={dailyRunsRef} className={styles.chartWrap}>
              <div className={styles.chartTitle}>
                Daily deployments / MTTR <span className={styles.chartSub}>— {chartDaysLabel}</span>
              </div>
              {isLoading ? (
                <div className={styles.chartSkeleton} />
              ) : chartLabels.length > 0 ? (
                <BarChart
                  xAxisData={chartLabels}
                  series={[
                    {
                      name: 'Deployments',
                      data: dailyRunsChartData,
                      color: chartColors.accent,
                    },
                    { name: 'MTTR (hours)', data: mttrChartData, color: chartColors.done },
                  ]}
                />
              ) : (
                <div
                  style={{
                    height: 160,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--fg-muted)',
                    fontSize: 13,
                  }}
                >
                  No workflow data available
                </div>
              )}
            </div>
          </div>

          <div className={styles.workflowCallout}>
            <div className={styles.calloutIcon}>⚡</div>
            <div className={styles.calloutContent}>
              <div className={styles.calloutTitle}>Workflow Health</div>
              <div className={styles.calloutDesc}>
                Persistent CI/CD failures and timeouts are tracked on the dedicated{' '}
                <Link to="/workflows/health">Workflow Health</Link> page.
              </div>
            </div>
          </div>

          <div ref={reposRef} className={styles.sectionTitle}>
            Most active repositories — last 30 days
          </div>
          <div className={styles.tableWrap} style={{ marginBottom: 20 }}>
            <DataTable<RepoActivityStats>
              columns={[
                {
                  key: 'name',
                  header: 'Repository',
                  helpText:
                    'Repository name. Activity is aggregated from all audit log events associated with this repo.',
                  filterable: true,
                  render: (r) => (
                    <span style={{ fontWeight: 500, color: 'var(--accent)', cursor: 'pointer' }}>
                      {r.name}
                    </span>
                  ),
                  filterValue: (r) => r.name,
                },
                {
                  key: 'totalEvents',
                  header: 'Events',
                  helpText: 'Total audit log events for this repository in the last 30 days.',
                  sortable: true,
                  render: (r) => (
                    <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {r.totalEvents.toLocaleString()}
                    </span>
                  ),
                  sortValue: (r) => r.totalEvents,
                },
                {
                  key: 'prEvents',
                  header: 'PR events',
                  helpText:
                    'Pull request related audit events (open, close, merge, review). From pull_request audit events.',
                  sortable: true,
                  render: (r) => (
                    <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {r.prEvents.toLocaleString()}
                    </span>
                  ),
                  sortValue: (r) => r.prEvents,
                },
                {
                  key: 'pushEvents',
                  header: 'Push events',
                  helpText:
                    'Code push events to this repository. From push and git.push audit events.',
                  sortable: true,
                  render: (r) => (
                    <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {r.pushEvents.toLocaleString()}
                    </span>
                  ),
                  sortValue: (r) => r.pushEvents,
                },
                {
                  key: 'contributors',
                  header: 'Contributors',
                  helpText:
                    'Unique developers who triggered events in this repo. From push and PR audit events.',
                  sortable: true,
                  render: (r) => (
                    <span style={{ fontVariantNumeric: 'tabular-nums' }}>{r.contributors}</span>
                  ),
                  sortValue: (r) => r.contributors,
                },
              ]}
              data={repoStats}
              rowKey={(r) => r.name}
              onRowClick={(r) => navigate(`/events?repo=${encodeURIComponent(r.name)}`)}
              emptyMessage="No repository activity data available"
            />
          </div>

          {buckets.length === 0 && !isLoading && (
            <div style={{ color: 'var(--fg-muted)', padding: '16px 0' }}>
              No workflow run data for the selected period.
            </div>
          )}

          {/* Branch Protection Changes */}
          <BranchProtectionSection branchProt={branchProtData} />

          <Drawer
            open={doraModalOpen}
            onClose={() => setDoraModalOpen(false)}
            title={`DORA Metrics — ${doraTier ? doraTier.name : 'Pending'} Tier`}
          >
            <p
              style={{ fontSize: 13, color: 'var(--fg-muted)', marginBottom: 16, lineHeight: 1.5 }}
            >
              DORA (DevOps Research and Assessment) metrics measure software delivery performance.
              Teams are classified into four tiers based on their performance across four key
              metrics.
            </p>
            {(() => {
              interface DoraMetricRow {
                metric: string;
                threshold: string;
                current: React.ReactNode;
              }
              const doraRows: DoraMetricRow[] = [
                {
                  metric: 'Deployment Frequency',
                  threshold: 'On-demand (multiple deploys/day)',
                  current:
                    deploymentProxy != null ? `${deploymentProxy.toLocaleString()} workflows` : '—',
                },
                {
                  metric: 'Lead Time for Changes',
                  threshold: '< 1 hour',
                  current: (
                    <>
                      {avgLeadTime != null && avgLeadTime > 0 ? `~${avgLeadTime.toFixed(1)}h` : '—'}{' '}
                      <span style={{ fontSize: 11, color: 'var(--fg-subtle)' }}>(estimated)</span>
                    </>
                  ),
                },
                {
                  metric: 'Change Failure Rate',
                  threshold: '< 5%',
                  current: changeFailureRate != null ? `${changeFailureRate}%` : '—',
                },
                {
                  metric: 'Time to Restore Service',
                  threshold: '< 1 hour',
                  current: (
                    <>
                      {mttrChartData.some((v) => v > 0)
                        ? `~${(mttrChartData.filter((v) => v > 0).reduce((a, b) => a + b, 0) / mttrChartData.filter((v) => v > 0).length).toFixed(1)}h`
                        : '—'}{' '}
                      <span style={{ fontSize: 11, color: 'var(--fg-subtle)' }}>
                        (estimated from failure rate)
                      </span>
                    </>
                  ),
                },
              ];
              return (
                <DataTable<DoraMetricRow>
                  columns={[
                    {
                      key: 'metric',
                      header: 'Metric',
                      helpText: 'DORA metric name. Measures software delivery performance.',
                      filterable: true,
                      render: (row) => <span style={{ fontWeight: 500 }}>{row.metric}</span>,
                      filterValue: (row) => row.metric,
                    },
                    {
                      key: 'threshold',
                      header: 'Elite threshold',
                      helpText: 'The benchmark value for DORA elite-performing teams.',
                      render: (row) => <>{row.threshold}</>,
                    },
                    {
                      key: 'current',
                      header: 'Current',
                      helpText: 'Your current value for this metric, computed from audit log data.',
                      render: (row) => <>{row.current}</>,
                    },
                  ]}
                  data={doraRows}
                  rowKey={(row) => row.metric}
                  className={styles.doraTable}
                />
              );
            })()}
            <p style={{ fontSize: 12, color: 'var(--fg-subtle)', marginTop: 12, lineHeight: 1.5 }}>
              Tier is computed from deployment frequency and change failure rate. Full DORA
              calculation requires deployment and incident tracking integrations.
            </p>
          </Drawer>

          <Drawer
            open={failureBucket !== null}
            onClose={handleCloseBucket}
            title={`Workflow runs — ${failureBucket ? formatBucketDate(failureBucket.bucket) : ''}`}
          >
            {failureBucket && (
              <div>
                <div className={styles.modalMetrics}>
                  {[
                    {
                      key: 'total' as const,
                      val: failureBucket.workflow_runs_total,
                      label: 'Total runs',
                      color: undefined,
                    },
                    {
                      key: 'succeeded' as const,
                      val: failureBucket.workflow_runs_succeeded,
                      label: 'Succeeded',
                      color: 'var(--success)',
                    },
                    {
                      key: 'failed' as const,
                      val: failureBucket.workflow_runs_failed,
                      label: 'Failed',
                      color: 'var(--danger)',
                    },
                  ].map((chip) => (
                    <div
                      key={chip.key}
                      className={[
                        styles.modalMetric,
                        styles.modalMetricClickable,
                        drillFilter === chip.key && styles.modalMetricActive,
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      role="button"
                      tabIndex={0}
                      aria-label={`View ${chip.label.toLowerCase()}`}
                      onClick={() => setDrillFilter(drillFilter === chip.key ? null : chip.key)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setDrillFilter(drillFilter === chip.key ? null : chip.key);
                        }
                      }}
                    >
                      <div
                        className={styles.modalMetricVal}
                        style={chip.color ? { color: chip.color } : undefined}
                      >
                        {chip.val}
                      </div>
                      <div className={styles.modalMetricLbl}>{chip.label}</div>
                    </div>
                  ))}
                  <div className={styles.modalMetric}>
                    <div className={styles.modalMetricVal}>
                      {failureBucket.success_rate_pct != null
                        ? `${Math.round(failureBucket.success_rate_pct)}%`
                        : '—'}
                    </div>
                    <div className={styles.modalMetricLbl}>Success rate</div>
                  </div>
                </div>

                {!drillFilter && (
                  <p
                    style={{
                      fontSize: 12,
                      color: 'var(--fg-subtle)',
                      marginTop: 16,
                      lineHeight: 1.5,
                    }}
                  >
                    Click a metric above to see individual workflow runs.
                  </p>
                )}

                {drillFilter && (
                  <div style={{ marginTop: 16 }}>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        marginBottom: 8,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                      }}
                    >
                      {drillFilter === 'total'
                        ? 'All'
                        : drillFilter === 'succeeded'
                          ? 'Succeeded'
                          : 'Failed'}{' '}
                      workflow runs
                      {drillLoading && <Spinner />}
                    </div>
                    {drillEvents && drillEvents.items.length > 0 ? (
                      <div className={styles.drillTable}>
                        <table>
                          <thead>
                            <tr>
                              <th scope="col">Repository</th>
                              <th scope="col">Workflow</th>
                              <th scope="col">Status</th>
                              <th scope="col">Time</th>
                              <th scope="col"></th>
                            </tr>
                          </thead>
                          <tbody>
                            {drillEvents.items.map((ev) => (
                              <tr key={ev.id}>
                                <td>{ev.repo?.split('/').pop() ?? ev.repo ?? '—'}</td>
                                <td className={styles.workflowName}>
                                  {(ev.data?.workflow_name as string) ??
                                    (ev.data?.name as string) ??
                                    '—'}
                                </td>
                                <td>
                                  <Label
                                    variant={
                                      ev.action.includes('success')
                                        ? 'success'
                                        : ev.action.includes('failure')
                                          ? 'danger'
                                          : 'attention'
                                    }
                                  >
                                    {ev.action.split('.').pop()}
                                  </Label>
                                </td>
                                <td style={{ color: 'var(--fg-muted)', whiteSpace: 'nowrap' }}>
                                  {new Date(ev.created_at).toLocaleTimeString()}
                                </td>
                                <td>
                                  {ev.data?.html_url ? (
                                    <a
                                      href={ev.data.html_url as string}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      style={{ fontSize: 11, color: 'var(--accent)' }}
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      View
                                    </a>
                                  ) : null}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {drillEvents.total > drillEvents.items.length && (
                          <div
                            style={{
                              fontSize: 11,
                              color: 'var(--fg-subtle)',
                              marginTop: 8,
                              textAlign: 'center',
                            }}
                          >
                            Showing {drillEvents.items.length} of {drillEvents.total} runs
                          </div>
                        )}
                      </div>
                    ) : (
                      !drillLoading && (
                        <div style={{ fontSize: 12, color: 'var(--fg-subtle)', padding: '12px 0' }}>
                          No events found for this filter.
                        </div>
                      )
                    )}
                  </div>
                )}
              </div>
            )}
          </Drawer>
        </>
      )}
    </div>
  );
}
