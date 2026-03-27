import { Label } from '../../components/primitives/Label';
import { ANOMALIES } from './copilotData';
import styles from './Copilot.module.css';

const SEVERITY_VARIANT = {
  high: 'danger',
  medium: 'attention',
  low: 'muted',
} as const;

export function AnomaliesPane() {
  return (
    <>
      <div className={styles.insightNote}>
        {ANOMALIES.length} anomalies detected in the last 7 days based on usage pattern analysis
      </div>

      <div className={styles.anomalyList}>
        {ANOMALIES.map((anomaly) => (
          <div key={anomaly.id} className={styles.anomalyCard}>
            <div className={styles.anomalyHeader}>
              <Label variant={SEVERITY_VARIANT[anomaly.severity]}>
                {anomaly.severity.toUpperCase()}
              </Label>
              <span className={styles.anomalyTime}>{anomaly.timestamp}</span>
            </div>
            <div className={styles.anomalyTitle}>{anomaly.title}</div>
            <div className={styles.anomalyDesc}>{anomaly.description}</div>
            <div className={styles.anomalyMeta}>Team: {anomaly.team}</div>
          </div>
        ))}
      </div>
    </>
  );
}
