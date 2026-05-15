import styles from '../widgets/Widgets.module.css';

/** Compliance Status widget — framework adherence overview. */
export function ComplianceStatusWidget() {
  return (
    <div className={styles.inlineStats}>
      <div className={styles.inlineStat}>
        <strong>94%</strong>
        <span>SOC 2 controls</span>
      </div>
      <div className={styles.inlineStat}>
        <strong>87%</strong>
        <span>CIS Benchmarks</span>
      </div>
      <div className={styles.inlineStat}>
        <strong>91%</strong>
        <span>Custom policies</span>
      </div>
    </div>
  );
}
