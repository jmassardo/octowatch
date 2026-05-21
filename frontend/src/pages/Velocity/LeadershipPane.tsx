import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getLeadershipSummary, getTeamComparison, getShippingCadence } from '../../api/velocity';
import type { MetricWithTrend, TeamMetricsItem, CadenceDayItem } from '../../api/velocity';
import { MetricCard } from '../../components/primitives/MetricCard';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { BarChart } from '../../components/charts/BarChart';
import { ContributionCalendar } from '../../components/charts/ContributionCalendar';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Velocity.module.css';

type DoraPeriod = 30 | 90 | 180;
type ComparisonMetric = 'deploy_freq' | 'lead_time' | 'cfr' | 'mttr';

interface CalendarDay {
  date: string;
  level: 0 | 1 | 2 | 3 | 4;
  alert?: boolean;
}

const PERIOD_OPTIONS: { value: DoraPeriod; label: string }[] = [
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
  { value: 180, label: '180 days' },
];

const METRIC_OPTIONS: { value: ComparisonMetric; label: string }[] = [
  { value: 'deploy_freq', label: 'Deploy Frequency' },
  { value: 'lead_time', label: 'Lead Time' },
  { value: 'cfr', label: 'Change Failure Rate' },
  { value: 'mttr', label: 'MTTR' },
];

const TIER_COLORS: Record<string, string> = {
  elite: 'var(--success)',
  high: 'var(--accent)',
  medium: 'var(--attention)',
  low: 'var(--danger)',
};

function formatTrend(trend: number): string {
  if (trend === 0) return '0%';
  const sign = trend > 0 ? '+' : '';
  return `${sign}${trend}%`;
}

function trendDirection(trend: number, invertBetter: boolean = false): 'up' | 'down' | 'neutral' {
  if (trend === 0) return 'neutral';
  if (invertBetter) {
    // For metrics where lower is better (lead time, CFR, MTTR)
    return trend < 0 ? 'up' : 'down';
  }
  return trend > 0 ? 'up' : 'down';
}

function classificationBadge(classification: string): string {
  const labels: Record<string, string> = {
    elite: '★ Elite',
    high: '▲ High',
    medium: '◆ Medium',
    low: '▼ Low',
    'n/a': '',
  };
  return labels[classification] ?? classification;
}

function buildMetricCards(
  summary: {
    deployment_frequency: MetricWithTrend;
    lead_time: MetricWithTrend;
    change_failure_rate: MetricWithTrend;
    mttr: MetricWithTrend;
    pr_throughput: MetricWithTrend;
    active_contributors: MetricWithTrend;
  } | null,
) {
  if (!summary) {
    return [
      { value: '—', label: 'Deployment Frequency', delta: 'Loading…', dir: 'neutral' as const },
      { value: '—', label: 'Lead Time for Changes', delta: 'Loading…', dir: 'neutral' as const },
      { value: '—', label: 'Change Failure Rate', delta: 'Loading…', dir: 'neutral' as const },
      { value: '—', label: 'Mean Time to Recovery', delta: 'Loading…', dir: 'neutral' as const },
      { value: '—', label: 'PR Throughput', delta: 'Loading…', dir: 'neutral' as const },
      { value: '—', label: 'Active Contributors', delta: 'Loading…', dir: 'neutral' as const },
    ];
  }

  const {
    deployment_frequency,
    lead_time,
    change_failure_rate,
    mttr,
    pr_throughput,
    active_contributors,
  } = summary;

  return [
    {
      value: `${deployment_frequency.value}/day`,
      label: 'Deployment Frequency',
      delta: `${formatTrend(deployment_frequency.trend_pct)} vs prev · ${classificationBadge(deployment_frequency.classification)}`,
      dir: trendDirection(deployment_frequency.trend_pct),
    },
    {
      value: `${lead_time.value}h`,
      label: 'Lead Time for Changes',
      delta: `${formatTrend(lead_time.trend_pct)} vs prev · ${classificationBadge(lead_time.classification)}`,
      dir: trendDirection(lead_time.trend_pct, true),
    },
    {
      value: `${change_failure_rate.value}%`,
      label: 'Change Failure Rate',
      delta: `${formatTrend(change_failure_rate.trend_pct)} vs prev · ${classificationBadge(change_failure_rate.classification)}`,
      dir: trendDirection(change_failure_rate.trend_pct, true),
    },
    {
      value: `${mttr.value}h`,
      label: 'Mean Time to Recovery',
      delta: `${formatTrend(mttr.trend_pct)} vs prev · ${classificationBadge(mttr.classification)}`,
      dir: trendDirection(mttr.trend_pct, true),
    },
    {
      value: `${pr_throughput.value}/wk`,
      label: 'PR Throughput',
      delta: `${formatTrend(pr_throughput.trend_pct)} vs prev`,
      dir: trendDirection(pr_throughput.trend_pct),
    },
    {
      value: `${active_contributors.value}/wk`,
      label: 'Active Contributors',
      delta: `${formatTrend(active_contributors.trend_pct)} vs prev`,
      dir: trendDirection(active_contributors.trend_pct),
    },
  ];
}

