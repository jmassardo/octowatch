import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useChartColors } from '../../hooks/useChartColors';
import { describeBarChart, chartToTableData } from '../../utils/chartA11y';

interface HorizontalBarChartProps {
  title?: string;
  categories: string[];
  series: {
    name: string;
    data: number[];
    color?: string;
  }[];
  height?: number;
  xAxisFormatter?: (v: number) => string;
}

export function HorizontalBarChart({
  title,
  categories,
  series,
  height = 200,
  xAxisFormatter,
}: HorizontalBarChartProps) {
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
    grid: { left: 8, right: 16, top: 20, bottom: 20, containLabel: true },
    yAxis: {
      type: 'category',
      data: categories,
      axisLine: { lineStyle: { color: colors.chartGrid } },
      axisTick: { show: false },
      axisLabel: { color: colors.chartTextSecondary, fontSize: 10 },
    },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: colors.chartGrid } },
      axisLabel: {
        color: colors.chartTextSecondary,
        fontSize: 10,
        formatter: xAxisFormatter,
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
      data: s.data,
      itemStyle: { color: resolveColor(s.color, idx), borderRadius: [0, 2, 2, 0] },
      barMaxWidth: 20,
    })),
    ...(series.length > 1
      ? {
          legend: {
            bottom: 0,
            textStyle: { color: colors.chartTextSecondary, fontSize: 10 },
            itemWidth: 12,
            itemHeight: 8,
          },
        }
      : {}),
    ...(title
      ? {
          title: {
            text: title,
            textStyle: { color: colors.chartText, fontSize: 12, fontWeight: 500 },
          },
        }
      : {}),
  };

  const ariaLabel = describeBarChart(title, categories, series);
  const tableData = chartToTableData('Category', categories, series);

  return (
    <div role="figure" aria-label={ariaLabel}>
      <ReactECharts option={option} style={{ height }} />
      <table className="sr-only">
        <caption>{title ?? 'Horizontal bar chart data'}</caption>
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
