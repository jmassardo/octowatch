import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getHealthSummary, getWafFindings } from '../../api/healthSignals';
import { useFeatures } from '../../hooks/useFeatures';
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
};

const TAB_TO_SLUG: Record<HealthTab, string> = Object.fromEntries(
  Object.entries(SLUG_TO_TAB).map(([slug, tab]) => [tab, slug]),
) as Record<HealthTab, string>;

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

  if (!features.org_health) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--fg-muted)' }}>
        <h2>Org Health is disabled</h2>
        <p style={{ marginTop: '0.75rem' }}>
          Enable it in <a href="/settings/features" style={{ color: 'var(--accent)' }}>Settings → Features</a>.
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

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Org Health</div>
      <div className={styles.pageSub}>
        Audit-log-derived health signals across repositories, access, licenses, and GitHub
        Well-Architected Framework alignment
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
    </div>
  );
}
