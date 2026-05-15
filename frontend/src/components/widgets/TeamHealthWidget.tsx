import styles from '../widgets/Widgets.module.css';

/** Team Health widget — aggregated team health indicators. */
export function TeamHealthWidget() {
  return (
    <div className={styles.inlineStats}>
      <div className={styles.inlineStat}>
        <strong>8/10</strong>
        <span>Teams healthy</span>
      </div>
      <div className={styles.inlineStat}>
        <strong>1</strong>
        <span>Needs attention</span>
      </div>
      <div className={styles.inlineStat}>
        <strong>1</strong>
        <span>At risk</span>
      </div>
    </div>
  );
}
