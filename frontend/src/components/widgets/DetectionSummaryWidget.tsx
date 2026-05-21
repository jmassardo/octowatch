import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { listDetections } from '../../api/detections';
import { useOrg } from '../../hooks/useOrg';
import type { DetectionSeverity } from '../../types/detections';
import { ErrorBanner } from '../primitives/ErrorBanner';
import { Spinner } from '../primitives/Spinner';
import styles from './Widgets.module.css';

const SEVERITIES: readonly DetectionSeverity[] = ['critical', 'high', 'medium', 'low'];
const SEVERITY_COLORS: Record<DetectionSeverity, string> = {
  critical: 'var(--danger)',
  high: 'var(--severe)',
  medium: 'var(--attention)',
  low: 'var(--success)',
};

export function DetectionSummaryWidget() {
  const navigate = useNavigate();
  const { selectedOrg } = useOrg();
  const orgParam = selectedOrg || undefined;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['widget', 'detection-summary', selectedOrg],
    queryFn: () => listDetections({ status: 'open', org: orgParam, page_size: 100 }),
    staleTime: 60_000,
  });

  if (isLoading) {
    return <Spinner />;
  }

  if (isError || !data) {
    return (
      <ErrorBanner message="Failed to load detection summary" onRetry={() => void refetch()} />
    );
  }

  const counts = data.items.reduce<Record<DetectionSeverity, number>>(
    (acc, detection) => {
      acc[detection.severity] += 1;
      return acc;
    },
    { critical: 0, high: 0, medium: 0, low: 0 },
  );
  const max = Math.max(...Object.values(counts), 1);

  return (
    <>
      <div className={styles.metricRow}>
        <div>
          <div className={styles.metricValue}>{data.total}</div>
          <div className={styles.metricLabel}>open detections</div>
        </div>
        <button type="button" className={styles.actionLink} onClick={() => navigate('/threats')}>
          Review queue
        </button>
      </div>
      <div className={styles.list}>
        {SEVERITIES.map((severity) => (
          <button
            key={severity}
            type="button"
            className={styles.barRow}
            style={{ background: 'transparent', border: 'none', padding: 0, cursor: 'pointer' }}
            onClick={() => navigate(`/threats?severity=${severity}`)}
          >
            <span className={styles.barLabel} style={{ textTransform: 'capitalize' }}>
              {severity}
            </span>
            <div className={styles.barTrack}>
              <div
                className={styles.barFill}
                style={{
                  width:
                    counts[severity] > 0
                      ? `${Math.max(6, (counts[severity] / max) * 100)}%`
                      : '2px',
                  background: SEVERITY_COLORS[severity],
                }}
              />
            </div>
            <span className={styles.barValue}>{counts[severity]}</span>
          </button>
        ))}
      </div>
    </>
  );
}
