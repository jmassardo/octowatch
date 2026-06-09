import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useChartColors } from '../../hooks/useChartColors';

interface DonutChartProps {
  data: { name: string; value: number; color?: string }[];
  height?: number;
  title?: string;
  onItemClick?: (name: string) => void;
}

export function DonutChart({ data, height = 240, title, onItemClick }: DonutChartProps) {
  const colors = useChartColors();

  const defaultColors = [
    colors.accent,
    colors.success,
    colors.done,
    colors.severe,
    colors.attention,
    colors.danger,
    '#79c0ff',
    '#56d364',
    '#d2a8ff',
    '#f0883e',
  ];

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { color: colors.chartText, fontFamily: 'inherit', fontSize: 11 },
    tooltip: {
      trigger: 'item',
      backgroundColor: colors.chartTooltipBg,
      borderColor: colors.chartTooltipBorder,
      textStyle: { color: colors.chartTooltipFg, fontSize: 12 },
      formatter: (params: unknown) => {
        const p = params as { name: string; value: number; percent: number };
        return `${p.name}: ${p.value} (${p.percent}%)`;
      },
    },
    legend: {
      orient: 'vertical',
      right: 10,
      top: 'center',
      textStyle: { color: colors.chartText, fontSize: 11 },
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
    },
    series: [
      {
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['35%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 4,
          borderColor: colors.chartBg || 'transparent',
          borderWidth: 2,
        },
        label: { show: false },
        emphasis: {
          label: {
            show: true,
            fontSize: 12,
            fontWeight: 'bold',
            color: colors.chartText,
          },
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.3)',
          },
        },
        data: data.map((item, i) => ({
          name: item.name,
          value: item.value,
          itemStyle: { color: item.color || defaultColors[i % defaultColors.length] },
        })),
      },
    ],
    ...(title
      ? {
          title: {
            text: title,
            textStyle: { color: colors.chartText, fontSize: 12, fontWeight: 500 },
            left: 'center',
          },
        }
      : {}),
  };

  const ariaLabel = title
    ? `${title}: ${data.map((d) => `${d.name} ${d.value}`).join(', ')}`
    : `Donut chart: ${data.map((d) => `${d.name} ${d.value}`).join(', ')}`;

  const onEvents = onItemClick
    ? {
        click: (params: { name: string }) => {
          onItemClick(params.name);
        },
      }
    : undefined;

  return (
    <div role="figure" aria-label={ariaLabel}>
      <ReactECharts option={option} style={{ height }} onEvents={onEvents} />
    </div>
  );
}
