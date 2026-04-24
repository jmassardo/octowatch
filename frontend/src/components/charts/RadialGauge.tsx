interface RadialGaugeProps {
  value: number;
  label: string;
  color?: string;
  size?: number;
}

function describeArc(
  cx: number,
  cy: number,
  r: number,
  startAngleDeg: number,
  endAngleDeg: number,
): string {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const x1 = cx + r * Math.cos(toRad(startAngleDeg));
  const y1 = cy + r * Math.sin(toRad(startAngleDeg));
  const x2 = cx + r * Math.cos(toRad(endAngleDeg));
  const y2 = cy + r * Math.sin(toRad(endAngleDeg));
  const largeArc = endAngleDeg - startAngleDeg > 180 ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`;
}

export function RadialGauge({ value, label, color, size = 140 }: RadialGaugeProps) {
  const clampedValue = Math.max(0, Math.min(100, value));

  const resolvedColor =
    color ??
    (clampedValue < 50
      ? 'var(--danger)'
      : clampedValue < 75
        ? 'var(--attention)'
        : 'var(--accent)');

  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.38;
  const strokeWidth = size * 0.08;

  const startAngle = 180;
  const endAngle = 360;
  const fillAngle = startAngle + (clampedValue / 100) * 180;
  const valueFontSize = size * 0.22;
  const labelFontSize = Math.max(11, size * 0.1);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 4,
      }}
      role="img"
      aria-label={`${label}: ${clampedValue.toFixed(0)}%`}
    >
      <svg width={size} height={size * 0.6} viewBox={`0 0 ${size} ${size * 0.6}`}>
        {/* Track */}
        <path
          d={describeArc(cx, cy * 0.95, r, startAngle, endAngle)}
          fill="none"
          stroke="var(--border-default, #30363d)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />
        {/* Fill */}
        {clampedValue > 0 && (
          <path
            d={describeArc(cx, cy * 0.95, r, startAngle, fillAngle)}
            fill="none"
            stroke={resolvedColor}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            style={{ transition: 'stroke-dasharray 0.5s ease' }}
          />
        )}
        {/* Value text */}
        <text
          x={cx}
          y={size * 0.52}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={valueFontSize}
          fontWeight="700"
          fill="var(--fg-default, #e6edf3)"
        >
          {clampedValue.toFixed(0)}%
        </text>
      </svg>
      <div
        style={{
          fontSize: labelFontSize,
          color: 'var(--fg-muted, #8b949e)',
          textAlign: 'center',
          lineHeight: 1.3,
          maxWidth: size,
        }}
      >
        {label}
      </div>
    </div>
  );
}
