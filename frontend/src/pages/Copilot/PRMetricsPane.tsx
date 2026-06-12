import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { BarChart } from '../../components/charts/BarChart';
import { getCopilotPRMetrics } from '../../api/copilotMetrics';
import { useChartColors } from '../../hooks/useChartColors';
import { useOrg } from '../../hooks/useOrg';
import styles from './Copilot.module.css';

function formatDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function PRMetricsPane() {
  const { selectedOrg } = useOrg();
  const orgParam = selectedOrg || undefined;
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['copilot', 'pr-metrics', orgParam],
    queryFn: () => getCopilotPRMetrics(orgParam),
    staleTime: 30 * 60 * 1000,
  });
  const chartColors = useChartColors();

  if (isLoading) return <Spinner />;
  if (isError)
    return <ErrorBanner message="Failed to load PR metrics" onRetry={() => void refetch()} />;
  if (data?.error) return <ErrorBanner message={data.message ?? 'PR metrics unavailable'} />;

  const dates = (data?.dates ?? []).map(formatDate);

  const totalPRActivity = (data?.pr_activity ?? []).reduce((a, b) => a + b, 0);
  const totalContributions = (data?.pr_contributions ?? []).reduce((a, b) => a + b, 0);
  const totalReviews = (data?.review_suggestions ?? []).reduce((a, b) => a + b, 0);

  return (
    <>
      {/* Summary stats */}
      <div className={styles.metricStrip}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{totalPRActivity.toLocaleString()}</div>
          <div className={styles.statLabel}>PR Active Users (28d)</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{totalContributions.toLocaleString()}</div>
          <div className={styles.statLabel}>PR Summaries Generated</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{totalReviews.toLocaleString()}</div>
          <div className={styles.statLabel}>Review Suggestions Accepted</div>
        </div>
      </div>

      {/* PR Activity Over Time */}
      <Card style={{ marginBottom: 16 }}>
        <CardHeader>Pull Request Activity Over Time</CardHeader>
        <div style={{ padding: '0 16px 16px' }}>
          <LineAreaChart
            xAxisData={dates}
            series={[
              {
                name: 'Active PR Users',
                data: data?.pr_activity ?? [],
                color: chartColors.accent,
                areaOpacity: 0.12,
              },
            ]}
            height={220}
          />
        </div>
      </Card>

      <div className={styles.grid2}>
        {/* Copilot PR Contributions */}
        <Card>
          <CardHeader>Copilot PR contributions</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <BarChart
              xAxisData={dates}
              series={[
                {
                  name: 'PR Summaries',
                  data: data?.pr_contributions ?? [],
                  color: chartColors.success,
                },
              ]}
              height={200}
            />
          </div>
        </Card>

        {/* Review Suggestions */}
        <Card>
          <CardHeader>Review suggestions</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <LineAreaChart
              xAxisData={dates}
              series={[
                {
                  name: 'Suggestions Accepted',
                  data: data?.review_suggestions ?? [],
                  color: chartColors.attention,
                  areaOpacity: 0.1,
                },
              ]}
              height={200}
            />
          </div>
        </Card>
      </div>
    </>
  );
}
