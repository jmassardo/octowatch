import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Label } from '../../components/primitives/Label';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { DrilldownModal } from '../../components/primitives/DrilldownModal';
import type { ColumnDef } from '../../components/primitives/DataTable';
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
  return (
    <div>
      <div className={styles.sectionTitle}>SSO status by organization</div>
      <div className={styles.sectionSub}>
        Per-org SSO enable/disable state derived from{' '}
        <code className={styles.codeSnippet}>org.enable_saml</code> /{' '}
        <code className={styles.codeSnippet}>org.disable_saml</code> audit events.
      </div>
      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Organization</th>
              <th>SSO status</th>
            </tr>
          </thead>
          <tbody>
            {orgs.length === 0 && (
              <tr>
                <td
                  colSpan={2}
                  style={{ textAlign: 'center', color: 'var(--fg-muted)', padding: 24 }}
                >
                  No SSO data available
                </td>
              </tr>
            )}
            {orgs.map((org) => (
              <tr key={org.org}>
                <td>{org.org}</td>
                <td>
                  <Label variant={org.sso_enabled ? 'success' : 'danger'}>
                    {org.sso_enabled ? 'enabled' : 'disabled'}
                  </Label>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ---------- main pane ---------- */

export function SecurityPosturePane() {
  const [ssoDrilldownOpen, setSsoDrilldownOpen] = useState(false);

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
          />
          <MetricCard
            value={String(posture?.repos_with_dependabot ?? 0)}
            label="Dependabot enabled"
          />
          <MetricCard value={String(posture?.repos_with_codeql ?? 0)} label="CodeQL enabled" />
          <MetricCard value={String(posture?.repos_with_ghas ?? 0)} label="GHAS enabled" />
          <MetricCard
            value={String(posture?.features_disabled_count ?? 0)}
            label="Features disabled"
            accent={posture != null && posture.features_disabled_count > 0}
          />
        </div>
      </div>

      {/* Secret Scanning Alerts */}
      <div>
        <div className={styles.sectionTitle}>Secret scanning alerts</div>
        <div className={styles.sectionSub}>
          Alert aging and resolution metrics derived from{' '}
          <code className={styles.codeSnippet}>secret_scanning_alert.*</code> events.
        </div>
        <div className={styles.metricGrid}>
          <MetricCard
            value={String(secrets?.unresolved_total ?? 0)}
            label="Unresolved total"
            accent={secrets != null && secrets.unresolved_total > 0}
          />
          <MetricCard
            value={String(secrets?.publicly_leaked ?? 0)}
            label="Publicly leaked"
            accent={secrets != null && secrets.publicly_leaked > 0}
          />
          <MetricCard value={String(secrets?.open_gt_7d ?? 0)} label="Open > 7 days" />
          <MetricCard value={String(secrets?.open_gt_30d ?? 0)} label="Open > 30 days" />
          <MetricCard
            value={secrets != null ? formatHours(secrets.mttr_hours) : '—'}
            label="MTTR"
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
          />
          <MetricCard
            value={String(privilege?.integration_manager_grants ?? 0)}
            label="Integration manager grants"
          />
          <MetricCard
            value={String(privilege?.custom_role_changes ?? 0)}
            label="Custom role changes"
          />
        </div>
      </div>

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
