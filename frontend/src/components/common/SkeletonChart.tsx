import styles from './Skeleton.module.css';

interface SkeletonChartProps {
  /** Number of bars. Default 8. */
  bars?: number;
  className?: string;
}

/**
 * Animated skeleton placeholder that mimics a bar chart.
 *
 * Respects `prefers-reduced-motion` by disabling animation.
 */
export function SkeletonChart({ bars = 8, className }: SkeletonChartProps) {
  const heights = Array.from({ length: bars }, (_, i) => 30 + ((i * 37 + 13) % 70));

  return (
    <div
      className={[styles.chartWrap, className].filter(Boolean).join(' ')}
      aria-hidden="true"
      role="presentation"
    >
      {heights.map((h, i) => (
        <div
          key={i}
          className={`${styles.skeleton} ${styles.chartBar}`}
          style={{ height: `${h}%` }}
        />
      ))}
    </div>
  );
}
