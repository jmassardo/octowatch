import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { BarChart } from '../../components/charts/BarChart';
import { StackedBarChart } from '../../components/charts/StackedBarChart';
import { HorizontalBarChart } from '../../components/charts/HorizontalBarChart';
import { getCopilotAgentActivity } from '../../api/copilotMetrics';
import { useChartColors } from '../../hooks/useChartColors';
import { useOrg } from '../../hooks/useOrg';
import styles from './Copilot.module.css';

function formatDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function AgentActivityPane() {
  const { selectedOrg } = useOrg();
  const orgParam = selectedOrg || undefined;
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['copilot', 'agent-activity', orgParam],
    queryFn: () => getCopilotAgentActivity(orgParam),
    staleTime: 30 * 60 * 1000,
  });
  const chartColors = useChartColors();

  if (isLoading) return <Spinner />;
  if (isError)
    return <ErrorBanner message="Failed to load agent activity" onRetry={() => void refetch()} />;
  if (data?.error)
    return <ErrorBanner message={data.message ?? 'Agent activity data unavailable'} />;

  const dates = (data?.dates ?? []).map(formatDate);
  const linesByMode = data?.lines_by_mode ?? {};
  const modeNames = Object.keys(linesByMode);
  const linesByModel = data?.lines_by_model ?? [];
  const linesByLang = data?.lines_by_language ?? [];

  const totalAdded = (data?.daily_lines_added ?? []).reduce((a, b) => a + b, 0);
  const totalAccepted = (data?.daily_lines_accepted ?? []).reduce((a, b) => a + b, 0);

  const palette = [
    chartColors.accent,
    chartColors.success,
    chartColors.attention,
    chartColors.done,
    chartColors.danger,
    '#a371f7',
    '#79c0ff',
    '#d2a8ff',
  ];

  return (
    <>
      {/* Summary stats */}
      <div className={styles.metricStrip}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{totalAdded.toLocaleString()}</div>
          <div className={styles.statLabel}>Lines Suggested (28d)</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue} style={{ color: 'var(--success)' }}>
            {totalAccepted.toLocaleString()}
          </div>
          <div className={styles.statLabel}>Lines Accepted (28d)</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>
            {totalAdded > 0 ? `${Math.round((totalAccepted / totalAdded) * 100)}%` : '—'}
          </div>
          <div className={styles.statLabel}>Line Acceptance Rate</div>
        </div>
      </div>

      {/* Daily lines added & accepted */}
      <Card style={{ marginBottom: 16 }}>
        <CardHeader>Daily lines suggested &amp; accepted</CardHeader>
        <div style={{ padding: '0 16px 16px' }}>
          <BarChart
            xAxisData={dates}
            series={[
              {
                name: 'Suggested',
                data: data?.daily_lines_added ?? [],
                color: chartColors.accent,
              },
              {
                name: 'Accepted',
                data: data?.daily_lines_accepted ?? [],
                color: chartColors.success,
              },
            ]}
            height={220}
          />
        </div>
      </Card>

      {/* Lines by mode (stacked bar) */}
      {modeNames.length > 0 && (
        <Card style={{ marginBottom: 16 }}>
          <CardHeader>Code changes by mode</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <StackedBarChart
              xAxisData={dates}
              series={modeNames.map((mode, idx) => ({
                name: mode,
                data: linesByMode[mode],
                color: palette[idx % palette.length],
              }))}
              height={220}
            />
          </div>
        </Card>
      )}

      {/* Lines by model + Lines by language (horizontal bars) */}
      <div className={styles.grid2}>
        {linesByModel.length > 0 && (
          <Card>
            <CardHeader>Lines added by model</CardHeader>
            <div style={{ padding: '0 16px 16px' }}>
              <HorizontalBarChart
                categories={linesByModel.map((m) => m.model)}
                series={[
                  {
                    name: 'Lines Added',
                    data: linesByModel.map((m) => m.lines_added),
                    color: chartColors.accent,
                  },
                  {
                    name: 'Lines Accepted',
                    data: linesByModel.map((m) => m.lines_accepted),
                    color: chartColors.success,
                  },
                ]}
                height={Math.max(160, linesByModel.length * 36)}
              />
            </div>
          </Card>
        )}
        {linesByLang.length > 0 && (
          <Card>
            <CardHeader>Lines added by language</CardHeader>
            <div style={{ padding: '0 16px 16px' }}>
              <HorizontalBarChart
                categories={linesByLang.map((l) => l.language)}
                series={[
                  {
                    name: 'Lines Added',
                    data: linesByLang.map((l) => l.lines_added),
                    color: chartColors.accent,
                  },
                  {
                    name: 'Lines Accepted',
                    data: linesByLang.map((l) => l.lines_accepted),
                    color: chartColors.success,
                  },
                ]}
                height={Math.max(160, linesByLang.length * 36)}
              />
            </div>
          </Card>
        )}
      </div>

      {/* Feature activity breakdown as line chart */}
      {modeNames.length > 0 && (
        <Card style={{ marginTop: 16 }}>
          <CardHeader>Feature activity over time</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <LineAreaChart
              xAxisData={dates}
              series={modeNames.map((mode, idx) => ({
                name: mode,
                data: linesByMode[mode],
                color: palette[idx % palette.length],
              }))}
              height={200}
            />
          </div>
        </Card>
      )}
    </>
  );
}
