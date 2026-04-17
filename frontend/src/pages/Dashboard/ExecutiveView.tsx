import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getExecutiveSummary, exportExecutivePdf } from '../../api/executive';
import type { ExecutiveSummary as ExecutiveSummaryType } from '../../api/executive';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { MetricsThatMatter } from './MetricsThatMatter';
import styles from './ExecutiveView.module.css';

type Period = 7 | 30 | 90;

function ScoreCard({ summary }: { summary: ExecutiveSummaryType }) {
  const { posture_score, score_delta, score_delta_pct } = summary;
  const isDown = score_delta < 0;
  const isBigDrop = score_delta_pct < -10;

  return (
    <div className={styles.scoreCard}>
      <div className={styles.scoreValue}>{posture_score}</div>
      <div className={styles.scoreLabel}>Security Posture Score</div>
      <div
        className={[
          styles.scoreDelta,
          isDown ? styles.deltaDown : styles.deltaUp,
          isBigDrop ? styles.deltaBigDrop : '',
        ]
          .filter(Boolean)
          .join(' ')}
        title={
          isBigDrop
            ? `Score decreased by ${Math.abs(score_delta_pct).toFixed(1)}% — exceeds 10% threshold`
            : undefined
        }
      >
        <span aria-hidden="true">{isDown ? '▼' : '▲'}</span> {Math.abs(score_delta).toFixed(1)} (
        {Math.abs(score_delta_pct).toFixed(1)}%)
      </div>
    </div>
  );
}

function ComplianceCards({ summary }: { summary: ExecutiveSummaryType }) {
  return (
    <div className={styles.complianceGrid}>
      {summary.compliance_summary.map((c) => (
        <Card key={c.framework} className={styles.complianceCard}>
          <div className={styles.complianceFramework}>{c.framework}</div>
          <div className={styles.complianceBar}>
            <div
              className={styles.complianceFill}
              style={{ width: `${Math.min(100, c.compliance_pct)}%` }}
            />
          </div>
          <div className={styles.complianceMeta}>
            <span className={styles.compliancePct}>{c.compliance_pct.toFixed(0)}%</span>
            <span className={styles.complianceDetail}>
              {c.controls_with_evidence}/{c.controls_assessed} controls
            </span>
          </div>
        </Card>
      ))}
    </div>
  );
}

function TopRisksList({ summary }: { summary: ExecutiveSummaryType }) {
  if (summary.top_risks.length === 0) {
    return <div className={styles.emptyText}>No open risks in this period</div>;
  }
  return (
    <div className={styles.riskList}>
      {summary.top_risks.map((r, i) => (
        <div key={i} className={styles.riskRow}>
          <span className={[styles.riskDot, styles[r.severity]].filter(Boolean).join(' ')} />
          <div className={styles.riskInfo}>
            <div className={styles.riskTitle}>{r.title}</div>
            <div className={styles.riskMeta}>
              {r.severity} · {r.count} occurrence{r.count !== 1 ? 's' : ''}
              {r.actor && <> · @{r.actor}</>}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function MomCards({ summary }: { summary: ExecutiveSummaryType }) {
  const m = summary.month_over_month;
  return (
    <div className={styles.momGrid}>
      <div className={styles.momCard}>
        <div className={styles.momValue}>{m.current_detections}</div>
        <div className={styles.momLabel}>Detections</div>
        <div
          className={[styles.momChange, m.detection_change_pct > 0 ? styles.momUp : styles.momDn]
            .filter(Boolean)
            .join(' ')}
        >
          {m.detection_change_pct > 0 ? '+' : ''}
          {m.detection_change_pct.toFixed(1)}% vs prev
        </div>
      </div>
      <div className={styles.momCard}>
        <div className={styles.momValue}>{m.current_events.toLocaleString()}</div>
        <div className={styles.momLabel}>Events</div>
        <div
          className={[styles.momChange, m.event_change_pct > 0 ? styles.momUp : styles.momDn]
            .filter(Boolean)
            .join(' ')}
        >
          {m.event_change_pct > 0 ? '+' : ''}
          {m.event_change_pct.toFixed(1)}% vs prev
        </div>
      </div>
    </div>
  );
}

export function ExecutiveView() {
  const [period, setPeriod] = useState<Period>(30);

  const {
    data: summary,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['executive-summary', period],
    queryFn: () => getExecutiveSummary(period),
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <div className={styles.center}>
        <Spinner />
      </div>
    );
  }

  if (isError || !summary) {
    return <ErrorBanner message="Failed to load executive summary" onRetry={refetch} />;
  }

  // Build trend chart data from detection_trend
  const trendLabels = Object.keys(summary.detection_trend);
  const trendValues = Object.values(summary.detection_trend);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.title}>Executive Security Summary</div>
          <div className={styles.subtitle}>Organization-level security posture overview</div>
        </div>
        <div className={styles.headerActions}>
          <div className={styles.periodToggle}>
            {([7, 30, 90] as Period[]).map((p) => (
              <button
                key={p}
                className={[styles.periodBtn, period === p && styles.active]
                  .filter(Boolean)
                  .join(' ')}
                onClick={() => setPeriod(p)}
              >
                {p}d
              </button>
            ))}
          </div>
          <Button size="sm" variant="primary" onClick={() => exportExecutivePdf(period)}>
            Export as PDF
          </Button>
        </div>
      </div>

      <ScoreCard summary={summary} />

      <div className={styles.grid2}>
        <Card>
          <CardHeader>Detection Trend</CardHeader>
          <LineAreaChart
            xAxisData={trendLabels}
            series={[
              {
                name: 'Detections',
                data: trendValues,
                color: '#f85149',
                areaOpacity: 0.15,
              },
            ]}
            height={200}
          />
        </Card>
        <Card>
          <CardHeader>Month-over-Month</CardHeader>
          <MomCards summary={summary} />
        </Card>
      </div>

      <Card>
        <CardHeader>Compliance Status</CardHeader>
        <ComplianceCards summary={summary} />
      </Card>

      <Card>
        <CardHeader>Top Risks</CardHeader>
        <TopRisksList summary={summary} />
      </Card>

      <MetricsThatMatter period={period} />
    </div>
  );
}
