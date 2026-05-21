/**
 * CustomQueryWidgetInstance — renders a single custom query widget given its
 * configuration ID. Fetches data via the query API and displays the result
 * using the configured visualization type.
 */

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { runQuery } from '../../api/query';
import { useChartColors } from '../../hooks/useChartColors';
import { Spinner } from '../primitives/Spinner';
import { ErrorBanner } from '../primitives/ErrorBanner';
import type { CustomWidgetConfig, VisualizationType } from '../../types/customWidget';
import type { QueryRunResponse } from '../../types/query';
import { getCustomWidgetConfig } from './customWidgetConfigStorage';
import styles from './Widgets.module.css';

// ─── Visualization renderers ────────────────────────────────────────────────

interface VisualizationProps {
  readonly data: QueryRunResponse;
  readonly colors: ReturnType<typeof useChartColors>;
}

function BarVisualization({ data, colors }: VisualizationProps) {
  if (data.columns.length < 2 || data.rows.length === 0) {
    return <p className={styles.metricLabel}>No data to display</p>;
  }

  const xAxisData = data.rows.map((row) => String(row[0] ?? ''));
  const seriesData = data.rows.map((row) => Number(row[1]) || 0);

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { color: colors.chartText, fontFamily: 'inherit', fontSize: 11 },
    grid: { left: 8, right: 8, top: 20, bottom: 20, containLabel: true },
    xAxis: {
      type: 'category',
      data: xAxisData,
      axisLine: { lineStyle: { color: colors.chartGrid } },
      axisTick: { show: false },
      axisLabel: { color: colors.chartTextSecondary, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: colors.chartGrid } },
      axisLabel: { color: colors.chartTextSecondary, fontSize: 10 },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: colors.chartTooltipBg,
      borderColor: colors.chartTooltipBorder,
      textStyle: { color: colors.chartTooltipFg, fontSize: 12 },
    },
    series: [
      {
        name: data.columns[1] ?? 'Value',
        type: 'bar',
        data: seriesData,
        itemStyle: { color: colors.accent, borderRadius: [2, 2, 0, 0] },
        barMaxWidth: 28,
      },
    ],
  };

  return <ReactECharts option={option} style={{ height: 160 }} />;
}

function LineVisualization({ data, colors }: VisualizationProps) {
  if (data.columns.length < 2 || data.rows.length === 0) {
    return <p className={styles.metricLabel}>No data to display</p>;
  }

  const xAxisData = data.rows.map((row) => String(row[0] ?? ''));
  const seriesData = data.rows.map((row) => Number(row[1]) || 0);

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { color: colors.chartText, fontFamily: 'inherit', fontSize: 11 },
    grid: { left: 8, right: 8, top: 20, bottom: 20, containLabel: true },
    xAxis: {
      type: 'category',
      data: xAxisData,
      axisLine: { lineStyle: { color: colors.chartGrid } },
      axisTick: { show: false },
      axisLabel: { color: colors.chartTextSecondary, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: colors.chartGrid } },
      axisLabel: { color: colors.chartTextSecondary, fontSize: 10 },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: colors.chartTooltipBg,
      borderColor: colors.chartTooltipBorder,
      textStyle: { color: colors.chartTooltipFg, fontSize: 12 },
    },
    series: [
      {
        name: data.columns[1] ?? 'Value',
        type: 'line',
        smooth: true,
        data: seriesData,
        lineStyle: { color: colors.accent, width: 2 },
        itemStyle: { color: colors.accent },
        symbol: 'none',
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: colors.accent + '40' },
              { offset: 1, color: 'transparent' },
            ],
          },
        },
      },
    ],
  };

  return <ReactECharts option={option} style={{ height: 160 }} />;
}

