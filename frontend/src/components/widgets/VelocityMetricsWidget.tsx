import styles from '../widgets/Widgets.module.css';

/** Velocity Metrics widget — development velocity indicators. */
export function VelocityMetricsWidget() {
  return (
    <div className={styles.inlineStats}>
      <div className={styles.inlineStat}>
        <strong>48</strong>
        <span>PRs merged (7d)</span>
      </div>
      <div className={styles.inlineStat}>
        <strong>6.2h</strong>
        <span>Avg. cycle time</span>
      </div>
      <div className={styles.inlineStat}>
        <strong>1.8h</strong>
        <span>Avg. review time</span>
      </div>
    </div>
  );
}
