import styles from '../widgets/Widgets.module.css';

/** MTTR Chart widget — mean time to resolve by severity. */
export function MttrChartWidget() {
  return (
    <div className={styles.inlineStats}>
      <div className={styles.inlineStat}>
        <strong>2.4h</strong>
        <span>Critical MTTR</span>
      </div>
      <div className={styles.inlineStat}>
        <strong>8.1h</strong>
        <span>High MTTR</span>
      </div>
      <div className={styles.inlineStat}>
        <strong>26h</strong>
        <span>Medium MTTR</span>
      </div>
    </div>
  );
}
