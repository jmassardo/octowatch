import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { getAppGovernance, getCodeScanning, getVulnerabilities } from '../../api/healthSignals';
import styles from './AppGovernancePane.module.css';

/* ---------- main pane ---------- */

export function AppGovernancePane() {
  const appQuery = useQuery({
    queryKey: ['health', 'app-governance'],
    queryFn: getAppGovernance,
    staleTime: 60_000,
  });

  const codeScanQuery = useQuery({
    queryKey: ['health', 'code-scanning'],
    queryFn: getCodeScanning,
    staleTime: 60_000,
  });

  const vulnQuery = useQuery({
    queryKey: ['health', 'vulnerabilities'],
    queryFn: getVulnerabilities,
    staleTime: 60_000,
  });

  const isLoading = appQuery.isLoading || codeScanQuery.isLoading || vulnQuery.isLoading;
  const isError = appQuery.isError || codeScanQuery.isError || vulnQuery.isError;

  if (isLoading) {
    return (
      <div className={styles.centered}>
        <Spinner size={28} />
      </div>
    );
  }

  if (isError) {
    const retryAll = () => {
      void appQuery.refetch();
      void codeScanQuery.refetch();
      void vulnQuery.refetch();
    };
    return <ErrorBanner message="Failed to load app governance data" onRetry={retryAll} />;
  }

  const app = appQuery.data;
  const codeScan = codeScanQuery.data;
  const vuln = vulnQuery.data;

  return (
    <div className={styles.pane}>
      {/* OAuth & App Summary (90d) */}
      <div>
        <div className={styles.sectionTitle}>OAuth &amp; app summary (90d)</div>
        <div className={styles.sectionSub}>
          Application lifecycle events derived from{' '}
          <code className={styles.codeSnippet}>integration_installation.*</code>,{' '}
          <code className={styles.codeSnippet}>oauth_access.*</code>, and{' '}
          <code className={styles.codeSnippet}>oauth_authorization.*</code> events.
        </div>
        <div className={styles.metricGrid}>
          <MetricCard
            value={String(app?.apps_installed ?? 0)}
            label="Apps installed"
            helpText="Number of GitHub Apps installed in the last 90 days. Derived from integration_installation.create events. Review new installations for security compliance."
          />
          <MetricCard
            value={String(app?.apps_removed ?? 0)}
            label="Apps removed"
            helpText="Number of GitHub Apps removed in the last 90 days. Derived from integration_installation.destroy events."
          />
          <MetricCard
            value={String(app?.oauth_approved ?? 0)}
            label="OAuth approved"
            helpText="Number of OAuth app authorizations approved in the last 90 days. Derived from oauth_authorization.create events. High counts may indicate overly permissive policies."
          />
          <MetricCard
            value={String(app?.oauth_denied ?? 0)}
            label="OAuth denied"
            accent={app != null && app.oauth_denied > 0}
            helpText="Number of OAuth app authorizations denied in the last 90 days. Derived from oauth_authorization.destroy events. Denials may indicate policy enforcement or suspicious app requests."
          />
          <MetricCard
            value={String(app?.token_revocations ?? 0)}
            label="Token revocations"
            helpText="Number of OAuth or app tokens revoked in the last 90 days. Derived from oauth_access.revoke events. Review for compromised credential response."
          />
        </div>
      </div>

      {/* Code Scanning Health */}
      <div>
        <div className={styles.sectionTitle}>Code scanning health</div>
        <div className={styles.sectionSub}>
          Alert metrics from synced GitHub code scanning data.
        </div>
        <div className={styles.metricGrid}>
          <MetricCard
            value={String(codeScan?.open_count ?? codeScan?.total_alerts ?? 0)}
            label="Open alerts"
            accent={codeScan != null && (codeScan.open_count ?? codeScan.total_alerts ?? 0) > 0}
            helpText="Number of open code scanning alerts. Derived from synced GitHub code scanning data. Address critical and high severity alerts first."
          />
          <MetricCard
            value={codeScan != null ? `${Math.round(codeScan.avg_hours_to_close ?? 0)}h` : '—'}
            label="Avg hours to close"
            helpText="Average time in hours to close code scanning alerts. Lower is better; track this over time to measure security response efficiency."
          />
          <MetricCard
            value={String(codeScan?.critical_count ?? 0)}
            label="Critical"
            accent={codeScan != null && (codeScan.critical_count ?? 0) > 0}
            helpText="Number of critical severity code scanning alerts. These represent the highest-risk vulnerabilities and should be prioritized for immediate remediation."
          />
          <MetricCard
            value={String(codeScan?.high_count ?? 0)}
            label="High"
            helpText="Number of high severity code scanning alerts. Address these after critical alerts to reduce overall security risk."
          />
          <MetricCard
            value={String(codeScan?.dismissed_count ?? 0)}
            label="Dismissed"
            helpText="Number of dismissed code scanning alerts. Review dismissed alerts periodically to ensure valid justification and prevent false negatives."
          />
          <MetricCard
            value={String(codeScan?.fixed_count ?? 0)}
            label="Fixed"
            helpText="Number of code scanning alerts that have been fixed. Track this alongside open alerts to measure remediation progress."
          />
        </div>
      </div>

      {/* Vulnerability Aging */}
      <div>
        <div className={styles.sectionTitle}>Vulnerability aging</div>
        <div className={styles.sectionSub}>
          Open vulnerability metrics from synced Dependabot alert data. Aging buckets use actual{' '}
          <code className={styles.codeSnippet}>created_at</code> timestamps.
        </div>
        <div className={styles.metricGrid}>
          <MetricCard
            value={String(vuln?.total_open ?? 0)}
            label="Total open"
            accent={vuln != null && vuln.total_open > 0}
            helpText="Total number of open Dependabot vulnerability alerts. Derived from synced Dependabot alert data."
          />
          <MetricCard
            value={String(vuln?.critical_open ?? 0)}
            label="Critical open"
            accent={vuln != null && vuln.critical_open > 0}
            helpText="Number of critical severity open vulnerabilities. These should be patched immediately to prevent exploitation."
          />
          <MetricCard
            value={String(vuln?.high_open ?? 0)}
            label="High open"
            helpText="Number of high severity open vulnerabilities. Prioritize patching these after critical vulnerabilities."
          />
          <MetricCard
            value={String(vuln?.age_0_30d ?? 0)}
            label="0–30 days"
            helpText="Vulnerabilities open for 0–30 days. These are recent findings within the normal remediation window."
          />
          <MetricCard
            value={String(vuln?.age_30_60d ?? 0)}
            label="30–60 days"
            helpText="Vulnerabilities open for 30–60 days. These are overdue and should be escalated for remediation."
          />
          <MetricCard
            value={String(vuln?.age_60_90d ?? 0)}
            label="60–90 days"
            helpText="Vulnerabilities open for 60–90 days. Extended exposure increases exploitation risk significantly."
          />
          <MetricCard
            value={String(vuln?.age_gt_90d ?? 0)}
            label="> 90 days"
            accent={vuln != null && (vuln.age_gt_90d ?? 0) > 0}
            helpText="Vulnerabilities open for more than 90 days. These represent chronic unpatched risks and need executive attention."
          />
          <MetricCard
            value={String(vuln?.critical_aging_gt_90d ?? 0)}
            label="Critical > 90d"
            accent={vuln != null && (vuln.critical_aging_gt_90d ?? 0) > 0}
            helpText="Critical vulnerabilities open for more than 90 days. These are the highest priority items requiring immediate action."
          />
          <MetricCard
            value={vuln != null ? `${Math.round(vuln.avg_open_days ?? 0)}d` : '—'}
            label="Avg open days"
            helpText="Average number of days vulnerabilities remain open. Track this metric to measure your team's remediation velocity."
          />
        </div>
      </div>

      {/* Webhook Activity (30d) */}
      <div>
        <div className={styles.sectionTitle}>Webhook activity (30d)</div>
        <div className={styles.sectionSub}>
          Webhook lifecycle events derived from{' '}
          <code className={styles.codeSnippet}>hook.create</code>,{' '}
          <code className={styles.codeSnippet}>hook.destroy</code>, and{' '}
          <code className={styles.codeSnippet}>hook.config_changed</code> events.
        </div>
        <div className={styles.metricGrid}>
          <MetricCard
            value={String(app?.webhooks_created ?? 0)}
            label="Created"
            helpText="Number of webhooks created in the last 30 days. Derived from hook.create audit events. Review new webhooks for data exfiltration risk."
          />
          <MetricCard
            value={String(app?.webhooks_removed ?? 0)}
            label="Removed"
            helpText="Number of webhooks removed in the last 30 days. Derived from hook.destroy audit events."
          />
          <MetricCard
            value={String(app?.webhooks_modified ?? 0)}
            label="Modified"
            helpText="Number of webhooks with configuration changes in the last 30 days. Derived from hook.config_changed events. Verify URL or secret changes are authorized."
          />
        </div>
      </div>
    </div>
  );
}
