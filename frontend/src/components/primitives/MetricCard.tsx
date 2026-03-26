import styles from './MetricCard.module.css';

interface MetricCardProps {
  value: string;
  label: string;
  delta?: string;
  deltaDir?: 'up' | 'down' | 'neutral';
  accent?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

export function MetricCard({ value, label, delta, deltaDir = 'neutral', accent, className, style }: MetricCardProps) {
  return (
    <div className={[styles.metric, accent && styles.accented, className].filter(Boolean).join(' ')} style={style}>
      <div className={styles.val}>{value}</div>
      <div className={styles.lbl}>{label}</div>
      {delta && (
        <div className={[styles.delta, styles[deltaDir]].join(' ')}>{delta}</div>
      )}
    </div>
  );
}
