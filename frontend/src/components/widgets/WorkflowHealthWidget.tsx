import styles from '../widgets/Widgets.module.css';

/** Workflow Health widget — GitHub Actions workflow success rates. */
export function WorkflowHealthWidget() {
  return (
    <div className={styles.inlineStats}>
      <div className={styles.inlineStat}>
        <strong>96.2%</strong>
        <span>Success rate (7d)</span>
      </div>
      <div className={styles.inlineStat}>
        <strong>142</strong>
        <span>Runs today</span>
      </div>
      <div className={styles.inlineStat}>
        <strong>4m 12s</strong>
        <span>Avg. duration</span>
      </div>
    </div>
  );
}
