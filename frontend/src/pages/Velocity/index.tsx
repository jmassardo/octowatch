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

/* ── Static demo / placeholder data for velocity charts ─────────────── */

const CHART_LABELS = Array.from({ length: 14 }, (_, i) => {
  const d = new Date();
  d.setDate(d.getDate() - 13 + i);
  return `${d.getMonth() + 1}/${d.getDate()}`;
});

const LEAD_TIME_MEDIAN = [4.2, 3.8, 5.1, 3.5, 4.0, 6.2, 5.5, 3.9, 4.8, 3.6, 4.1, 3.3, 5.0, 4.4];
const LEAD_TIME_P90 = [8.1, 7.5, 9.3, 6.8, 7.2, 11.4, 10.1, 7.0, 8.9, 6.5, 7.8, 6.1, 9.2, 8.0];
const CHANGE_FAILURE = [3.2, 2.8, 4.1, 5.5, 3.0, 2.1, 6.3, 4.8, 3.5, 2.9, 1.8, 3.4, 2.5, 3.1];
const WORKFLOW_SUCCESS_DEMO = [96.2, 95.8, 97.1, 94.5, 96.0, 93.8, 95.5, 97.9, 96.8, 98.1, 97.4, 95.3, 96.0, 97.5];
const DAILY_DEPLOYS = [5, 8, 3, 7, 12, 6, 4, 9, 11, 7, 5, 8, 10, 6];

const ACTIVE_REPOS = [
  { name: 'octowatch/frontend', commits: 142, prs: 28, cfr: '2.1%', mttr: '0.8 h', contributors: 6 },
  { name: 'octowatch/backend', commits: 118, prs: 22, cfr: '3.4%', mttr: '1.2 h', contributors: 5 },
  { name: 'octowatch/infra', commits: 67, prs: 14, cfr: '1.5%', mttr: '0.5 h', contributors: 3 },
  { name: 'octowatch/docs', commits: 45, prs: 11, cfr: '0.0%', mttr: '—', contributors: 4 },
  { name: 'octowatch/cli', commits: 38, prs: 9, cfr: '5.2%', mttr: '2.1 h', contributors: 2 },
];

