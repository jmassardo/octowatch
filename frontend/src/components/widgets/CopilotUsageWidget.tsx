import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getCopilotAdoption } from '../../api/copilotMetrics';
import { MiniBarChart } from '../charts/MiniBarChart';
import { ErrorBanner } from '../primitives/ErrorBanner';
import { Spinner } from '../primitives/Spinner';
import styles from './Widgets.module.css';

export function CopilotUsageWidget() {
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['widget', 'copilot-usage'],
    queryFn: getCopilotAdoption,
    staleTime: 60_000,
  });

  if (isLoading) return <Spinner />;
  if (isError || !data) {
    return <ErrorBanner message="Failed to load Copilot usage" onRetry={() => void refetch()} />;
  }

  const tierCounts = data.tiers.map((tier) => tier.count);
  const topTier = [...data.tiers].sort((left, right) => right.count - left.count)[0];

  return (
    <>
      <div className={styles.metricRow}>
        <div>
          <div className={styles.metricValue}>{data.total_adoption.toFixed(1)}%</div>
          <div className={styles.metricLabel}>overall Copilot adoption</div>
        </div>
        <button type="button" className={styles.actionLink} onClick={() => navigate('/copilot')}>
          Open Copilot view
        </button>
      </div>
      <MiniBarChart data={tierCounts.length > 0 ? tierCounts : [0]} height={84} color="var(--done)" />
      <div className={styles.list}>
        <div className={styles.listItem}>
          <span className={styles.listLabel}>Largest cohort</span>
          <span className={styles.listValue}>{topTier ? topTier.label : 'No data'}</span>
        </div>
        <div className={styles.listItem}>
          <span className={styles.listLabel}>Power users</span>
          <span className={styles.listValue}>{data.power_users.length}</span>
        </div>
      </div>
    </>
  );
}
