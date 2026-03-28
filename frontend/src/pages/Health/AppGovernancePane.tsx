import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import {
  getAppGovernance,
  getCodeScanning,
  getVulnerabilities,
} from '../../api/healthSignals';
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
          />
          <MetricCard
            value={String(app?.apps_removed ?? 0)}
            label="Apps removed"
          />
          <MetricCard
            value={String(app?.oauth_approved ?? 0)}
            label="OAuth approved"
          />
          <MetricCard
            value={String(app?.oauth_denied ?? 0)}
            label="OAuth denied"
            accent={app != null && app.oauth_denied > 0}
          />
          <MetricCard
            value={String(app?.token_revocations ?? 0)}
            label="Token revocations"
          />
        </div>
      </div>

      {/* Code Scanning Health */}
      <div>
        <div className={styles.sectionTitle}>Code scanning health</div>
        <div className={styles.sectionSub}>
          Alert metrics derived from{' '}
          <code className={styles.codeSnippet}>code_scanning_alert.*</code> events.
        </div>
        <div className={styles.metricGrid}>
          <MetricCard
            value={String(codeScan?.total_alerts ?? 0)}
            label="Total alerts"
            accent={codeScan != null && codeScan.total_alerts > 0}
          />
          <MetricCard
            value={codeScan != null ? `${Math.round(codeScan.avg_hours_to_close)}h` : '—'}
            label="Avg hours to close"
          />
          <MetricCard
            value={String(codeScan?.dismissed_count ?? 0)}
            label="Dismissed"
          />
          <MetricCard
            value={String(codeScan?.reappeared_count ?? 0)}
            label="Reappeared"
            accent={codeScan != null && codeScan.reappeared_count > 0}
          />
        </div>
      </div>

      {/* Vulnerability Aging */}
      <div>
        <div className={styles.sectionTitle}>Vulnerability aging</div>
        <div className={styles.sectionSub}>
          Open vulnerability metrics derived from{' '}
          <code className={styles.codeSnippet}>dependabot_alert.*</code> events.
        </div>
        <div className={styles.metricGrid}>
          <MetricCard
            value={String(vuln?.total_open ?? 0)}
            label="Total open"
            accent={vuln != null && vuln.total_open > 0}
          />
          <MetricCard
            value={String(vuln?.critical_open ?? 0)}
            label="Critical open"
            accent={vuln != null && vuln.critical_open > 0}
          />
          <MetricCard
            value={String(vuln?.high_open ?? 0)}
            label="High open"
          />
          <MetricCard
            value={String(vuln?.open_gt_30d ?? 0)}
            label="Open > 30 days"
          />
          <MetricCard
            value={String(vuln?.critical_open_gt_14d ?? 0)}
            label="Critical > 14 days"
            accent={vuln != null && vuln.critical_open_gt_14d > 0}
          />
          <MetricCard
            value={vuln != null ? `${Math.round(vuln.avg_open_days)}d` : '—'}
            label="Avg open days"
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
          />
          <MetricCard
            value={String(app?.webhooks_removed ?? 0)}
            label="Removed"
          />
          <MetricCard
            value={String(app?.webhooks_modified ?? 0)}
            label="Modified"
          />
        </div>
      </div>
    </div>
  );
}
