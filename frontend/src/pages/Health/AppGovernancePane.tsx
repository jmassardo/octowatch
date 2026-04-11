import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { DrilldownModal } from '../../components/primitives/DrilldownModal';
import { getAppGovernance, getCodeScanning, getVulnerabilities } from '../../api/healthSignals';
import styles from './AppGovernancePane.module.css';

/* ---------- main pane ---------- */

export function AppGovernancePane() {
  const [govDrilldown, setGovDrilldown] = useState<{
    title: string;
    metricName: string;
  } | null>(null);

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
            onClick={() =>
              setGovDrilldown({ title: 'Apps installed (90d)', metricName: 'apps_installed' })
            }
          />
          <MetricCard
            value={String(app?.apps_removed ?? 0)}
            label="Apps removed"
            onClick={() =>
              setGovDrilldown({ title: 'Apps removed (90d)', metricName: 'apps_removed' })
            }
          />
          <MetricCard
            value={String(app?.oauth_approved ?? 0)}
            label="OAuth approved"
            onClick={() =>
              setGovDrilldown({ title: 'OAuth approved (90d)', metricName: 'oauth_approved' })
            }
          />
          <MetricCard
            value={String(app?.oauth_denied ?? 0)}
            label="OAuth denied"
            accent={app != null && app.oauth_denied > 0}
            onClick={() =>
              setGovDrilldown({ title: 'OAuth denied (90d)', metricName: 'oauth_denied' })
            }
          />
          <MetricCard
            value={String(app?.token_revocations ?? 0)}
            label="Token revocations"
            onClick={() =>
              setGovDrilldown({
                title: 'Token revocations (90d)',
                metricName: 'token_revocations',
              })
            }
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
            onClick={() =>
              setGovDrilldown({ title: 'Open code scanning alerts', metricName: 'open_alerts' })
            }
          />
          <MetricCard
            value={codeScan != null ? `${Math.round(codeScan.avg_hours_to_close ?? 0)}h` : '—'}
            label="Avg hours to close"
            onClick={() =>
              setGovDrilldown({
                title: 'Average hours to close',
                metricName: 'avg_hours_to_close',
              })
            }
          />
          <MetricCard
            value={String(codeScan?.critical_count ?? 0)}
            label="Critical"
            accent={codeScan != null && (codeScan.critical_count ?? 0) > 0}
            onClick={() =>
              setGovDrilldown({
                title: 'Critical code scanning alerts',
                metricName: 'critical',
              })
            }
          />
          <MetricCard
            value={String(codeScan?.high_count ?? 0)}
            label="High"
            onClick={() =>
              setGovDrilldown({
                title: 'High severity code scanning alerts',
                metricName: 'high',
              })
            }
          />
          <MetricCard
            value={String(codeScan?.dismissed_count ?? 0)}
            label="Dismissed"
            onClick={() =>
              setGovDrilldown({
                title: 'Dismissed code scanning alerts',
                metricName: 'dismissed',
              })
            }
          />
          <MetricCard
            value={String(codeScan?.fixed_count ?? 0)}
            label="Fixed"
            onClick={() =>
              setGovDrilldown({
                title: 'Fixed code scanning alerts',
                metricName: 'fixed',
              })
            }
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
            onClick={() =>
              setGovDrilldown({
                title: 'Total open vulnerabilities',
                metricName: 'total_open',
              })
            }
          />
          <MetricCard
            value={String(vuln?.critical_open ?? 0)}
            label="Critical open"
            accent={vuln != null && vuln.critical_open > 0}
            onClick={() =>
              setGovDrilldown({
                title: 'Critical open vulnerabilities',
                metricName: 'critical_open',
              })
            }
          />
          <MetricCard
            value={String(vuln?.high_open ?? 0)}
            label="High open"
            onClick={() =>
              setGovDrilldown({
                title: 'High severity open vulnerabilities',
                metricName: 'high_open',
              })
            }
          />
          <MetricCard
            value={String(vuln?.age_0_30d ?? 0)}
            label="0–30 days"
            onClick={() =>
              setGovDrilldown({
                title: 'Vulnerabilities open 0–30 days',
                metricName: 'age_0_30d',
              })
            }
          />
          <MetricCard
            value={String(vuln?.age_30_60d ?? 0)}
            label="30–60 days"
            onClick={() =>
              setGovDrilldown({
                title: 'Vulnerabilities open 30–60 days',
                metricName: 'age_30_60d',
              })
            }
          />
          <MetricCard
            value={String(vuln?.age_60_90d ?? 0)}
            label="60–90 days"
            onClick={() =>
              setGovDrilldown({
                title: 'Vulnerabilities open 60–90 days',
                metricName: 'age_60_90d',
              })
            }
          />
          <MetricCard
            value={String(vuln?.age_gt_90d ?? 0)}
            label="> 90 days"
            accent={vuln != null && (vuln.age_gt_90d ?? 0) > 0}
            onClick={() =>
              setGovDrilldown({
                title: 'Vulnerabilities open > 90 days',
                metricName: 'age_gt_90d',
              })
            }
          />
          <MetricCard
            value={String(vuln?.critical_aging_gt_90d ?? 0)}
            label="Critical > 90d"
            accent={vuln != null && (vuln.critical_aging_gt_90d ?? 0) > 0}
            onClick={() =>
              setGovDrilldown({
                title: 'Critical aging vulnerabilities (> 90 days)',
                metricName: 'critical_aging_gt_90d',
              })
            }
          />
          <MetricCard
            value={vuln != null ? `${Math.round(vuln.avg_open_days ?? 0)}d` : '—'}
            label="Avg open days"
            onClick={() =>
              setGovDrilldown({
                title: 'Average open days for vulnerabilities',
                metricName: 'avg_open_days',
              })
            }
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
            onClick={() =>
              setGovDrilldown({
                title: 'Webhooks created (30d)',
                metricName: 'webhooks_created',
              })
            }
          />
          <MetricCard
            value={String(app?.webhooks_removed ?? 0)}
            label="Removed"
            onClick={() =>
              setGovDrilldown({
                title: 'Webhooks removed (30d)',
                metricName: 'webhooks_removed',
              })
            }
          />
          <MetricCard
            value={String(app?.webhooks_modified ?? 0)}
            label="Modified"
            onClick={() =>
              setGovDrilldown({
                title: 'Webhooks modified (30d)',
                metricName: 'webhooks_modified',
              })
            }
          />
        </div>
      </div>

      {/* App Governance Drilldown Modal */}
      <DrilldownModal
        open={govDrilldown !== null}
        onClose={() => setGovDrilldown(null)}
        title={govDrilldown?.title ?? ''}
        data={
          govDrilldown
            ? [
                {
                  metric: govDrilldown.metricName,
                  note: 'Per-event detail requires GitHub API integration.',
                },
              ]
            : []
        }
        columns={[
          {
            key: 'metric',
            header: 'Metric',
            render: (r: { metric: string; note: string }) => r.metric,
          },
          {
            key: 'note',
            header: 'Note',
            render: (r: { metric: string; note: string }) => r.note,
          },
        ]}
        rowKey={(r: { metric: string }) => r.metric}
      />
    </div>
  );
}
