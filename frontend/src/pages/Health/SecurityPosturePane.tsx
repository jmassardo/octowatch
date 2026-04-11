import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Label } from '../../components/primitives/Label';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { DrilldownModal } from '../../components/primitives/DrilldownModal';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import {
  getSecurityPosture,
  getSecretScanning,
  getSsoHealth,
  getPrivilegeChanges,
} from '../../api/healthSignals';
import type { SsoOrgStatus } from '../../api/healthSignals';
import styles from './SecurityPosturePane.module.css';

/* ---------- helpers ---------- */

function formatHours(hours: number): string {
  if (hours < 1) return '< 1h';
  if (hours < 24) return `${Math.round(hours)}h`;
  const days = Math.round(hours / 24);
  return `${days}d`;
}

/* ---------- sub-components ---------- */

function SsoStatusTable({ orgs }: { orgs: SsoOrgStatus[] }) {
  const ssoTableColumns: ColumnDef<SsoOrgStatus>[] = [
    {
      key: 'org',
      header: 'Organization',
      sortable: true,
      filterable: true,
      render: (o) => o.org,
      sortValue: (o) => o.org,
      filterValue: (o) => o.org,
    },
    {
      key: 'sso_status',
      header: 'SSO status',
      sortable: true,
      render: (o) => (
        <Label variant={o.sso_enabled ? 'success' : 'danger'}>
          {o.sso_enabled ? 'enabled' : 'disabled'}
        </Label>
      ),
      sortValue: (o) => (o.sso_enabled ? 'enabled' : 'disabled'),
    },
  ];

  return (
    <div>
      <div className={styles.sectionTitle}>SSO status by organization</div>
      <div className={styles.sectionSub}>
        Per-org SSO enable/disable state derived from{' '}
        <code className={styles.codeSnippet}>org.enable_saml</code> /{' '}
        <code className={styles.codeSnippet}>org.disable_saml</code> audit events.
      </div>
      <div className={styles.tableWrap}>
        <DataTable
          columns={ssoTableColumns}
          data={orgs}
          rowKey={(o) => o.org}
          emptyMessage="No SSO data available"
        />
      </div>
    </div>
  );
}

/* ---------- main pane ---------- */

