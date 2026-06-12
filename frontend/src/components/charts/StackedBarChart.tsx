import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useChartColors } from '../../hooks/useChartColors';
import { describeBarChart, chartToTableData } from '../../utils/chartA11y';

interface StackedBarChartProps {
  title?: string;
  xAxisData: string[];
  series: {
    name: string;
    data: number[];
    color?: string;
  }[];
  height?: number;
  yAxisFormatter?: (v: number) => string;
}

export function StackedBarChart({
  title,
  xAxisData,
  series,
  height = 200,
  yAxisFormatter,
}: StackedBarChartProps) {
  const colors = useChartColors();

  const resolveColor = (color: string | undefined, idx: number): string => {
    if (!color) {
      const palette = [
        colors.accent,
        colors.success,
        colors.attention,
        colors.done,
        colors.danger,
        '#a371f7',
        '#79c0ff',
        '#d2a8ff',
      ];
      return palette[idx % palette.length] || '#58a6ff';
    }
    const varMatch = color.match(/^var\(--(\w[\w-]*)\)$/);
    if (varMatch) {
      const resolved = getComputedStyle(document.documentElement)
        .getPropertyValue(`--${varMatch[1]}`)
        .trim();
      return resolved || colors.accent || '#58a6ff';
    }
    return color;
  };

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
      axisLabel: {
        color: colors.chartTextSecondary,
        fontSize: 10,
        formatter: yAxisFormatter,
      },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: colors.chartTooltipBg,
      borderColor: colors.chartTooltipBorder,
      textStyle: { color: colors.chartTooltipFg, fontSize: 12 },
    },
    series: series.map((s, idx) => ({
      name: s.name,
      type: 'bar' as const,
      stack: 'total',
      data: s.data,
      itemStyle: { color: resolveColor(s.color, idx), borderRadius: 0 },
      barMaxWidth: 28,
    })),
    legend: {
      bottom: 0,
      textStyle: { color: colors.chartTextSecondary, fontSize: 10 },
      itemWidth: 12,
      itemHeight: 8,
    },
    ...(title
      ? {
          title: {
            text: title,
            textStyle: { color: colors.chartText, fontSize: 12, fontWeight: 500 },
          },
        }
      : {}),
  };

  const ariaLabel = describeBarChart(title, xAxisData, series);
  const tableData = chartToTableData('Category', xAxisData, series);

  return (
    <div role="figure" aria-label={ariaLabel}>
      <ReactECharts option={option} style={{ height }} />
      <table className="sr-only">
        <caption>{title ?? 'Stacked bar chart data'}</caption>
        <thead>
          <tr>
            {tableData.headers.map((h) => (
              <th key={h} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tableData.rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
