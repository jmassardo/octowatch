import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getSeatUtilizationReport, getCopilotSeatsReport } from '../../api/reports';
import type { SeatUtilizationBucket, CopilotSeatsBucket } from '../../types/reports';
import { CopilotTabBar } from './CopilotTabBar';
import type { CopilotTab } from './CopilotTabBar';
import { OverviewPane } from './OverviewPane';
import { AdoptionPane } from './AdoptionPane';
import { ModelsPane } from './ModelsPane';
import { LicensePane } from './LicensePane';
import { AnomaliesPane } from './AnomaliesPane';
import { ANOMALIES } from './copilotData';
import styles from './Copilot.module.css';

export function CopilotPage() {
  const [activeTab, setActiveTab] = useState<CopilotTab>('overview');

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
        onTabChange={setActiveTab}
        anomalyCount={ANOMALIES.length}
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

