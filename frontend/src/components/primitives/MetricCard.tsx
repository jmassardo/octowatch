import { useNavigate } from 'react-router-dom';
import styles from './MetricCard.module.css';

interface MetricCardProps {
  value: string;
  label: string;
  delta?: string;
  deltaDir?: 'up' | 'down' | 'neutral';
  accent?: boolean;
  className?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
  to?: string;
}

/** Internal presentational card — does NOT use router hooks. */
function MetricCardBase({ value, label, delta, deltaDir = 'neutral', accent, className, style, onClick }: Omit<MetricCardProps, 'to'>) {
  const isClickable = !!onClick;

  return (
    <div
      className={[styles.metric, accent && styles.accented, isClickable && styles.clickable, className].filter(Boolean).join(' ')}
      style={style}
      onClick={isClickable ? onClick : undefined}
      role={isClickable ? 'button' : undefined}
      aria-label={isClickable ? label : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={isClickable ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } } : undefined}
    >
      {isClickable && <span className={styles.arrow} aria-hidden="true">→</span>}
      <div className={styles.val}>{value}</div>
      <div className={styles.lbl}>{label}</div>
      {delta && (
        <div className={[styles.delta, styles[deltaDir]].join(' ')}>{delta}</div>
      )}
    </div>
  );
}

/** Wrapper that adds router navigation when `to` is provided. */
function MetricCardWithNav({ to, onClick, ...rest }: MetricCardProps) {
  const navigate = useNavigate();

  function handleClick() {
    if (to) {
      navigate(to);
    }
    onClick?.();
  }

  return <MetricCardBase {...rest} onClick={handleClick} />;
}

export function MetricCard(props: MetricCardProps) {
  if (props.to) {
    return <MetricCardWithNav {...props} />;
  }
  return <MetricCardBase {...props} />;
}