export function SecurityPosturePane() {
  const [ssoDrilldownOpen, setSsoDrilldownOpen] = useState(false);
  const [securityDrilldown, setSecurityDrilldown] = useState<{
    title: string;
    metricName: string;
  } | null>(null);
  const [privilegeDrilldown, setPrivilegeDrilldown] = useState<{
    title: string;
    metricName: string;
  } | null>(null);

  const postureQuery = useQuery({
    queryKey: ['health', 'security-posture'],
    queryFn: getSecurityPosture,
    staleTime: 60_000,
  });

  const secretQuery = useQuery({
    queryKey: ['health', 'secret-scanning'],
    queryFn: getSecretScanning,
    staleTime: 60_000,
  });

  const ssoQuery = useQuery({
    queryKey: ['health', 'sso'],
    queryFn: getSsoHealth,
    staleTime: 60_000,
  });

  const privilegeQuery = useQuery({
    queryKey: ['health', 'privilege-changes'],
    queryFn: getPrivilegeChanges,
    staleTime: 60_000,
  });

  const isLoading =
    postureQuery.isLoading ||
    secretQuery.isLoading ||
    ssoQuery.isLoading ||
    privilegeQuery.isLoading;
  const isError =
    postureQuery.isError || secretQuery.isError || ssoQuery.isError || privilegeQuery.isError;

  if (isLoading) {
    return (
      <div className={styles.centered}>
        <Spinner size={28} />
      </div>
    );
  }

  if (isError) {
    const retryAll = () => {
      void postureQuery.refetch();
      void secretQuery.refetch();
      void ssoQuery.refetch();
      void privilegeQuery.refetch();
    };
    return <ErrorBanner message="Failed to load security posture data" onRetry={retryAll} />;
  }

  const posture = postureQuery.data;
  const secrets = secretQuery.data;
  const ssoOrgs = ssoQuery.data?.orgs ?? [];
  const privilege = privilegeQuery.data;

  const ssoEnabledCount = ssoOrgs.filter((o) => o.sso_enabled).length;
  const auditStreamActive = ssoOrgs.length > 0;

  const ssoColumns: ColumnDef<SsoOrgStatus>[] = [
    {
      key: 'org',
      header: 'Organization',
      sortable: true,
      filterable: true,
      render: (o) => o.org,
      sortValue: (o) => o.org,
      filterValue: (o) => o.org,
    },
    {
      key: 'sso_status',
      header: 'SSO Status',
      sortable: true,
      render: (o) => (
        <Label variant={o.sso_enabled ? 'success' : 'danger'}>
          {o.sso_enabled ? 'enabled' : 'disabled'}
        </Label>
      ),
      sortValue: (o) => (o.sso_enabled ? 'enabled' : 'disabled'),
    },
  ];

  function handleSsoKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setSsoDrilldownOpen(true);
    }
  }

  return (
    <div className={styles.pane}>
      <SampleDataBanner message="Security posture signals are derived from audit log events. Some metrics require a baseline import from Settings → Integrations." />

      {/* Security Coverage Summary */}
      <div>
        <div className={styles.sectionTitle}>Security coverage summary</div>
        <div className={styles.sectionSub}>
          Repository-level security feature adoption derived from audit log events.
        </div>
        <div className={styles.metricGrid}>
          <MetricCard
            value={String(posture?.repos_with_secret_scanning ?? 0)}
            label="Secret scanning enabled"
            onClick={() =>
              setSecurityDrilldown({
                title: 'Repos with secret scanning enabled',
                metricName: 'secret_scanning',
              })
            }
          />
          <MetricCard
            value={String(posture?.repos_with_dependabot ?? 0)}
            label="Dependabot enabled"
            onClick={() =>
              setSecurityDrilldown({
                title: 'Repos with Dependabot enabled',
                metricName: 'dependabot',
              })
            }
          />
          <MetricCard
            value={String(posture?.repos_with_codeql ?? 0)}
            label="CodeQL enabled"
            onClick={() =>
              setSecurityDrilldown({
                title: 'Repos with CodeQL enabled',
                metricName: 'codeql',
              })
            }
          />
          <MetricCard
            value={String(posture?.repos_with_ghas ?? 0)}
            label="GHAS enabled"
            onClick={() =>
              setSecurityDrilldown({
                title: 'Repos with GHAS enabled',
                metricName: 'ghas',
              })
            }
          />
          <MetricCard
            value={String(posture?.features_disabled_count ?? 0)}
            label="Features disabled"
            accent={posture != null && posture.features_disabled_count > 0}
            onClick={() =>
              setSecurityDrilldown({
                title: 'Security features disabled',
                metricName: 'features_disabled',
              })
            }
          />
        </div>
      </div>

      {/* Security Coverage Drilldown */}
      <DrilldownModal
        open={securityDrilldown !== null}
        onClose={() => setSecurityDrilldown(null)}
        title={securityDrilldown?.title ?? ''}
        data={
          securityDrilldown
            ? [
                {
                  metric: securityDrilldown.metricName,
                  count:
                    securityDrilldown.metricName === 'secret_scanning'
                      ? (posture?.repos_with_secret_scanning ?? 0)
                      : securityDrilldown.metricName === 'dependabot'
                        ? (posture?.repos_with_dependabot ?? 0)
                        : securityDrilldown.metricName === 'codeql'
                          ? (posture?.repos_with_codeql ?? 0)
                          : securityDrilldown.metricName === 'ghas'
                            ? (posture?.repos_with_ghas ?? 0)
                            : (posture?.features_disabled_count ?? 0),
                  note: 'Per-repository detail requires GitHub API integration.',
                },
              ]
            : []
        }
        columns={[
          {
            key: 'metric',
            header: 'Metric',
            render: (r: { metric: string; count: number; note: string }) => r.metric,
          },
          {
            key: 'count',
            header: 'Count',
            render: (r: { metric: string; count: number; note: string }) => String(r.count),
          },
          {
            key: 'note',
            header: 'Note',
            render: (r: { metric: string; count: number; note: string }) => r.note,
          },
        ]}
        rowKey={(r: { metric: string }) => r.metric}
      />

      {/* Secret Scanning Alerts */}
      <div>
        <div className={styles.sectionTitle}>Secret scanning alerts</div>
        <div className={styles.sectionSub}>
          Alert metrics from synced GitHub secret scanning data. MTTR and resolution rates reflect
          actual alert records.
        </div>
        <div className={styles.metricGrid}>
          <MetricCard
            value={String(secrets?.unresolved_total ?? 0)}
            label="Unresolved total"
            accent={secrets != null && secrets.unresolved_total > 0}
            onClick={() =>
              setSecurityDrilldown({
                title: 'Unresolved secret scanning alerts',
                metricName: 'unresolved_total',
              })
            }
          />
          <MetricCard
            value={String(secrets?.push_protection_bypassed_count ?? secrets?.publicly_leaked ?? 0)}
            label="Push protection bypassed"
            accent={
              secrets != null &&
              (secrets.push_protection_bypassed_count ?? secrets.publicly_leaked ?? 0) > 0
            }
            onClick={() =>
              setSecurityDrilldown({
                title: 'Push protection bypassed alerts',
                metricName: 'push_protection_bypassed',
              })
            }
          />
          <MetricCard
            value={String(secrets?.unresolved_gt_7d ?? secrets?.open_gt_7d ?? 0)}
            label="Open > 7 days"
            onClick={() =>
              setSecurityDrilldown({
                title: 'Secret alerts open > 7 days',
                metricName: 'open_gt_7d',
              })
            }
          />
          <MetricCard
            value={String(secrets?.unresolved_gt_30d ?? secrets?.open_gt_30d ?? 0)}
            label="Open > 30 days"
            onClick={() =>
              setSecurityDrilldown({
                title: 'Secret alerts open > 30 days',
                metricName: 'open_gt_30d',
              })
            }
          />
          <MetricCard
            value={secrets != null ? formatHours(secrets.avg_hours_to_resolve ?? secrets.mttr_hours ?? 0) : '—'}
            label="MTTR"
            onClick={() =>
              setSecurityDrilldown({
                title: 'Mean time to resolution',
                metricName: 'mttr',
              })
            }
          />
          <MetricCard
            value={
              secrets?.resolution_rate_pct != null
                ? `${secrets.resolution_rate_pct}%`
                : '—'
            }
            label="Resolution rate"
            onClick={() =>
              setSecurityDrilldown({
                title: 'Alert resolution rate',
                metricName: 'resolution_rate',
              })
            }
          />
        </div>
      </div>

      {/* SSO Status */}
      <SsoStatusTable orgs={ssoOrgs} />

      {/* Privilege Changes (30d) */}
      <div>
        <div className={styles.sectionTitle}>Privilege changes (30d)</div>
        <div className={styles.sectionSub}>
          Administrative role changes derived from{' '}
          <code className={styles.codeSnippet}>org.update_member</code> and{' '}
          <code className={styles.codeSnippet}>custom_role.*</code> events.
        </div>
        <div className={styles.metricGrid}>
          <MetricCard
            value={String(privilege?.admin_promotions ?? 0)}
            label="Admin promotions"
            accent={privilege != null && privilege.admin_promotions > 0}
            onClick={() =>
              setPrivilegeDrilldown({
                title: 'Admin promotions (30d)',
                metricName: 'admin_promotions',
              })
            }
          />
          <MetricCard
            value={String(privilege?.integration_manager_grants ?? 0)}
            label="Integration manager grants"
            onClick={() =>
              setPrivilegeDrilldown({
                title: 'Integration manager grants (30d)',
                metricName: 'integration_manager_grants',
              })
            }
          />
          <MetricCard
            value={String(privilege?.custom_role_changes ?? 0)}
            label="Custom role changes"
            onClick={() =>
              setPrivilegeDrilldown({
                title: 'Custom role changes (30d)',
                metricName: 'custom_role_changes',
              })
            }
          />
        </div>
      </div>

      {/* Privilege Changes Drilldown */}
      <DrilldownModal
        open={privilegeDrilldown !== null}
        onClose={() => setPrivilegeDrilldown(null)}
        title={privilegeDrilldown?.title ?? ''}
        data={
          privilegeDrilldown
            ? [
                {
                  metric: privilegeDrilldown.metricName,
                  count:
                    privilegeDrilldown.metricName === 'admin_promotions'
                      ? (privilege?.admin_promotions ?? 0)
                      : privilegeDrilldown.metricName === 'integration_manager_grants'
                        ? (privilege?.integration_manager_grants ?? 0)
                        : (privilege?.custom_role_changes ?? 0),
                  note: 'Per-user detail requires GitHub API integration.',
                },
              ]
            : []
        }
        columns={[
          {
            key: 'metric',
            header: 'Metric',
            render: (r: { metric: string; count: number; note: string }) => r.metric,
          },
          {
            key: 'count',
            header: 'Count',
            render: (r: { metric: string; count: number; note: string }) => String(r.count),
          },
          {
            key: 'note',
            header: 'Note',
            render: (r: { metric: string; count: number; note: string }) => r.note,
          },
        ]}
        rowKey={(r: { metric: string }) => r.metric}
      />

      {/* IP Allowlist / Audit Stream */}
      <div>
        <div className={styles.sectionTitle}>Audit stream status</div>
        <div className={styles.streamStatus}>
          <div
            className={[
              styles.streamDot,
              auditStreamActive ? styles.streamDotEnabled : styles.streamDotDisabled,
            ].join(' ')}
          />
          <span>
            Audit log stream: <strong>{auditStreamActive ? 'active' : 'inactive'}</strong>
            {ssoOrgs.length > 0 && (
              <>
                {' · '}
                <span
                  className={styles.clickableStat}
                  onClick={() => setSsoDrilldownOpen(true)}
                  role="button"
                  tabIndex={0}
                  aria-label={`${ssoEnabledCount} of ${ssoOrgs.length} orgs with SSO – click to view details`}
                  onKeyDown={handleSsoKeyDown}
                >
                  {ssoEnabledCount}/{ssoOrgs.length} orgs with SSO
                </span>
              </>
            )}
          </span>
        </div>
      </div>

      <DrilldownModal
        open={ssoDrilldownOpen}
        onClose={() => setSsoDrilldownOpen(false)}
        title="SSO status by organization"
        data={ssoOrgs}
        columns={ssoColumns}
        rowKey={(o) => o.org}
      />
    </div>
  );
}
