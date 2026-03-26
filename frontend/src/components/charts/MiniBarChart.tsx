interface MiniBarChartProps {
  data: number[];
  color?: string;
  height?: number;
  className?: string;
}

export function MiniBarChart({ data, color = 'var(--success)', height = 24, className }: MiniBarChartProps) {
  const max = Math.max(...data, 1);
  return (
    <div
      className={className}
      style={{
        display: 'flex',
        alignItems: 'flex-end',
        gap: 2,
        height,
      }}
    >
      {data.map((v, i) => (
        <div
          key={i}
          style={{
            width: 10,
            height: Math.max(3, (v / max) * height),
            borderRadius: 2,
            background: color,
          }}
        />
      ))}
    </div>
  );
}