function buildDoraChartData(
  summary: {
    deployment_frequency: MetricWithTrend;
    lead_time: MetricWithTrend;
    change_failure_rate: MetricWithTrend;
    mttr: MetricWithTrend;
    period_days: number;
  } | null,
  period: DoraPeriod,
): {
  labels: string[];
  deployFreq: number[];
  leadTime: number[];
  cfr: number[];
  mttrData: number[];
} {
  if (!summary) {
    return { labels: [], deployFreq: [], leadTime: [], cfr: [], mttrData: [] };
  }

  // Generate synthetic time series from current + previous period values
  // Split the period into weekly buckets and interpolate
  const weeks = Math.max(Math.floor(period / 7), 2);
  const labels: string[] = [];
  const deployFreq: number[] = [];
  const leadTime: number[] = [];
  const cfr: number[] = [];
  const mttrData: number[] = [];

  const now = new Date();
  for (let i = weeks - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i * 7);
    labels.push(`${d.getMonth() + 1}/${d.getDate()}`);

    // Linear interpolation from previous to current values across the period
    const progress = 1 - i / (weeks - 1);
    deployFreq.push(
      +(
        summary.deployment_frequency.previous_value +
        (summary.deployment_frequency.value - summary.deployment_frequency.previous_value) *
          progress
      ).toFixed(2),
    );
    leadTime.push(
      +(
        summary.lead_time.previous_value +
        (summary.lead_time.value - summary.lead_time.previous_value) * progress
      ).toFixed(1),
    );
    cfr.push(
      +(
        summary.change_failure_rate.previous_value +
        (summary.change_failure_rate.value - summary.change_failure_rate.previous_value) * progress
      ).toFixed(1),
    );
    mttrData.push(
      +(
        summary.mttr.previous_value +
        (summary.mttr.value - summary.mttr.previous_value) * progress
      ).toFixed(1),
    );
  }

  return { labels, deployFreq, leadTime, cfr, mttrData };
}

function buildTeamChartData(teams: TeamMetricsItem[]): {
  labels: string[];
  values: number[];
  colors: string[];
} {
  const sorted = [...teams].sort((a, b) => b.value - a.value).slice(0, 10);
  return {
    labels: sorted.map((t) => t.team),
    values: sorted.map((t) => t.value),
    colors: sorted.map((t) => TIER_COLORS[t.classification] ?? 'var(--accent)'),
  };
}

function buildCadenceCalendarData(items: CadenceDayItem[]): CalendarDay[] {
  const values = items.map((i) => i.deployments + i.merges + i.reviews);
  const maxCount = Math.max(...values, 1);

  return items.map((item) => {
    const count = item.deployments + item.merges + item.reviews;
    let level: 0 | 1 | 2 | 3 | 4;
    if (count === 0) level = 0;
    else if (count <= maxCount * 0.25) level = 1;
    else if (count <= maxCount * 0.5) level = 2;
    else if (count <= maxCount * 0.75) level = 3;
    else level = 4;
    return { date: item.date, level };
  });
}

function metricUnit(metric: ComparisonMetric): string {
  switch (metric) {
    case 'deploy_freq':
      return '/day';
    case 'lead_time':
      return 'h';
    case 'cfr':
      return '%';
    case 'mttr':
      return 'h';
  }
}

