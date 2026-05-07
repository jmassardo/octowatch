import { useQuery } from '@tanstack/react-query';
import { getAnalytics } from '../../api/threatIntel';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { BarChart } from '../../components/charts/BarChart';
import styles from './ThreatIntel.module.css';

/** Simple donut chart using ECharts via the same pattern as other charts. */
function DonutChart({
  title,
  data,
}: {
  title: string;
  data: readonly { type: string; count: number }[];
}) {
  // Re-use BarChart as a horizontal representation since we already have it
  // For a donut, we show the data as a bar chart with type names on x-axis
  const xAxisData = data.map((d) => d.type);
  const series = [{ name: 'Count', data: data.map((d) => d.count), color: '#bc8cff' }];

  if (data.length === 0) {
    return (
      <div className={styles.chartCard}>
        <div className={styles.chartTitle}>{title}</div>
        <div className={styles.emptyState}>No data available</div>
      </div>
    );
  }

  return (
    <div className={styles.chartCard}>
      <div className={styles.chartTitle}>{title}</div>
      <BarChart xAxisData={xAxisData} series={series} height={200} />
    </div>
  );
}

export function AnalyticsTab() {
  const {
    data: analytics,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['threat-intel', 'analytics'],
    queryFn: getAnalytics,
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <div className={styles.centered}>
        <Spinner />
      </div>
    );
  }

  if (isError) {
    return <ErrorBanner message="Failed to load analytics" onRetry={refetch} />;
  }

  if (!analytics) return null;

  const matchDates = analytics.matches_over_time.map((m) => m.date);
  const matchCounts = analytics.matches_over_time.map((m) => m.count);

  const feedNames = analytics.matches_by_feed.map((f) => f.name);
  const feedCounts = analytics.matches_by_feed.map((f) => f.count);

  return (
    <div>
      <div className={styles.metricsRow}>
        <MetricCard value={String(analytics.total_feeds)} label="Total Feeds" />
        <MetricCard value={String(analytics.total_indicators)} label="Total Indicators" />
        <MetricCard value={String(analytics.matches_30d)} label="Matches (30d)" />
        <MetricCard
          value={`${Math.round(analytics.coverage_score * 100)}%`}
          label="Coverage Score"
        />
      </div>

      <div className={styles.chartsGrid}>
        <div className={[styles.chartCard, styles.chartFull].join(' ')}>
          <div className={styles.chartTitle}>Matches Over Time (30 days)</div>
          {matchDates.length > 0 ? (
            <LineAreaChart
              xAxisData={matchDates}
              series={[
                {
                  name: 'Matches',
                  data: matchCounts,
                  color: '#f85149',
                  areaOpacity: 0.15,
                },
              ]}
              height={220}
            />
          ) : (
            <div className={styles.emptyState}>No match data for the last 30 days</div>
          )}
        </div>

        <div className={styles.chartCard}>
          <div className={styles.chartTitle}>Indicators by Source</div>
          {feedNames.length > 0 ? (
            <BarChart
              xAxisData={feedNames}
              series={[{ name: 'Indicators', data: feedCounts, color: '#58a6ff' }]}
              height={200}
            />
          ) : (
            <div className={styles.emptyState}>No feed data available</div>
          )}
        </div>

        <DonutChart
          title="Indicator Type Distribution"
          data={analytics.indicator_type_distribution}
        />
      </div>
    </div>
  );
}
