import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getHealthSummary } from '../../api/healthSignals';
import { MetricCard } from '../../components/primitives/MetricCard';
import { HealthTabBar } from './HealthTabBar';
import type { HealthTab } from './HealthTabBar';
import { RepoHealthPane } from './RepoHealthPane';
import { AccessIdentityPane } from './AccessIdentityPane';
import { LicensePane } from './LicensePane';
import { MaintenancePane } from './MaintenancePane';
import { WafInsightsPane } from './WafInsightsPane';
import { WAF_FINDINGS } from './healthData';
import styles from './Health.module.css';

export function HealthPage() {
  const [activeTab, setActiveTab] = useState<HealthTab>('repo-health');

  const { data: summary, isLoading } = useQuery({
    queryKey: ['health-signals', 'summary'],
    queryFn: getHealthSummary,
    staleTime: 60_000,
  });

  const totalFindings = summary
    ? summary.stale_repos +
      summary.pat_no_expiry +
      summary.pat_stale +
      summary.bypass_offenders +
      summary.ext_collab_elevated
    : 0;

  const evaluatedWafFindings = WAF_FINDINGS.filter((f) => f.evaluated).length;

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
        onTabChange={setActiveTab}
        findingsCount={totalFindings > 0 ? totalFindings : evaluatedWafFindings}
      />

      {activeTab === 'repo-health' && <RepoHealthPane />}
      {activeTab === 'access-identity' && <AccessIdentityPane />}
      {activeTab === 'license' && <LicensePane />}
      {activeTab === 'maintenance' && <MaintenancePane />}
      {activeTab === 'waf' && <WafInsightsPane />}
    </div>
  );
}
