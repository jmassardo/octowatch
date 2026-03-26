import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';

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
  const option: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { color: '#8b949e', fontFamily: 'inherit', fontSize: 11 },
    grid: { left: 8, right: 8, top: 20, bottom: 20, containLabel: true },
    xAxis: {
      type: 'category',
      data: xAxisData,
      axisLine: { lineStyle: { color: '#30363d' } },
      axisTick: { show: false },
      axisLabel: { color: '#6e7681', fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#21262d' } },
      axisLabel: { color: '#6e7681', fontSize: 10 },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#161b22',
      borderColor: '#30363d',
      textStyle: { color: '#e6edf3', fontSize: 12 },
    },
    series: series.map((s) => ({
      name: s.name,
      type: 'bar' as const,
      data: s.data,
      itemStyle: { color: s.color ?? '#58a6ff', borderRadius: [2, 2, 0, 0] },
      barMaxWidth: 28,
    })),
    ...(title ? { title: { text: title, textStyle: { color: '#8b949e', fontSize: 12, fontWeight: 500 } } } : {}),
  };

  return <ReactECharts option={option} style={{ height }} />;
}
