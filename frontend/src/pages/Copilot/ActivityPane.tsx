import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { BarChart } from '../../components/charts/BarChart';
import { StackedBarChart } from '../../components/charts/StackedBarChart';
import { getCopilotActivity } from '../../api/copilotMetrics';
import { useChartColors } from '../../hooks/useChartColors';
import { useOrg } from '../../hooks/useOrg';
import styles from './Copilot.module.css';

function formatDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function ActivityPane() {
  const { selectedOrg } = useOrg();
  const orgParam = selectedOrg || undefined;
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['copilot', 'activity', orgParam],
    queryFn: () => getCopilotActivity(orgParam),
    staleTime: 30 * 60 * 1000,
  });
  const chartColors = useChartColors();

  if (isLoading) return <Spinner />;
  if (isError)
    return <ErrorBanner message="Failed to load activity data" onRetry={() => void refetch()} />;
  if (data?.error) return <ErrorBanner message={data.message ?? 'Activity data unavailable'} />;

  const dates = (data?.dates ?? []).map(formatDate);
  const modeData = data?.requests_per_mode;
  const modeDates = (modeData?.dates ?? []).map(formatDate);

  return (
    <>
      {/* DAU / WAU */}
      <div className={styles.grid2}>
        <Card>
          <CardHeader>IDE daily active users</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <LineAreaChart
              xAxisData={dates}
              series={[
                {
                  name: 'DAU',
                  data: data?.ide_dau ?? [],
                  color: chartColors.accent,
                  areaOpacity: 0.15,
                },
              ]}
              height={200}
            />
          </div>
        </Card>
        <Card>
          <CardHeader>IDE weekly active users</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <LineAreaChart
              xAxisData={dates}
              series={[
                {
                  name: 'WAU',
                  data: data?.ide_wau ?? [],
                  color: chartColors.success,
                  areaOpacity: 0.15,
                },
              ]}
              height={200}
            />
          </div>
        </Card>
      </div>

      {/* Code completions + Acceptance rate */}
      <div className={styles.grid2}>
        <Card>
          <CardHeader>Code completions</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <LineAreaChart
              xAxisData={dates}
              series={[
                {
                  name: 'Suggestions',
                  data: data?.completions_count ?? [],
                  color: chartColors.accent,
                },
                {
                  name: 'Accepted',
                  data: data?.completions_accepted ?? [],
                  color: chartColors.success,
                },
              ]}
              height={200}
            />
          </div>
        </Card>
        <Card>
          <CardHeader>Code completions acceptance rate</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <BarChart
              xAxisData={dates}
              series={[
                {
                  name: 'Acceptance %',
                  data: data?.acceptance_rate_pct ?? [],
                  color: chartColors.success,
                },
              ]}
              height={200}
            />
          </div>
        </Card>
      </div>

      {/* Chat per user + Requests per mode */}
      <div className={styles.grid2}>
        <Card>
          <CardHeader>Average chat requests per active user</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <LineAreaChart
              xAxisData={dates}
              series={[
                {
                  name: 'Requests/user',
                  data: data?.chat_requests_per_user ?? [],
                  color: chartColors.attention,
                  areaOpacity: 0.1,
                },
              ]}
              height={200}
            />
          </div>
        </Card>
        <Card>
          <CardHeader>Requests per chat mode</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <StackedBarChart
              xAxisData={modeDates}
              series={[
                { name: 'Completions', data: modeData?.completions ?? [] },
                { name: 'Chat', data: modeData?.chat ?? [] },
                { name: 'Dotcom Chat', data: modeData?.dotcom_chat ?? [] },
                { name: 'PR', data: modeData?.pr ?? [] },
              ]}
              height={200}
            />
          </div>
        </Card>
      </div>
    </>
  );
}
