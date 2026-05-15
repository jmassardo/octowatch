import styles from '../widgets/Widgets.module.css';

/** Posture Score widget — overall security posture. */
export function PostureScoreWidget() {
  return (
    <div className={styles.metricRow}>
      <div>
        <div className={styles.metricValue}>82</div>
        <div className={styles.metricLabel}>posture score</div>
      </div>
      <span className={`${styles.statusPill} ${styles.statusHealthy}`}>Healthy</span>
    </div>
  );
}
