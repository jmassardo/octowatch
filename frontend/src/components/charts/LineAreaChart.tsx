import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useChartColors } from '../../hooks/useChartColors';
import { describeLineAreaChart, chartToTableData } from '../../utils/chartA11y';

interface LineAreaChartProps {
  title?: string;
  xAxisData: string[];
  series: {
    name: string;
    data: number[];
    color?: string;
    dashed?: boolean;
    areaOpacity?: number;
  }[];
  height?: number;
  yAxisFormatter?: (v: number) => string;
}

export function LineAreaChart({
  title,
  xAxisData,
  series,
  height = 160,
  yAxisFormatter,
}: LineAreaChartProps) {
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
    series: series.map((s) => ({
      name: s.name,
      type: 'line' as const,
      smooth: true,
      data: s.data,
      lineStyle: {
        color: s.color ?? '#58a6ff',
        width: 2,
        type: s.dashed ? 'dashed' : 'solid',
      },
      itemStyle: { color: s.color ?? '#58a6ff' },
      symbol: 'none',
      areaStyle:
        s.areaOpacity !== undefined
          ? {
              color: {
                type: 'linear' as const,
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  {
                    offset: 0,
                    color: (s.color ?? '#58a6ff')
                      .replace(')', `, ${s.areaOpacity})`)
                      .replace('rgb', 'rgba'),
                  },
                  { offset: 1, color: 'transparent' },
                ],
              },
            }
          : undefined,
    })),
    ...(title
      ? { title: { text: title, textStyle: { color: colors.chartText, fontSize: 12, fontWeight: 500 } } }
      : {}),
  };

  const ariaLabel = describeLineAreaChart(title, xAxisData, series);
  const tableData = chartToTableData('Period', xAxisData, series);

  return (
    <div role="figure" aria-label={ariaLabel}>
      <ReactECharts option={option} style={{ height }} />
      <table className="sr-only">
        <caption>{title ?? 'Line chart data'}</caption>
        <thead>
          <tr>
            {tableData.headers.map((h) => (
              <th key={h} scope="col">{h}</th>
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
