import styles from '../widgets/Widgets.module.css';

/** Alert Trends widget — shows a placeholder trend summary. */
export function AlertTrendsWidget() {
  return (
    <div className={styles.inlineStats}>
      <div className={styles.inlineStat}>
        <strong>↑ 12%</strong>
        <span>Critical alerts (7d)</span>
      </div>
      <div className={styles.inlineStat}>
        <strong>↓ 5%</strong>
        <span>High alerts (7d)</span>
      </div>
      <div className={styles.inlineStat}>
        <strong>— 0%</strong>
        <span>Medium alerts (7d)</span>
      </div>
    </div>
  );
}
