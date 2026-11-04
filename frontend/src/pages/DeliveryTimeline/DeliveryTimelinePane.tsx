import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getDeliveryTimeline } from '../../api/deliveryTimeline';
import type { DeliveryTimelineItem } from '../../api/deliveryTimeline';
import { MetricCard } from '../../components/primitives/MetricCard';
import { BarChart } from '../../components/charts/BarChart';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { useOrg } from '../../hooks/useOrg';
import styles from './DeliveryTimeline.module.css';

const PHASE_LABELS: Record<string, string> = {
  backlog: 'Backlog',
  dev: 'Development',
  review: 'Review',
  deploy: 'Deploy',
};

function formatHours(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${value.toFixed(1)}h`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** Sort timelines ascending by merge/created date for trend charting. */
function buildTrendData(timelines: DeliveryTimelineItem[]): {
  labels: string[];
  totalHours: number[];
} {
  const sorted = [...timelines]
    .filter((t) => t.total_hours !== null)
    .sort((a, b) => {
      const aDate = new Date(a.pr_merged_at ?? a.created_at).getTime();
      const bDate = new Date(b.pr_merged_at ?? b.created_at).getTime();
      return aDate - bDate;
    });

  return {
    labels: sorted.map((t) => formatDate(t.pr_merged_at ?? t.created_at)),
    totalHours: sorted.map((t) => t.total_hours ?? 0),
  };
}

export function DeliveryTimelinePane() {
  const { selectedOrg } = useOrg();
  const orgParam = selectedOrg || undefined;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['delivery-timeline', orgParam],
    queryFn: () => getDeliveryTimeline({ org: orgParam }),
    staleTime: 60_000,
  });

  const phaseChart = useMemo(() => {
    if (!data) return null;
    const phases: { key: string; value: number | null }[] = [
      { key: 'backlog', value: data.avg_backlog_hours },
      { key: 'dev', value: data.avg_dev_hours },
      { key: 'review', value: data.avg_review_hours },
      { key: 'deploy', value: data.avg_deploy_hours },
    ];
    return {
      labels: phases.map((p) => PHASE_LABELS[p.key] ?? p.key),
      values: phases.map((p) => p.value ?? 0),
    };
  }, [data]);

  const trendChart = useMemo(() => (data ? buildTrendData(data.timelines) : null), [data]);

  if (isLoading) return <Spinner />;
  if (isError)
    return (
      <ErrorBanner message="Failed to load delivery timeline metrics" onRetry={() => refetch()} />
    );

  const bottleneckLabel = data?.bottleneck_phase ? PHASE_LABELS[data.bottleneck_phase] : null;

  return (
    <div>
      {/* Bottleneck callout */}
      {bottleneckLabel && (
        <div className={styles.calloutBox}>
          <div className={styles.calloutBody}>
            <div className={styles.calloutTitle}>Bottleneck phase: {bottleneckLabel}</div>
            <div className={styles.calloutDesc}>
              The <strong>{bottleneckLabel.toLowerCase()}</strong> phase currently takes the longest
              on average across delivered pull requests. Focus process improvements there to reduce
              overall delivery time.
            </div>
          </div>
        </div>
      )}

      {/* Summary metric strip */}
      <div className={styles.metricStrip}>
        <MetricCard value={String(data?.total_prs ?? 0)} label="Total PRs" />
        <MetricCard value={formatHours(data?.avg_backlog_hours)} label="Avg Backlog" />
        <MetricCard value={formatHours(data?.avg_dev_hours)} label="Avg Development" />
        <MetricCard value={formatHours(data?.avg_review_hours)} label="Avg Review" />
        <MetricCard value={formatHours(data?.avg_deploy_hours)} label="Avg Deploy" />
        <MetricCard value={formatHours(data?.avg_total_hours)} label="Avg Total" />
      </div>

      <div className={styles.chartsGrid}>
        {/* Phase breakdown chart */}
        <div className={styles.chartWrap}>
          <div className={styles.chartTitle}>Phase breakdown — average hours</div>
          {phaseChart && phaseChart.values.some((v) => v > 0) ? (
            <BarChart
              xAxisData={phaseChart.labels}
              series={[{ name: 'Avg Hours', data: phaseChart.values, color: 'var(--accent)' }]}
              height={220}
            />
          ) : (
            <div className={styles.emptyState}>No phase data available</div>
          )}
        </div>

        {/* Trend chart */}
        <div className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Total delivery time trend
            <span className={styles.chartSub}> — recent merged PRs</span>
          </div>
          {trendChart && trendChart.labels.length > 0 ? (
            <LineAreaChart
              xAxisData={trendChart.labels}
              series={[
                {
                  name: 'Total Hours',
                  data: trendChart.totalHours,
                  color: 'var(--accent)',
                  areaOpacity: 0.1,
                },
              ]}
              height={220}
            />
          ) : (
            <div className={styles.emptyState}>No trend data available</div>
          )}
        </div>
      </div>
    </div>
  );
}
