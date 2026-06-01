import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useChartColors } from '../../hooks/useChartColors';
import { describeBarChart, chartToTableData } from '../../utils/chartA11y';

interface BarChartProps {
  title?: string;
  xAxisData: string[];
  series: {
    name: string;
    data: number[];
    color?: string;
  }[];
  height?: number;
}

export function BarChart({ title, xAxisData, series, height = 160 }: BarChartProps) {
  const colors = useChartColors();

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
    series: series.map((s) => ({
      name: s.name,
      type: 'bar' as const,
      data: s.data,
      itemStyle: { color: s.color ?? 'var(--accent)', borderRadius: [2, 2, 0, 0] },
      barMaxWidth: 28,
    })),
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
        <caption>{title ?? 'Bar chart data'}</caption>
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
