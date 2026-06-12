import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { BarChart } from '../../components/charts/BarChart';
import { getCopilotChatMetrics } from '../../api/copilotMetrics';
import { useChartColors } from '../../hooks/useChartColors';
import { useOrg } from '../../hooks/useOrg';
import styles from './Copilot.module.css';

function formatDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function ChatMetricsPane() {
  const { selectedOrg } = useOrg();
  const orgParam = selectedOrg || undefined;
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['copilot', 'chat-metrics', orgParam],
    queryFn: () => getCopilotChatMetrics(orgParam),
    staleTime: 30 * 60 * 1000,
  });
  const chartColors = useChartColors();

  if (isLoading) return <Spinner />;
  if (isError)
    return <ErrorBanner message="Failed to load chat metrics" onRetry={() => void refetch()} />;
  if (data?.error) return <ErrorBanner message={data.message ?? 'Chat metrics unavailable'} />;

  const dates = (data?.dates ?? []).map(formatDate);

  return (
    <>
      {/* Summary stats */}
      <div className={styles.metricStrip}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>
            {(data?.total_interactions ?? []).reduce((a, b) => a + b, 0).toLocaleString()}
          </div>
          <div className={styles.statLabel}>Total Interactions (28d)</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>
            {(data?.code_actions ?? []).reduce((a, b) => a + b, 0).toLocaleString()}
          </div>
          <div className={styles.statLabel}>Code Actions (28d)</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{Math.max(...(data?.active_chat_users ?? [0]))}</div>
          <div className={styles.statLabel}>Peak Active Chat Users</div>
        </div>
      </div>

      {/* Daily interactions */}
      <Card style={{ marginBottom: 16 }}>
        <CardHeader>Daily Chat Interactions &amp; Code Actions</CardHeader>
        <div style={{ padding: '0 16px 16px' }}>
          <LineAreaChart
            xAxisData={dates}
            series={[
              {
                name: 'Interactions',
                data: data?.total_interactions ?? [],
                color: chartColors.accent,
                areaOpacity: 0.12,
              },
              {
                name: 'Code Actions',
                data: data?.code_actions ?? [],
                color: chartColors.success,
                areaOpacity: 0.12,
              },
            ]}
            height={220}
          />
        </div>
      </Card>

      <div className={styles.grid2}>
        {/* Active chat users */}
        <Card>
          <CardHeader>Daily active chat users</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <BarChart
              xAxisData={dates}
              series={[
                {
                  name: 'Active Users',
                  data: data?.active_chat_users ?? [],
                  color: chartColors.accent,
                },
              ]}
              height={200}
            />
          </div>
        </Card>

        {/* Action rate */}
        <Card>
          <CardHeader>Daily action rate</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <LineAreaChart
              xAxisData={dates}
              series={[
                {
                  name: 'Action Rate %',
                  data: data?.action_rate_pct ?? [],
                  color: chartColors.success,
                  areaOpacity: 0.1,
                },
              ]}
              height={200}
              yAxisFormatter={(v) => `${v}%`}
            />
          </div>
        </Card>
      </div>
    </>
  );
}
