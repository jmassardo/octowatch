import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getSeatUtilizationReport } from '../../api/reports';
import { getCopilotAnomalies } from '../../api/copilotMetrics';
import type { SeatUtilizationBucket } from '../../types/reports';
import { useFeatures } from '../../hooks/useFeatures';
import { useOrg } from '../../hooks/useOrg';
import { CopilotTabBar } from './CopilotTabBar';
import type { CopilotTab } from './CopilotTabBar';
import { PageHeader } from '../../components/common/PageHeader';
import { OverviewPane } from './OverviewPane';
import { ActivityPane } from './ActivityPane';
import { AdoptionPane } from './AdoptionPane';
import { TeamsPane } from './TeamsPane';
import { ChatMetricsPane } from './ChatMetricsPane';
import { LanguageBreakdownPane } from './LanguageBreakdownPane';
import { ModelsPane } from './ModelsPane';
import { LicensePane } from './LicensePane';
import { BillingPane } from './BillingPane';
import { ROIPane } from './ROIPane';
import { PRMetricsPane } from './PRMetricsPane';
import { AgentActivityPane } from './AgentActivityPane';
import { BlockersPane } from './BlockersPane';
import { PolicyPane } from './PolicyPane';
import { GovernancePane } from './GovernancePane';
import { AnomaliesPane } from './AnomaliesPane';
import styles from './Copilot.module.css';

const VALID_TABS: readonly CopilotTab[] = [
  'overview',
  'activity',
  'adoption',
  'teams',
  'chat',
  'languages',
  'models',
  'prs',
  'agent',
  'license',
  'billing',
  'roi',
  'blockers',
  'policy',
  'governance',
  'anomalies',
];

export function CopilotPage() {
  const { tab } = useParams<{ tab: string }>();
  const navigate = useNavigate();
  const { features } = useFeatures();
  const { selectedOrg } = useOrg();
  const orgParam = selectedOrg || undefined;

  const activeTab: CopilotTab = VALID_TABS.includes(tab as CopilotTab)
    ? (tab as CopilotTab)
    : 'overview';

  const {
    isLoading: loadingSeatUtil,
    isError: seatUtilError,
    refetch: refetchSeatUtil,
    data: seatUtilData,
  } = useQuery({
    queryKey: ['reports', 'seat-util', orgParam],
    queryFn: () => getSeatUtilizationReport({ window_days: 30, org: orgParam }),
  });

  const { data: anomalyData } = useQuery({
    queryKey: ['copilot', 'anomalies', orgParam],
    queryFn: () => getCopilotAnomalies(orgParam),
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
          isLoading={loadingSeatUtil}
          isError={seatUtilError}
          onRetry={() => void refetchSeatUtil()}
        />
      )}
      {activeTab === 'activity' && <ActivityPane />}
      {activeTab === 'adoption' && <AdoptionPane />}
      {activeTab === 'teams' && <TeamsPane />}
      {activeTab === 'chat' && <ChatMetricsPane />}
      {activeTab === 'languages' && <LanguageBreakdownPane />}
      {activeTab === 'models' && <ModelsPane />}
      {activeTab === 'prs' && <PRMetricsPane />}
      {activeTab === 'agent' && <AgentActivityPane />}
      {activeTab === 'license' && <LicensePane seatBuckets={seatBuckets} />}
      {activeTab === 'billing' && <BillingPane />}
      {activeTab === 'roi' && <ROIPane />}
      {activeTab === 'blockers' && <BlockersPane />}
      {activeTab === 'policy' && <PolicyPane />}
      {activeTab === 'governance' && <GovernancePane />}
      {activeTab === 'anomalies' && <AnomaliesPane />}
    </div>
  );
}
