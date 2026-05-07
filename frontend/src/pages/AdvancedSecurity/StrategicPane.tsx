import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SkeletonCard } from '../../components/common/SkeletonCard';
import { SkeletonChart } from '../../components/common/SkeletonChart';
import { RadialGauge } from '../../components/charts/RadialGauge';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { BarChart } from '../../components/charts/BarChart';
import {
  getMttrTrends,
  getCoverageGrowth,
  getAlertAging,
  getSecurityScore,
  type OldestAlert,
  type UncoveredRepo,
  type CoverageGrowthResponse,
  type AlertAgingResponse,
  type SecurityScoreResponse,
  type MttrTrendsResponse,
} from '../../api/healthSignals';
import { formatRelativeShort } from '../../utils/dates';
import styles from './AdvancedSecurity.module.css';

/* ── Helpers ── */

function trendArrow(pct: number): { symbol: string; color: string } {
  if (pct < -5) return { symbol: '↓', color: 'var(--success, #3fb950)' };
  if (pct > 5) return { symbol: '↑', color: 'var(--danger, #f85149)' };
  return { symbol: '→', color: 'var(--fg-muted, #8b949e)' };
}

function formatHours(hours: number): string {
  if (hours < 1) return '<1h';
  if (hours < 24) return `${Math.round(hours)}h`;
  const days = Math.round(hours / 24);
  return `${days}d`;
}

function scoreColor(score: number): string {
  if (score >= 80) return 'var(--success, #3fb950)';
  if (score >= 60) return 'var(--attention, #d29922)';
  return 'var(--danger, #f85149)';
}

const FEATURE_NAMES = ['ghas', 'code_scanning', 'secret_scanning', 'dependabot', 'push_protection'];

type PeriodKey = '7d' | '30d' | '90d';

/* ── Main Component ── */

export function StrategicPane() {
  const [mttrPeriod, setMttrPeriod] = useState<PeriodKey>('30d');
  const [mttrSeverity, setMttrSeverity] = useState<string | undefined>(undefined);

  const scoreQuery = useQuery({
    queryKey: ['strategic-security-score'],
    queryFn: () => getSecurityScore(),
  });

  const mttrQuery = useQuery({
    queryKey: ['strategic-mttr', mttrPeriod, mttrSeverity],
    queryFn: () => getMttrTrends(mttrPeriod, mttrSeverity),
  });

  const coverageQuery = useQuery({
    queryKey: ['strategic-coverage'],
    queryFn: () => getCoverageGrowth('90d'),
  });

  const agingQuery = useQuery({
    queryKey: ['strategic-aging'],
    queryFn: () => getAlertAging(),
  });

  const isLoading =
    scoreQuery.isLoading || mttrQuery.isLoading || coverageQuery.isLoading || agingQuery.isLoading;
  const error = scoreQuery.error || mttrQuery.error || coverageQuery.error || agingQuery.error;

  if (error) {
    return <ErrorBanner message={String(error)} />;
  }

  if (isLoading) {
    return (
      <div>
        <div className={styles.cardGrid}>
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
        <SkeletonChart />
      </div>
    );
  }

  const score = scoreQuery.data;
  const mttr = mttrQuery.data;
  const coverage = coverageQuery.data;
  const aging = agingQuery.data;

  return (
    <div>
      {/* ── Executive Summary Cards ── */}
      <ExecutiveSummary score={score} mttr={mttr} coverage={coverage} aging={aging} />

      {/* ── Security Score Detail ── */}
      {score && <SecurityScoreSection score={score} />}

      {/* ── MTTR Trend Analysis ── */}
      {mttr && (
        <MttrSection
          mttr={mttr}
          period={mttrPeriod}
          setPeriod={setMttrPeriod}
          severity={mttrSeverity}
          setSeverity={setMttrSeverity}
        />
      )}

      {/* ── Coverage Growth ── */}
      {coverage && <CoverageSection coverage={coverage} />}

      {/* ── Alert Aging & Burndown ── */}
      {aging && <AgingSection aging={aging} />}
    </div>
  );
}

/* ── Executive Summary ── */

interface ExecutiveSummaryProps {
  score: SecurityScoreResponse | undefined;
  mttr: MttrTrendsResponse | undefined;
  coverage: CoverageGrowthResponse | undefined;
  aging: AlertAgingResponse | undefined;
}

