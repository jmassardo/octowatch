import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getSeatUtilizationReport, getCopilotSeatsReport } from '../../api/reports';
import { getCopilotAnomalies } from '../../api/copilotMetrics';
import type { SeatUtilizationBucket, CopilotSeatsBucket } from '../../types/reports';
import { CopilotTabBar } from './CopilotTabBar';
import type { CopilotTab } from './CopilotTabBar';
import { OverviewPane } from './OverviewPane';
import { AdoptionPane } from './AdoptionPane';
import { ModelsPane } from './ModelsPane';
import { LicensePane } from './LicensePane';
import { AnomaliesPane } from './AnomaliesPane';
import styles from './Copilot.module.css';

const VALID_TABS: readonly CopilotTab[] = ['overview', 'adoption', 'models', 'license', 'anomalies'];

export function CopilotPage() {
  const { tab } = useParams<{ tab: string }>();
  const navigate = useNavigate();

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
    staleTime: 300_000,
  });

  const seatBuckets = (seatUtilData?.data ?? []) as unknown as SeatUtilizationBucket[];
  const copilotBuckets = (copilotData?.data ?? []) as unknown as CopilotSeatsBucket[];

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Copilot Insights</div>
      <div className={styles.pageSub}>
        GitHub Copilot adoption, seat utilization, and correlation with delivery outcomes
      </div>

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
      {activeTab === 'anomalies' && <AnomaliesPane />}
    </div>
  );
}

