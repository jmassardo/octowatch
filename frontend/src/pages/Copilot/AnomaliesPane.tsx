import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Label } from '../../components/primitives/Label';
import { Modal } from '../../components/primitives/Modal';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { getCopilotAnomalies } from '../../api/copilotMetrics';
import styles from './Copilot.module.css';

const SEVERITY_VARIANT = {
  high: 'danger',
  medium: 'attention',
  low: 'muted',
} as const;

type SeverityFilter = 'high' | 'medium' | 'low' | null;

export function AnomaliesPane() {
  const {
    data: anomalyData,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['copilot', 'anomalies'],
    queryFn: getCopilotAnomalies,
    staleTime: 30 * 60 * 1000,
  });
  const anomalies = anomalyData?.anomalies ?? [];

  const anomalyListRef = useRef<HTMLDivElement>(null);
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>(null);
  const [teamModal, setTeamModal] = useState<string | null>(null);

  function handleCountClick() {
    if (anomalyListRef.current) {
      anomalyListRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }

  function handleSeverityClick(severity: 'high' | 'medium' | 'low') {
    setSeverityFilter((prev) => (prev === severity ? null : severity));
  }

  const filteredAnomalies = severityFilter
    ? anomalies.filter((a) => a.severity === severityFilter)
    : anomalies;

  const selectedAnomaly = teamModal ? anomalies.find((a) => a.team === teamModal) : null;

  return (
    <>
      {anomalyData?.error && (
        <SampleDataBanner message={anomalyData.message ?? 'Anomaly data is unavailable.'} />
      )}

      {isError && (
        <ErrorBanner message="Failed to load anomaly data" onRetry={() => void refetch()} />
      )}
      {isLoading && <Spinner />}

      {!isLoading && !isError && anomalies.length === 0 && !anomalyData?.error && (
        <div className={styles.insightNote} style={{ textAlign: 'center', padding: '32px 0' }}>
          ✅ No anomalies detected. This is a good sign!
        </div>
      )}

      {!isLoading && !isError && anomalies.length > 0 && (
        <>
          <div className={styles.insightNote}>
            <span
              className={styles.anomalyCountClickable}
              role="button"
              tabIndex={0}
              onClick={handleCountClick}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  handleCountClick();
                }
              }}
            >
              {anomalies.length} anomalies
            </span>{' '}
            detected in the last 7 days based on usage pattern analysis
            {severityFilter && (
              <span style={{ marginLeft: 8, fontSize: 11 }}>
                (filtered: {severityFilter}){' '}
                <span
                  className={styles.clickableStat}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSeverityFilter(null)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSeverityFilter(null);
                    }
                  }}
                  style={{ fontSize: 11 }}
                >
                  clear
                </span>
              </span>
            )}
          </div>

          <div className={styles.anomalyList} ref={anomalyListRef}>
            {filteredAnomalies.map((anomaly) => (
              <div key={anomaly.id} className={styles.anomalyCard}>
                <div className={styles.anomalyHeader}>
                  <span
                    className={styles.severityBadgeClickable}
                    role="button"
                    tabIndex={0}
                    onClick={() => handleSeverityClick(anomaly.severity)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        handleSeverityClick(anomaly.severity);
                      }
                    }}
                  >
                    <Label variant={SEVERITY_VARIANT[anomaly.severity]}>
                      {anomaly.severity.toUpperCase()}
                    </Label>
                  </span>
                  <span className={styles.anomalyTime}>{anomaly.timestamp}</span>
                </div>
                <div className={styles.anomalyTitle}>{anomaly.title}</div>
                <div className={styles.anomalyDesc}>{anomaly.description}</div>
                <div className={styles.anomalyMeta}>
                  Team:{' '}
                  <span
                    className={styles.anomalyTeamClickable}
                    role="button"
                    tabIndex={0}
                    onClick={() => setTeamModal(anomaly.team)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setTeamModal(anomaly.team);
                      }
                    }}
                  >
                    {anomaly.team}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Team anomaly context modal */}
          <Modal
            open={teamModal !== null}
            onClose={() => setTeamModal(null)}
            title={teamModal ? `${teamModal} team — anomaly context` : 'Team context'}
            width={520}
          >
            {selectedAnomaly && (
              <div>
                <table className={styles.modalTable}>
                  <thead>
                    <tr>
                      <th>Detail</th>
                      <th>Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td style={{ color: 'var(--fg-muted)' }}>Team</td>
                      <td style={{ fontWeight: 500 }}>{selectedAnomaly.team}</td>
                    </tr>
                    <tr>
                      <td style={{ color: 'var(--fg-muted)' }}>Anomaly</td>
                      <td>{selectedAnomaly.title}</td>
                    </tr>
                    <tr>
                      <td style={{ color: 'var(--fg-muted)' }}>Severity</td>
                      <td>{selectedAnomaly.severity.toUpperCase()}</td>
                    </tr>
                    <tr>
                      <td style={{ color: 'var(--fg-muted)' }}>Detected</td>
                      <td>{selectedAnomaly.timestamp}</td>
                    </tr>
                  </tbody>
                </table>
                <p
                  style={{
                    fontSize: 13,
                    color: 'var(--fg-muted)',
                    lineHeight: 1.6,
                    margin: '12px 0 0',
                  }}
                >
                  {selectedAnomaly.description}
                </p>
                <p
                  style={{
                    fontSize: 13,
                    color: 'var(--fg-muted)',
                    lineHeight: 1.6,
                    margin: '12px 0 0',
                  }}
                >
                  Team-level Copilot usage trends, member-specific breakdowns, and historical
                  anomaly patterns require the Copilot Metrics API integration.
                </p>
              </div>
            )}
          </Modal>
        </>
      )}
    </>
  );
}