function ExecutiveSummary({ score, mttr, coverage, aging }: ExecutiveSummaryProps) {
  const mttrTrend = mttr ? trendArrow(mttr.trend_pct) : null;
  const totalCritHigh = aging
    ? aging.age_buckets.reduce((sum, b) => sum + b.critical_count + b.high_count, 0)
    : 0;

  const avgAge = useMemo(() => {
    if (!aging) return 0;
    const totalCount = aging.age_buckets.reduce((sum, b) => sum + b.total_count, 0);
    if (totalCount === 0) return 0;
    const midpoints = [3.5, 18.5, 60, 120];
    const weightedSum = aging.age_buckets.reduce(
      (sum, b, i) => sum + b.total_count * midpoints[i],
      0,
    );
    return Math.round(weightedSum / totalCount);
  }, [aging]);

  const coveragePct = useMemo(() => {
    if (!coverage) return 0;
    const fc = coverage.feature_coverage ?? {};
    const featurePcts = FEATURE_NAMES.map((f) => fc[f]?.pct ?? 0);
    if (featurePcts.length === 0) return 0;
    return Math.round(featurePcts.reduce((a, b) => a + b, 0) / featurePcts.length);
  }, [coverage]);

  return (
    <div className={styles.cardGrid}>
      <MetricCard
        value={score ? `${Math.round(score.score)}` : '—'}
        label="Security Score"
        helpText="Composite score (0-100) based on coverage, MTTR, alert volume, aging, and trends"
      />
      <MetricCard
        value={mttr ? formatHours(mttr.current_mttr_hours) : '—'}
        label="MTTR"
        delta={
          mttrTrend
            ? `${mttrTrend.symbol} ${Math.abs(Math.round(mttr?.trend_pct ?? 0))}%`
            : undefined
        }
        deltaDir={
          mttr ? (mttr.trend_pct < -5 ? 'down' : mttr.trend_pct > 5 ? 'up' : 'neutral') : 'neutral'
        }
        helpText="Mean Time to Remediate across all alert types"
      />
      <MetricCard
        value={String(totalCritHigh)}
        label="Critical/High Open"
        helpText="Total open critical and high severity alerts"
      />
      <MetricCard
        value={`${coveragePct}%`}
        label="GHAS Coverage"
        helpText="Average coverage across all GHAS features"
      />
      <MetricCard
        value={avgAge > 0 ? `${avgAge}d` : '—'}
        label="Avg Alert Age"
        helpText="Average age of open alerts in days"
      />
    </div>
  );
}

/* ── Security Score Section ── */

