import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getHealthSummary, getWafFindings } from '../../api/healthSignals';
import { useFeatures } from '../../hooks/useFeatures';
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

  const { data: summary, isLoading } = useQuery({
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

      <div className={styles.dataSourceNote}>
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="currentColor"
          aria-hidden="true"
          style={{ flexShrink: 0, marginTop: 1 }}
        >
          <path d="M0 8a8 8 0 1116 0A8 8 0 010 8zm8-6.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM6.5 7.75A.75.75 0 017.25 7h1a.75.75 0 01.75.75v2.75h.25a.75.75 0 010 1.5h-2a.75.75 0 010-1.5h.25v-2h-.25a.75.75 0 01-.75-.75zM8 6a1 1 0 110-2 1 1 0 010 2z" />
        </svg>
        <span>
          Health signals are derived exclusively from GitHub audit log events. No GitHub API polling
          is performed. Some signals require a one-time baseline import from Settings →
          Integrations.
        </span>
      </div>

      <div className={styles.metricStrip}>
        <MetricCard
          value={isLoading ? '…' : String(summary?.stale_repos ?? 0)}
          label="Stale Repos"
        />
        <MetricCard
          value={isLoading ? '…' : String(summary?.pat_no_expiry ?? 0)}
          label="PATs Without Expiry"
        />
        <MetricCard
          value={isLoading ? '…' : String(summary?.bypass_offenders ?? 0)}
          label="Bypass Offenders"
        />
        <MetricCard
          value={isLoading ? '…' : String(summary?.ext_collab_total ?? 0)}
          label="External Collaborators"
        />
        <MetricCard
          value={isLoading ? '…' : String(summary?.ext_collab_elevated ?? 0)}
          label="Elevated Collaborators"
          accent
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
    </div>
  );
}