export function VelocityPage() {
  const { data: actionsData, isLoading, isError, refetch } = useQuery({
    queryKey: ['reports', 'actions-volume'],
    queryFn: () => getActionsVolumeReport({ window_days: 30, granularity: 'daily' }),
  });

  const { data: prEvents } = useQuery({
    queryKey: ['events', 'pr-events'],
    queryFn: () => listEvents({ action: 'pull_request', page_size: 500, sort: 'created_at_desc' }),
  });

  const buckets = (actionsData?.data ?? []) as unknown as ActionsVolumeBucket[];

  // Aggregate totals from actions volume data
  const totalRuns = buckets.reduce((sum, b) => sum + (b.workflow_runs_total ?? 0), 0);
  const totalSucceeded = buckets.reduce((sum, b) => sum + (b.workflow_runs_succeeded ?? 0), 0);
  const overallSuccessRate = totalRuns > 0 ? ((totalSucceeded / totalRuns) * 100).toFixed(1) : null;

  const prMerged = prEvents?.total ?? null;

  const metrics = [
    { value: prMerged != null ? prMerged.toLocaleString() : '—', label: 'PRs merged (30d)', delta: 'last 30 days', dir: 'neutral' as const },
    { value: '4.2 h', label: 'Lead time for changes', delta: '↓ 12% vs prior', dir: 'up' as const },
    { value: '2.8 h', label: 'PR cycle time (median)', delta: 'last 30 days', dir: 'neutral' as const },
    { value: '3.1%', label: 'Change failure rate', delta: '< 5% target', dir: 'up' as const },
    { value: '6.4 / d', label: 'Deployments (30d)', delta: '↑ 8% vs prior', dir: 'up' as const },
    { value: overallSuccessRate != null ? `${overallSuccessRate}%` : '—', label: 'Workflow success', delta: '30-day average', dir: overallSuccessRate != null && parseFloat(overallSuccessRate) >= 90 ? 'up' as const : 'down' as const },
    { value: '12', label: 'WIP (items in flight)', delta: 'across all repos', dir: 'neutral' as const },
    { value: '74%', label: 'Planned work ratio', delta: 'vs unplanned', dir: 'neutral' as const },
  ];

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
          <MetricCard key={i} value={m.value} label={m.label} delta={m.delta} deltaDir={m.dir} />
        ))}
      </div>

      {isLoading && <Spinner />}

      <Card style={{ marginBottom: 20 }}>
        <CardHeader actions={<span style={{ fontWeight: 400 }}>commit + PR + deploy activity</span>}>
          Team contribution calendar — last 13 weeks
        </CardHeader>
        <ContributionCalendar />
      </Card>

      <div className={styles.chartsGrid}>
        <div className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Lead time for changes <span className={styles.chartSub}>— 14 days</span>
          </div>
          <LineAreaChart
            xAxisData={CHART_LABELS}
            series={[
              { name: 'Median', data: LEAD_TIME_MEDIAN, color: 'rgb(88, 166, 255)', areaOpacity: 0.15 },
              { name: 'P90', data: LEAD_TIME_P90, color: 'rgb(88, 166, 255)', dashed: true },
            ]}
            yAxisFormatter={(v: number) => `${v}h`}
          />
        </div>

        <div className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Change failure rate <span className={styles.chartSub}>— 14 days</span>
          </div>
          <LineAreaChart
            xAxisData={CHART_LABELS}
            series={[
              { name: 'CFR', data: CHANGE_FAILURE, color: 'rgb(248, 81, 73)', areaOpacity: 0.15 },
              { name: 'Threshold (5%)', data: Array.from({ length: 14 }, () => 5), color: 'rgb(248, 81, 73)', dashed: true },
            ]}
            yAxisFormatter={(v: number) => `${v}%`}
          />
        </div>

        <div className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Workflow success rate <span className={styles.chartSub}>— 14 days</span>
          </div>
          <LineAreaChart
            xAxisData={CHART_LABELS}
            series={[
              { name: 'Success rate', data: WORKFLOW_SUCCESS_DEMO, color: 'rgb(63, 185, 80)', areaOpacity: 0.15 },
            ]}
            yAxisFormatter={(v: number) => `${v}%`}
          />
        </div>

        <div className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Daily deployments <span className={styles.chartSub}>— 14 days</span>
          </div>
          <BarChart
            xAxisData={CHART_LABELS}
            series={[
              { name: 'Deployments', data: DAILY_DEPLOYS, color: '#58a6ff' },
            ]}
          />
        </div>
      </div>

      {recentFailingBuckets.length > 0 && (
        <>
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
        </>
      )}

      <div className={styles.sectionTitle}>Most active repositories — last 30 days</div>
      <div className={styles.tableWrap} style={{ marginBottom: 20 }}>
        <table>
          <thead>
            <tr>
              <th>Repository</th>
              <th>Commits</th>
              <th>PRs merged</th>
              <th>Change failure rate</th>
              <th>MTTR</th>
              <th>Contributors</th>
            </tr>
          </thead>
          <tbody>
            {ACTIVE_REPOS.map((r) => (
              <tr key={r.name}>
                <td style={{ fontWeight: 500 }}>{r.name}</td>
                <td style={{ fontVariantNumeric: 'tabular-nums' }}>{r.commits}</td>
                <td style={{ fontVariantNumeric: 'tabular-nums' }}>{r.prs}</td>
                <td>{r.cfr}</td>
                <td>{r.mttr}</td>
                <td style={{ fontVariantNumeric: 'tabular-nums' }}>{r.contributors}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {buckets.length === 0 && !isLoading && (
        <div style={{ color: 'var(--fg-muted)', padding: '16px 0' }}>No workflow run data for the selected period.</div>
      )}
    </div>
  );
}
