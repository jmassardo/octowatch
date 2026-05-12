import { useCallback, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { PageHeader } from '../../components/common/PageHeader';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { getComplianceSummary } from '../../api/compliance';
import { OverviewPane } from './OverviewPane';
import { FrameworkPane } from './FrameworkPane';
import { GDPRPane } from './GDPRPane';
import { PolicyChecksPane } from './PolicyChecksPane';
import { useEnumQueryParam } from '../../hooks/useQueryParam';
import type { ComplianceTab } from '../../types/compliance';
import styles from './Compliance.module.css';

const TAB_KEYS = ['overview', 'soc2', 'iso27001', 'nist_csf', 'gdpr', 'policy'] as const;

const TABS: { key: ComplianceTab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'soc2', label: 'SOC 2' },
  { key: 'iso27001', label: 'ISO 27001' },
  { key: 'nist_csf', label: 'NIST CSF' },
  { key: 'gdpr', label: 'GDPR' },
  { key: 'policy', label: 'Policy Checks' },
];

export function CompliancePage() {
  const [activeTab, setActiveTab] = useEnumQueryParam('tab', TAB_KEYS, 'overview');
  const [isGenerating, setIsGenerating] = useState(false);
  const queryClient = useQueryClient();

  const {
    data: summary,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['compliance', 'summary'],
    queryFn: () => getComplianceSummary(),
    staleTime: 120_000,
  });

  const handleSelectFramework = useCallback((name: string) => {
    const tabMap: Record<string, ComplianceTab> = {
      soc2: 'soc2',
      iso27001: 'iso27001',
      nist_csf: 'nist_csf',
      gdpr: 'gdpr',
    };
    const tab = tabMap[name];
    if (tab) {
      setActiveTab(tab);
    }
  }, [setActiveTab]);

  const handleGenerateAll = useCallback(() => {
    setIsGenerating(true);
    // Invalidate all compliance queries to trigger re-fetch
    queryClient
      .invalidateQueries({ queryKey: ['compliance'] })
      .then(() => {
        setIsGenerating(false);
      })
      .catch(() => {
        setIsGenerating(false);
      });
  }, [queryClient]);

  if (isLoading) {
    return (
      <div className={styles.compliancePage}>
        <PageHeader
          title="Compliance Center"
          description="Track compliance posture across security frameworks"
          showHelp
        />
        <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
          <Spinner size={32} />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.compliancePage}>
        <PageHeader
          title="Compliance Center"
          description="Track compliance posture across security frameworks"
          showHelp
        />
        <ErrorBanner message="Failed to load compliance data" onRetry={() => refetch()} />
      </div>
    );
  }

  const lastDate = summary?.last_assessment_date
    ? new Date(summary.last_assessment_date).toLocaleDateString()
    : '—';

  return (
    <div className={styles.compliancePage}>
      <PageHeader
        title="Compliance Center"
        description="Track compliance posture across security frameworks"
        showHelp
      />

      {/* Summary Strip */}
      <div className={styles.summaryStrip}>
        <MetricCard
          value={summary ? `${summary.overall_score}%` : '—'}
          label="Overall Score"
          accent
          helpText="Weighted average compliance score across all frameworks"
        />
        <MetricCard
          value={summary ? String(summary.frameworks_tracked) : '—'}
          label="Frameworks Tracked"
          helpText="Number of compliance frameworks being monitored"
        />
        <MetricCard
          value={summary ? `${summary.controls_passing} / ${summary.controls_total}` : '—'}
          label="Controls Passing"
          helpText="Number of controls with evidence collected"
        />
        <MetricCard
          value={summary ? String(summary.critical_gaps) : '—'}
          label="Critical Gaps"
          helpText="Controls without evidence or failing"
        />
        <MetricCard
          value={lastDate}
          label="Last Assessment"
          helpText="Date of most recent assessment"
        />
      </div>

      {/* Tab Bar */}
      <div className={styles.tabBar} role="tablist" aria-label="Compliance tabs">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={`${styles.tab} ${activeTab === tab.key ? styles.tabActive : ''}`}
            onClick={() => setActiveTab(tab.key)}
            role="tab"
            aria-selected={activeTab === tab.key}
            aria-controls={`tabpanel-${tab.key}`}
            id={`tab-${tab.key}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div
        className={styles.tabContent}
        role="tabpanel"
        id={`tabpanel-${activeTab}`}
        aria-labelledby={`tab-${activeTab}`}
      >
        {activeTab === 'overview' && (
          <OverviewPane
            summary={summary}
            onSelectFramework={handleSelectFramework}
            onGenerateAll={handleGenerateAll}
            isGenerating={isGenerating}
          />
        )}
        {activeTab === 'soc2' && <FrameworkPane frameworkName="soc2" />}
        {activeTab === 'iso27001' && <FrameworkPane frameworkName="iso27001" />}
        {activeTab === 'nist_csf' && <FrameworkPane frameworkName="nist_csf" />}
        {activeTab === 'gdpr' && <GDPRPane />}
        {activeTab === 'policy' && <PolicyChecksPane />}
      </div>
    </div>
  );
}