function TableVisualization({ data }: Pick<VisualizationProps, 'data'>) {
  if (data.rows.length === 0) {
    return <p className={styles.metricLabel}>No rows returned</p>;
  }

  return (
    <div className={styles.tableContainer}>
      <table className={styles.resultTable}>
        <thead>
          <tr>
            {data.columns.map((col) => (
              <th key={col}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.slice(0, 20).map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{cell == null ? '—' : String(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {data.rows.length > 20 && (
        <p className={styles.metricLabel}>Showing 20 of {data.row_count} rows</p>
      )}
    </div>
  );
}

function StatVisualization({ data, colors }: VisualizationProps) {
  if (data.rows.length === 0 || data.columns.length === 0) {
    return <p className={styles.metricLabel}>No data</p>;
  }

  const value = data.rows[0]?.[0];
  const label = data.columns[0] ?? 'Value';

  return (
    <div className={styles.metricRow}>
      <div>
        <div className={styles.metricValue} style={{ color: colors.accent }}>
          {value == null ? '—' : String(value)}
        </div>
        <div className={styles.metricLabel}>{label}</div>
      </div>
    </div>
  );
}

function PieVisualization({ data, colors }: VisualizationProps) {
  if (data.columns.length < 2 || data.rows.length === 0) {
    return <p className={styles.metricLabel}>No data to display</p>;
  }

  const pieData = data.rows.map((row) => ({
    name: String(row[0] ?? ''),
    value: Number(row[1]) || 0,
  }));

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { color: colors.chartText, fontFamily: 'inherit', fontSize: 11 },
    tooltip: {
      trigger: 'item',
      backgroundColor: colors.chartTooltipBg,
      borderColor: colors.chartTooltipBorder,
      textStyle: { color: colors.chartTooltipFg, fontSize: 12 },
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        data: pieData,
        label: {
          color: colors.chartTextSecondary,
          fontSize: 10,
        },
        emphasis: {
          label: { show: true, fontWeight: 'bold' },
        },
      },
    ],
  };

  return <ReactECharts option={option} style={{ height: 180 }} />;
}

function Visualization({
  type,
  data,
  colors,
}: {
  readonly type: VisualizationType;
  readonly data: QueryRunResponse;
  readonly colors: ReturnType<typeof useChartColors>;
}) {
  switch (type) {
    case 'bar':
      return <BarVisualization data={data} colors={colors} />;
    case 'line':
      return <LineVisualization data={data} colors={colors} />;
    case 'table':
      return <TableVisualization data={data} />;
    case 'stat':
      return <StatVisualization data={data} colors={colors} />;
    case 'pie':
      return <PieVisualization data={data} colors={colors} />;
  }
}

// ─── Inner component ────────────────────────────────────────────────────────

function CustomQueryWidgetInner({ config }: { readonly config: CustomWidgetConfig }) {
  const colors = useChartColors();
  const sql = config.inlineSql || '';

  const staleTime =
    config.refreshIntervalSeconds > 0 ? config.refreshIntervalSeconds * 1000 : 60_000;

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['custom-widget', config.id, sql],
    queryFn: () => runQuery({ sql }),
    staleTime,
    refetchInterval:
      config.refreshIntervalSeconds > 0 ? config.refreshIntervalSeconds * 1000 : false,
    enabled: sql.length > 0,
  });

  if (!sql) {
    return <p className={styles.metricLabel}>No query configured</p>;
  }

  if (isLoading) return <Spinner />;

  if (isError) {
    const message = error instanceof Error ? error.message : 'Query execution failed';
    return <ErrorBanner message={message} onRetry={() => void refetch()} />;
  }

  if (!data) {
    return <p className={styles.metricLabel}>No results</p>;
  }

  return (
    <div>
      <Visualization type={config.visualizationType} data={data} colors={colors} />
      <div className={styles.listItem}>
        <span className={styles.listLabel}>
          {data.row_count} row{data.row_count !== 1 ? 's' : ''} · {data.execution_ms}ms
        </span>
      </div>
    </div>
  );
}

// ─── Instance component (loaded by factory) ─────────────────────────────────

export function CustomQueryWidgetInstance({ widgetId }: { readonly widgetId: string }) {
  const config = useMemo(() => getCustomWidgetConfig(widgetId), [widgetId]);

  if (!config) {
    return <p className={styles.metricLabel}>Widget configuration not found</p>;
  }

  return <CustomQueryWidgetInner config={config} />;
}