export function LeadershipPane() {
  const [period, setPeriod] = useState<DoraPeriod>(30);
  const [comparisonMetric, setComparisonMetric] = useState<ComparisonMetric>('deploy_freq');

  const {
    data: summaryData,
    isLoading: summaryLoading,
    isError: summaryError,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['velocity', 'leadership-summary', period],
    queryFn: () => getLeadershipSummary({ period }),
    staleTime: 60_000,
  });

  const {
    data: teamData,
    isLoading: teamLoading,
    isError: teamError,
    refetch: refetchTeams,
  } = useQuery({
    queryKey: ['velocity', 'team-comparison', period, comparisonMetric],
    queryFn: () => getTeamComparison({ period, metric: comparisonMetric }),
    staleTime: 60_000,
  });

  const {
    data: cadenceData,
    isLoading: cadenceLoading,
    isError: cadenceError,
    refetch: refetchCadence,
  } = useQuery({
    queryKey: ['velocity', 'shipping-cadence', period],
    queryFn: () => getShippingCadence({ period }),
    staleTime: 60_000,
  });

  const metricCards = useMemo(() => buildMetricCards(summaryData ?? null), [summaryData]);

  const doraChart = useMemo(
    () => buildDoraChartData(summaryData ?? null, period),
    [summaryData, period],
  );

  const teamChart = useMemo(
    () => (teamData?.items ? buildTeamChartData(teamData.items) : null),
    [teamData],
  );

  const cadenceCalendar = useMemo(
    () => (cadenceData?.items ? buildCadenceCalendarData(cadenceData.items) : undefined),
    [cadenceData],
  );

  const isLoading = summaryLoading || teamLoading || cadenceLoading;
  const isError = summaryError || teamError || cadenceError;

  const handleRefetch = () => {
    refetchSummary();
    refetchTeams();
    refetchCadence();
  };

  return (
    <div>
      {/* Period selector */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 16,
        }}
      >
        <span style={{ fontSize: 12, color: 'var(--fg-muted)', fontWeight: 500 }}>Period:</span>
        {PERIOD_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setPeriod(opt.value)}
            style={{
              padding: '4px 12px',
              borderRadius: 4,
              border: '1px solid var(--border)',
              background: period === opt.value ? 'var(--accent)' : 'var(--canvas-subtle)',
              color: period === opt.value ? 'var(--fg-on-emphasis)' : 'var(--fg-muted)',
              fontSize: 12,
              cursor: 'pointer',
              fontWeight: period === opt.value ? 600 : 400,
            }}
          >
            {opt.label}
          </button>
        ))}
        {isLoading && <Spinner size={14} />}
      </div>

      {isError && (
        <ErrorBanner message="Failed to load leadership metrics" onRetry={handleRefetch} />
      )}

      {/* Executive Summary Strip */}
      <div className={styles.metricStrip}>
        {metricCards.map((m, i) => (
          <MetricCard key={i} value={m.value} label={m.label} delta={m.delta} deltaDir={m.dir} />
        ))}
      </div>

      {/* DORA Metrics Over Time */}
      <div className={styles.chartsGrid}>
        <div className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Deployment Frequency &amp; Lead Time
            <span className={styles.chartSub}> — {period}d</span>
          </div>
          {doraChart.labels.length > 0 ? (
            <LineAreaChart
              xAxisData={doraChart.labels}
              series={[
                {
                  name: 'Deploy Freq (/day)',
                  data: doraChart.deployFreq,
                  color: 'var(--success)',
                  areaOpacity: 0.1,
                },
                {
                  name: 'Lead Time (h)',
                  data: doraChart.leadTime,
                  color: 'var(--accent)',
                  dashed: true,
                },
              ]}
              height={200}
            />
          ) : (
            <div className={styles.chartSkeleton} />
          )}
        </div>

        <div className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Change Failure Rate &amp; MTTR
            <span className={styles.chartSub}> — {period}d</span>
          </div>
          {doraChart.labels.length > 0 ? (
            <LineAreaChart
              xAxisData={doraChart.labels}
              series={[
                {
                  name: 'CFR (%)',
                  data: doraChart.cfr,
                  color: 'var(--danger)',
                  areaOpacity: 0.1,
                },
                {
                  name: 'MTTR (h)',
                  data: doraChart.mttrData,
                  color: 'var(--attention)',
                  dashed: true,
                },
              ]}
              height={200}
            />
          ) : (
            <div className={styles.chartSkeleton} />
          )}
        </div>
      </div>

      {/* Team Comparison */}
      <div style={{ marginBottom: 20 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 12,
          }}
        >
          <div
            className={styles.sectionTitle}
            style={{ marginBottom: 0, borderBottom: 'none', paddingBottom: 0 }}
          >
            Team Comparison
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {METRIC_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setComparisonMetric(opt.value)}
                style={{
                  padding: '3px 10px',
                  borderRadius: 4,
                  border: '1px solid var(--border)',
                  background:
                    comparisonMetric === opt.value ? 'var(--accent)' : 'var(--canvas-subtle)',
                  color:
                    comparisonMetric === opt.value ? 'var(--fg-on-emphasis)' : 'var(--fg-muted)',
                  fontSize: 11,
                  cursor: 'pointer',
                  fontWeight: comparisonMetric === opt.value ? 600 : 400,
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        <div className={styles.chartWrap}>
          {teamChart && teamChart.labels.length > 0 ? (
            <BarChart
              xAxisData={teamChart.labels}
              series={[
                {
                  name: `${METRIC_OPTIONS.find((o) => o.value === comparisonMetric)?.label ?? comparisonMetric} (${metricUnit(comparisonMetric)})`,
                  data: teamChart.values,
                  color: teamChart.colors[0],
                },
              ]}
              height={220}
            />
          ) : teamLoading ? (
            <div className={styles.chartSkeleton} />
          ) : (
            <div
              style={{
                height: 220,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--fg-muted)',
                fontSize: 13,
              }}
            >
              No team data available
            </div>
          )}
        </div>
      </div>

      {/* Shipping Cadence */}
      <div>
        <div className={styles.sectionTitle}>
          Shipping Cadence
          <span style={{ fontWeight: 400, fontSize: 12, color: 'var(--fg-muted)' }}>
            {' '}
            — deployments + merges + reviews per day
          </span>
        </div>
        <div className={styles.chartWrap}>
          {cadenceCalendar ? (
            <ContributionCalendar data={cadenceCalendar} />
          ) : cadenceLoading ? (
            <div className={styles.chartSkeleton} />
          ) : cadenceError ? (
            <div
              style={{
                padding: 20,
                textAlign: 'center',
                color: 'var(--fg-muted)',
                fontSize: 13,
              }}
            >
              Failed to load cadence data
            </div>
          ) : (
            <ContributionCalendar />
          )}
        </div>
      </div>
    </div>
  );
}
