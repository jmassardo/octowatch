import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getSeatUtilizationReport, getCopilotSeatsReport } from '../../api/reports';
import { getCopilotAnomalies } from '../../api/copilotMetrics';
import type { SeatUtilizationBucket, CopilotSeatsBucket } from '../../types/reports';
import { useFeatures } from '../../hooks/useFeatures';
import { CopilotTabBar } from './CopilotTabBar';
import type { CopilotTab } from './CopilotTabBar';
import { PageHeader } from '../../components/common/PageHeader';
import { OverviewPane } from './OverviewPane';
import { AdoptionPane } from './AdoptionPane';
import { ModelsPane } from './ModelsPane';
import { LicensePane } from './LicensePane';
import { BillingPane } from './BillingPane';
import { AnomaliesPane } from './AnomaliesPane';
import styles from './Copilot.module.css';

const VALID_TABS: readonly CopilotTab[] = [
  'overview',
  'adoption',
  'models',
  'license',
  'billing',
  'anomalies',
];

export function CopilotPage() {
  const { tab } = useParams<{ tab: string }>();
  const navigate = useNavigate();
  const { features } = useFeatures();

  const activeTab: CopilotTab = VALID_TABS.includes(tab as CopilotTab)
    ? (tab as CopilotTab)
    : 'overview';

  const {
    isLoading: loadingSeatUtil,
    isError: seatUtilError,
    refetch: refetchSeatUtil,
    data: seatUtilData,
  } = useQuery({
    queryKey: ['reports', 'seat-util'],
    queryFn: () => getSeatUtilizationReport({ window_days: 30 }),
  });

  const { data: copilotData, isLoading: loadingCopilot } = useQuery({
    queryKey: ['reports', 'copilot-seats'],
    queryFn: () => getCopilotSeatsReport({ window_days: 30 }),
  });

  const { data: anomalyData } = useQuery({
    queryKey: ['copilot', 'anomalies'],
    queryFn: getCopilotAnomalies,
    staleTime: 30 * 60 * 1000,
  });

  if (!features.copilot_insights) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--fg-muted)' }}>
        <h2>Copilot Insights is disabled</h2>
        <p style={{ marginTop: '0.75rem' }}>
          Enable it in{' '}
          <Link to="/settings/features" style={{ color: 'var(--accent)' }}>
            Settings → Features
          </Link>{' '}
          to view Copilot metrics.
        </p>
      </div>
    );
  }

  const seatBuckets = (seatUtilData?.data ?? []) as unknown as SeatUtilizationBucket[];
  const copilotBuckets = (copilotData?.data ?? []) as unknown as CopilotSeatsBucket[];

  return (
    <div className={styles.page}>
      <PageHeader
        title="Copilot Insights"
        description="GitHub Copilot usage analytics and adoption metrics"
        showHelp
      />

      <CopilotTabBar
        activeTab={activeTab}
        onTabChange={(newTab) => navigate(`/copilot/${newTab}`)}
        anomalyCount={anomalyData?.anomalies?.length ?? 0}
      />

      {activeTab === 'overview' && (
        <OverviewPane
          seatBuckets={seatBuckets}
          copilotBuckets={copilotBuckets}
          isLoading={loadingSeatUtil || loadingCopilot}
          isError={seatUtilError}
          onRetry={() => void refetchSeatUtil()}
        />
      )}
      {activeTab === 'adoption' && <AdoptionPane />}
      {activeTab === 'models' && <ModelsPane />}
      {activeTab === 'license' && <LicensePane seatBuckets={seatBuckets} />}
      {activeTab === 'billing' && <BillingPane />}
      {activeTab === 'anomalies' && <AnomaliesPane />}
    </div>
  );
}
