import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { DonutChart } from '../../components/charts/DonutChart';
import { BarChart } from '../../components/charts/BarChart';
import { HorizontalBarChart } from '../../components/charts/HorizontalBarChart';
import { getCopilotLanguageBreakdown } from '../../api/copilotMetrics';
import { useChartColors } from '../../hooks/useChartColors';
import { useOrg } from '../../hooks/useOrg';
import styles from './Copilot.module.css';

function formatDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function LanguageBreakdownPane() {
  const { selectedOrg } = useOrg();
  const orgParam = selectedOrg || undefined;
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['copilot', 'language-breakdown', orgParam],
    queryFn: () => getCopilotLanguageBreakdown(orgParam),
    staleTime: 30 * 60 * 1000,
  });
  const chartColors = useChartColors();

  if (isLoading) return <Spinner />;
  if (isError)
    return <ErrorBanner message="Failed to load language data" onRetry={() => void refetch()} />;
  if (data?.error) return <ErrorBanner message={data.message ?? 'Language data unavailable'} />;

  const dates = (data?.dates ?? []).map(formatDate);
  const langPerDay = data?.language_per_day ?? {};
  const langNames = Object.keys(langPerDay);

  // Build series for stacked area chart (language per day)
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
  const langSeries = langNames.map((lang, idx) => ({
    name: lang,
    data: langPerDay[lang],
    color: palette[idx % palette.length],
    areaOpacity: 0.3,
  }));

  // Model per language (grouped bar)
  const modelPerLang = data?.model_per_language;

  // Acceptance by editor (horizontal bar)
  const editorData = data?.acceptance_by_editor ?? [];

  // Top 5 charts
  const topGens = data?.top_by_generations ?? [];
  const topLines = data?.top_by_lines ?? [];

  return (
    <>
      {/* Language usage per day (stacked area) */}
      <Card style={{ marginBottom: 16 }}>
        <CardHeader>Language usage per day</CardHeader>
        <div style={{ padding: '0 16px 16px' }}>
          <LineAreaChart xAxisData={dates} series={langSeries} height={240} />
        </div>
      </Card>

      <div className={styles.grid2}>
        {/* Language distribution donut */}
        <Card>
          <CardHeader>Language distribution</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <DonutChart data={data?.language_distribution ?? []} height={220} title="" />
          </div>
        </Card>

        {/* Model usage per language (grouped bar) */}
        {modelPerLang && modelPerLang.labels.length > 0 && (
          <Card>
            <CardHeader>Model usage per language</CardHeader>
            <div style={{ padding: '0 16px 16px' }}>
              <BarChart
                xAxisData={modelPerLang.labels}
                series={modelPerLang.series.map((s, idx) => ({
                  name: s.name,
                  data: s.data,
                  color: palette[idx % palette.length],
                }))}
                height={220}
              />
            </div>
          </Card>
        )}
      </div>

      {/* Acceptance rate by editor */}
      {editorData.length > 0 && (
        <Card style={{ marginBottom: 16 }}>
          <CardHeader>Acceptance rate by editor</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <HorizontalBarChart
              categories={editorData.map((e) => e.editor)}
              series={[
                {
                  name: 'Acceptance %',
                  data: editorData.map((e) => Math.round(e.rate * 10) / 10),
                  color: chartColors.success,
                },
              ]}
              height={Math.max(120, editorData.length * 32)}
              xAxisFormatter={(v) => `${v}%`}
            />
          </div>
        </Card>
      )}

      {/* Top 5 by generations + Top 5 by lines */}
      <div className={styles.grid2}>
        {topGens.length > 0 && (
          <Card>
            <CardHeader>Top 5 languages by code generations</CardHeader>
            <div style={{ padding: '0 16px 16px' }}>
              <HorizontalBarChart
                categories={topGens.map((l) => l.language)}
                series={[
                  {
                    name: 'Generations',
                    data: topGens.map((l) => l.count),
                    color: chartColors.accent,
                  },
                ]}
                height={180}
              />
            </div>
          </Card>
        )}
        {topLines.length > 0 && (
          <Card>
            <CardHeader>Top 5 languages by lines added</CardHeader>
            <div style={{ padding: '0 16px 16px' }}>
              <HorizontalBarChart
                categories={topLines.map((l) => l.language)}
                series={[
                  {
                    name: 'Lines',
                    data: topLines.map((l) => l.lines),
                    color: chartColors.success,
                  },
                ]}
                height={180}
              />
            </div>
          </Card>
        )}
      </div>
    </>
  );
}
