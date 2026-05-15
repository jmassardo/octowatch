import styles from '../widgets/Widgets.module.css';

/** Failure Rates widget — CI/CD pipeline failure rate indicators. */
export function FailureRatesWidget() {
  return (
    <div className={styles.inlineStats}>
      <div className={styles.inlineStat}>
        <strong>3.8%</strong>
        <span>Overall failure rate</span>
      </div>
      <div className={styles.inlineStat}>
        <strong>7</strong>
        <span>Failed runs today</span>
      </div>
      <div className={styles.inlineStat}>
        <strong>2</strong>
        <span>Flaky workflows</span>
      </div>
    </div>
  );
}
