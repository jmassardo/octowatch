import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';

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
      axisLabel: {
        color: '#6e7681',
        fontSize: 10,
        formatter: yAxisFormatter,
      },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#161b22',
      borderColor: '#30363d',
      textStyle: { color: '#e6edf3', fontSize: 12 },
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
      ? { title: { text: title, textStyle: { color: '#8b949e', fontSize: 12, fontWeight: 500 } } }
      : {}),
  };

  return <ReactECharts option={option} style={{ height }} />;
}