function SecurityScoreSection({ score }: { score: SecurityScoreResponse }) {
  const radarData = useMemo(() => {
    const labels = score.components.map((c) => c.name);
    const values = score.components.map((c) => c.score);
    return { labels, values };
  }, [score.components]);

  return (
    <div className={styles.trendSection}>
      <div className={styles.trendHeader}>
        <span className={styles.trendTitle}>Security Score Breakdown</span>
      </div>
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <RadialGauge
          value={score.score}
          label="Overall Score"
          color={scoreColor(score.score)}
          size={180}
        />
        <div style={{ flex: 1, minWidth: 280 }}>
          <BarChart
            title="Component Scores"
            xAxisData={radarData.labels}
            series={[
              {
                name: 'Score',
                data: radarData.values,
                color: scoreColor(score.score),
              },
            ]}
            height={180}
          />
        </div>
      </div>

      {score.suggestions.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              marginBottom: 8,
              color: 'var(--fg-default)',
            }}
          >
            What&apos;s Dragging Your Score Down
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {score.suggestions.map((s, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  gap: 8,
                  fontSize: 12,
                  color: 'var(--fg-muted)',
                  alignItems: 'baseline',
                }}
              >
                <span
                  style={{
                    background: 'var(--danger)',
                    color: '#fff',
                    borderRadius: 4,
                    padding: '1px 6px',
                    fontSize: 10,
                    fontWeight: 600,
                    flexShrink: 0,
                  }}
                >
                  {i + 1}
                </span>
                <span>
                  <strong>{s.name}:</strong> {s.suggestion}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── MTTR Section ── */

interface MttrSectionProps {
  mttr: MttrTrendsResponse;
  period: PeriodKey;
  setPeriod: (p: PeriodKey) => void;
  severity: string | undefined;
  setSeverity: (s: string | undefined) => void;
}

function MttrSection({ mttr, period, setPeriod, severity, setSeverity }: MttrSectionProps) {
  const arrow = trendArrow(mttr.trend_pct);
  const periods: PeriodKey[] = ['7d', '30d', '90d'];

  const timeSeriesData = useMemo(
    () => ({
      dates: mttr.time_series.map((p) => p.date),
      values: mttr.time_series.map((p) => Number(p.mttr_hours)),
    }),
    [mttr.time_series],
  );

  return (
    <div className={styles.trendSection}>
      <div className={styles.trendHeader}>
        <span className={styles.trendTitle}>
          MTTR Trend{' '}
          <span style={{ color: arrow.color, fontWeight: 700 }}>
            {arrow.symbol} {Math.abs(Math.round(mttr.trend_pct))}%
          </span>
        </span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select
            className={styles.filterSelect}
            value={severity ?? ''}
            onChange={(e) => setSeverity(e.target.value || undefined)}
            aria-label="Filter by severity"
          >
            <option value="">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <div className={styles.periodToggle}>
            {periods.map((p) => (
              <button
                key={p}
                className={`${styles.periodBtn} ${period === p ? styles.periodBtnActive : ''}`}
                onClick={() => setPeriod(p)}
                aria-pressed={period === p}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      </div>

      <LineAreaChart
        title="MTTR Over Time (hours)"
        xAxisData={timeSeriesData.dates}
        series={[
          {
            name: 'MTTR (hours)',
            data: timeSeriesData.values,
            color: '#58a6ff',
            areaOpacity: 0.15,
          },
        ]}
        height={200}
        yAxisFormatter={(v: number) => formatHours(v)}
      />

      <div style={{ marginTop: 16 }}>
        <BarChart
          title="MTTR by Tool"
          xAxisData={mttr.by_tool.map((t) => t.tool.replace('_', ' '))}
          series={[
            {
              name: 'MTTR (hours)',
              data: mttr.by_tool.map((t) => Number(t.mttr_hours)),
              color: '#79c0ff',
            },
          ]}
          height={160}
        />
      </div>

      {mttr.by_severity.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <BarChart
            title="MTTR by Severity"
            xAxisData={mttr.by_severity.map((s) => s.severity)}
            series={[
              {
                name: 'MTTR (hours)',
                data: mttr.by_severity.map((s) => Number(s.mttr_hours)),
                color: '#d29922',
              },
            ]}
            height={140}
          />
        </div>
      )}
    </div>
  );
}

/* ── Coverage Section ── */

function CoverageSection({ coverage }: { coverage: CoverageGrowthResponse }) {
  const featureEntries = useMemo(() => {
    const fc = coverage.feature_coverage ?? {};
    return FEATURE_NAMES.filter((f) => fc[f]).map((f) => ({
      name: f.replace(/_/g, ' '),
      pct: fc[f].pct,
      repos: fc[f].repos,
    }));
  }, [coverage.feature_coverage]);

  const avgPct = useMemo(() => {
    if (featureEntries.length === 0) return 0;
    return Math.round(featureEntries.reduce((s, e) => s + e.pct, 0) / featureEntries.length);
  }, [featureEntries]);

  const timeSeriesData = useMemo(
    () => ({
      dates: coverage.time_series.map((p) => p.date),
      values: coverage.time_series.map((p) => {
        // Average the pct across features for the coverage growth chart
        const pcts = [
          p.ghas_pct,
          p.code_scanning_pct,
          p.secret_scanning_pct,
          p.dependabot_pct,
          p.push_protection_pct,
        ].filter((v) => v != null);
        return pcts.length > 0 ? Math.round(pcts.reduce((a, b) => a + b, 0) / pcts.length) : 0;
      }),
    }),
    [coverage.time_series],
  );

  const uncoveredCols: ColumnDef<UncoveredRepo>[] = useMemo(
    () => [
      { key: 'repo_full_name', header: 'Repository', render: (r) => r.repo_full_name },
      {
        key: 'missing_features',
        header: 'Missing Features',
        render: (r) => r.missing_features.join(', '),
      },
    ],
    [],
  );

  return (
    <div className={styles.trendSection}>
      <div className={styles.trendHeader}>
        <span className={styles.trendTitle}>
          Security Coverage — {avgPct}% avg ({coverage.total_repos} repos)
        </span>
      </div>

      {timeSeriesData.dates.length > 0 && (
        <LineAreaChart
          title="Coverage Growth Over Time"
          xAxisData={timeSeriesData.dates}
          series={[
            {
              name: 'Avg Coverage %',
              data: timeSeriesData.values,
              color: '#3fb950',
              areaOpacity: 0.2,
            },
          ]}
          height={180}
          yAxisFormatter={(v: number) => `${Math.round(v)}%`}
        />
      )}

      {featureEntries.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <BarChart
            title="Coverage by Feature"
            xAxisData={featureEntries.map((f) => f.name)}
            series={[
              {
                name: 'Coverage %',
                data: featureEntries.map((f) => Number(f.pct)),
                color: '#3fb950',
              },
            ]}
            height={160}
          />
        </div>
      )}

      {coverage.uncovered_repos.length > 0 && (
        <div className={styles.tableSection} style={{ marginTop: 16 }}>
          <div className={styles.severityTitle}>
            Uncovered Repos — Top {coverage.uncovered_repos.length}
          </div>
          <DataTable
            columns={uncoveredCols}
            data={coverage.uncovered_repos}
            rowKey={(repo) => repo.repo_full_name}
          />
        </div>
      )}
    </div>
  );
}

/* ── Alert Aging & Burndown ── */

function AgingSection({ aging }: { aging: AlertAgingResponse }) {
  const bucketLabels = aging.age_buckets.map((b) => b.bucket);

  const oldestCols: ColumnDef<OldestAlert>[] = useMemo(
    () => [
      { key: 'repo_full_name', header: 'Repository', render: (r) => r.repo_full_name },
      { key: 'rule_info', header: 'Rule', render: (r) => r.rule_info },
      { key: 'tool', header: 'Tool', render: (r) => r.tool },
      { key: 'age_days', header: 'Age', render: (r) => `${r.age_days}d` },
      {
        key: 'created_at',
        header: 'Created',
        render: (r) => formatRelativeShort(r.created_at),
      },
    ],
    [],
  );

  const burndown = aging.burndown_projection;

  return (
    <div className={styles.trendSection}>
      <div className={styles.trendHeader}>
        <span className={styles.trendTitle}>Alert Aging &amp; Burndown</span>
      </div>

      <BarChart
        title="Open Alerts by Age"
        xAxisData={bucketLabels}
        series={[
          {
            name: 'Critical',
            data: aging.age_buckets.map((b) => b.critical_count),
            color: '#f85149',
          },
          {
            name: 'High',
            data: aging.age_buckets.map((b) => b.high_count),
            color: '#db6d28',
          },
          {
            name: 'Other',
            data: aging.age_buckets.map((b) =>
              Math.max(0, b.total_count - b.critical_count - b.high_count),
            ),
            color: '#8b949e',
          },
        ]}
        height={200}
      />

      {burndown.time_series.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <LineAreaChart
            title={`Burndown Projection — ${burndown.weeks_to_zero !== null ? `~${Math.round(burndown.weeks_to_zero)} weeks to zero` : 'not converging'}`}
            xAxisData={burndown.time_series.map((p) => `Week ${p.week}`)}
            series={[
              {
                name: 'Projected Open',
                data: burndown.time_series.map((p) => p.projected_open),
                color: '#d29922',
                dashed: true,
              },
            ]}
            height={180}
          />
          <div style={{ fontSize: 12, color: 'var(--fg-muted)', marginTop: 4 }}>
            Current open: {burndown.current_open} · Avg close rate:{' '}
            {burndown.avg_close_rate_per_week.toFixed(1)}/week
          </div>
        </div>
      )}

      {aging.oldest_critical.length > 0 && (
        <div className={styles.tableSection} style={{ marginTop: 16 }}>
          <div className={styles.severityTitle}>Oldest Critical/High Alerts</div>
          <DataTable
            columns={oldestCols}
            data={aging.oldest_critical}
            rowKey={(alert) => `${alert.repo_full_name}-${alert.alert_number}`}
          />
        </div>
      )}
    </div>
  );
}
