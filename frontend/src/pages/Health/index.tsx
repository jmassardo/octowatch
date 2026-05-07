import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getHealthSummary, getWafFindings, getHealthScore } from '../../api/healthSignals';
import { useFeatures } from '../../hooks/useFeatures';
import { PageHeader } from '../../components/common/PageHeader';
import { MetricCard } from '../../components/primitives/MetricCard';
import { HealthTabBar } from './HealthTabBar';
import type { HealthTab } from './HealthTabBar';
import { RepoHealthPane } from './RepoHealthPane';
import { AccessIdentityPane } from './AccessIdentityPane';
import { LicensePane } from './LicensePane';
import { MaintenancePane } from './MaintenancePane';
import { WafInsightsPane } from './WafInsightsPane';
import { SecurityPosturePane } from './SecurityPosturePane';
import { AppGovernancePane } from './AppGovernancePane';
import { OpsHealthPane } from './OpsHealthPane';
import { ApiAbuseTab } from './ApiAbuseTab';
import { DormantUsersTab } from './DormantUsersTab';
import { SecurityTab } from './SecurityTab';
import { MaintenanceSignalsTab } from './MaintenanceSignalsTab';
import styles from './Health.module.css';

const SLUG_TO_TAB: Record<string, HealthTab> = {
  repos: 'repo-health',
  access: 'access-identity',
  security: 'security-posture',
  governance: 'app-governance',
  operations: 'operations',
  license: 'license',
  maintenance: 'maintenance',
  waf: 'waf',
  'api-abuse': 'api-abuse',
  users: 'dormant-users',
  'platform-security': 'platform-security',
  'maintenance-signals': 'maintenance-signals',
};

const TAB_TO_SLUG: Record<HealthTab, string> = Object.fromEntries(
  Object.entries(SLUG_TO_TAB).map(([slug, tab]) => [tab, slug]),
) as Record<HealthTab, string>;

function gradeColor(grade: string): string {
  switch (grade) {
    case 'A':
      return 'var(--success)';
    case 'B':
      return 'var(--accent)';
    case 'C':
      return 'var(--attention)';
    case 'D':
      return 'color-mix(in srgb, var(--attention) 70%, var(--danger))';
    default:
      return 'var(--danger)';
  }
}

export function HealthPage() {
  const { tab: tabSlug } = useParams<{ tab: string }>();
  const navigate = useNavigate();
  const { features } = useFeatures();

  const activeTab: HealthTab = SLUG_TO_TAB[tabSlug ?? 'repos'] ?? 'repo-health';

  const { data: summary } = useQuery({
    queryKey: ['health-signals', 'summary'],
    queryFn: getHealthSummary,
    staleTime: 60_000,
  });

  const { data: wafData } = useQuery({
    queryKey: ['health', 'waf-findings'],
    queryFn: getWafFindings,
    staleTime: 60_000,
  });

  const { data: scoreData } = useQuery({
    queryKey: ['health', 'score'],
    queryFn: getHealthScore,
    staleTime: 60_000,
  });

  if (!features.org_health) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--fg-muted)' }}>
        <h2>Org Health is disabled</h2>
        <p style={{ marginTop: '0.75rem' }}>
          Enable it in{' '}
          <Link to="/settings/features" style={{ color: 'var(--accent)' }}>
            Settings → Features
          </Link>
          .
        </p>
      </div>
    );
  }

  const totalFindings = summary
    ? summary.stale_repos +
      summary.pat_no_expiry +
      summary.pat_stale +
      summary.bypass_offenders +
      summary.ext_collab_elevated
    : 0;

  const evaluatedWafFindings = (wafData?.findings ?? []).filter(
    (f) => f.evaluated && (f.severity === 'critical' || f.severity === 'warning'),
  ).length;

  const score = scoreData?.score ?? 100;
  const grade = scoreData?.grade ?? 'A';
  const criticalCount = scoreData?.critical_count ?? 0;
  const highCount = scoreData?.high_count ?? 0;
  const mediumCount = scoreData?.medium_count ?? 0;
  const lowCount = scoreData?.low_count ?? 0;
  const totalSignals = scoreData?.total_signals ?? 0;
  const orgsMonitored = scoreData?.orgs_monitored ?? 0;

  return (
    <div className={styles.page}>
      <PageHeader
        title="Org Health"
        description="Monitor organization health signals and configuration drift"
      />

      {/* Health Score & Summary Strip */}
      <div className={styles.metricStrip}>
        <MetricCard
          value={`${score}`}
          label="Health Score"
          style={{
            borderLeft: `4px solid ${gradeColor(grade)}`,
          }}
          helpText={`Overall health score (0-100). Grade: ${grade}. Based on weighted signal severities.`}
        />
        <MetricCard
          value={String(totalSignals)}
          label="Total Signals"
          accent={totalSignals > 0}
          helpText="Combined count of all detected health signals across severity levels."
        />
        <MetricCard
          value={String(criticalCount)}
          label="Critical"
          accent={criticalCount > 0}
          helpText="Critical signals require immediate attention (-10 points each)."
        />
        <MetricCard
          value={String(highCount)}
          label="High"
          accent={highCount > 0}
          helpText="High severity signals (-5 points each)."
        />
        <MetricCard
          value={String(mediumCount)}
          label="Medium"
          helpText="Medium severity signals (-2 points each)."
        />
        <MetricCard
          value={String(lowCount)}
          label="Low"
          helpText="Low severity signals (-1 point each)."
        />
        <MetricCard
          value={String(orgsMonitored)}
          label="Orgs Monitored"
          helpText="Number of organizations included in health signal analysis."
        />
      </div>

      <HealthTabBar
        activeTab={activeTab}
        onTabChange={(newTab) => navigate(`/health/${TAB_TO_SLUG[newTab]}`)}
        findingsCount={totalFindings > 0 ? totalFindings : evaluatedWafFindings}
      />

      {activeTab === 'repo-health' && <RepoHealthPane />}
      {activeTab === 'access-identity' && <AccessIdentityPane />}
      {activeTab === 'security-posture' && <SecurityPosturePane />}
      {activeTab === 'app-governance' && <AppGovernancePane />}
      {activeTab === 'operations' && <OpsHealthPane />}
      {activeTab === 'license' && <LicensePane />}
      {activeTab === 'maintenance' && <MaintenancePane />}
      {activeTab === 'waf' && <WafInsightsPane />}
      {activeTab === 'api-abuse' && <ApiAbuseTab />}
      {activeTab === 'dormant-users' && <DormantUsersTab />}
      {activeTab === 'platform-security' && <SecurityTab />}
      {activeTab === 'maintenance-signals' && <MaintenanceSignalsTab />}
    </div>
  );
}
