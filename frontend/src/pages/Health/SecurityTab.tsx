import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { getPlatformSecurity } from '../../api/healthSignals';
import type { PlatformSecurityOrg } from '../../api/healthSignals';
import styles from './SecurityTab.module.css';

function scoreClass(score: number): string {
  if (score >= 80) return styles.scoreHigh;
  if (score >= 50) return styles.scoreMedium;
  return styles.scoreLow;
}

interface SecurityCheckProps {
  label: string;
  enabled: boolean;
}

function SecurityCheck({ label, enabled }: SecurityCheckProps) {
  return (
    <li className={styles.checkItem}>
      <span className={styles.checkIcon}>{enabled ? '✅' : '❌'}</span>
      <span>{label}</span>
    </li>
  );
}

function OrgSecurityCard({ org }: { org: PlatformSecurityOrg }) {
  return (
    <div className={styles.orgCard}>
      <div className={styles.orgCardHeader}>
        <span className={styles.orgName}>{org.org}</span>
        <span className={`${styles.scoreCircle} ${scoreClass(org.compliance_score)}`}>
          {Math.round(org.compliance_score)}%
        </span>
      </div>

      <ul className={styles.checkList}>
        <SecurityCheck label="SSO configured" enabled={org.sso_configured} />
        <SecurityCheck label="2FA required" enabled={org.two_fa_required} />
        <SecurityCheck label="Audit log streaming" enabled={org.audit_log_streaming} />
        <SecurityCheck label="IP allowlist" enabled={org.ip_allowlist_configured} />
        <SecurityCheck label="Branch protection defaults" enabled={org.branch_protection_default} />
      </ul>

      {org.recommendations.length > 0 && (
        <div className={styles.recommendations}>
          <div className={styles.recTitle}>Recommendations</div>
          <ul>
            {org.recommendations.map((rec) => (
              <li key={rec}>{rec}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function SecurityTab() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['health', 'platform-security'],
    queryFn: getPlatformSecurity,
    staleTime: 60_000,
  });

  const orgs = data?.orgs ?? [];
  const overallScore = data?.overall_compliance_score ?? 0;
  const ssoCount = orgs.filter((o) => o.sso_configured).length;
  const twoFaCount = orgs.filter((o) => o.two_fa_required).length;
  const gapsCount = orgs.reduce((acc, o) => acc + o.recommendations.length, 0);

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spinner size={28} />
      </div>
    );
  }

  return (
    <div className={styles.pane}>
      <div className={styles.metricGrid}>
        <MetricCard
          value={`${Math.round(overallScore)}%`}
          label="Overall compliance"
          accent={overallScore < 80}
          helpText="Average security compliance score across all monitored organizations."
        />
        <MetricCard
          value={`${ssoCount}/${orgs.length}`}
          label="SSO enabled"
          helpText="Organizations with SSO configured and enforced."
        />
        <MetricCard
          value={`${twoFaCount}/${orgs.length}`}
          label="2FA required"
          helpText="Organizations with two-factor authentication requirement enabled."
        />
        <MetricCard
          value={String(gapsCount)}
          label="Security gaps"
          accent={gapsCount > 0}
          helpText="Total number of actionable security recommendations across all orgs."
        />
      </div>

      {isError && (
        <ErrorBanner
          message="Failed to load platform security data"
          onRetry={() => void refetch()}
        />
      )}

      {!isError && orgs.length === 0 && (
        <div style={{ color: 'var(--fg-muted)', fontSize: 13, padding: 16, textAlign: 'center' }}>
          No platform security data available — security events will appear here after audit log
          ingestion.
        </div>
      )}

      {!isError && orgs.length > 0 && (
        <>
          <div className={styles.sectionTitle}>Per-organization security checklist</div>
          <div className={styles.orgCards}>
            {orgs.map((org) => (
              <OrgSecurityCard key={org.org} org={org} />
            ))}
          </div>
        </>
      )}

      <div className={styles.sourceNote}>
        ℹ️ Derived from <code className={styles.sourceCode}>org.enable_saml</code>,{' '}
        <code className={styles.sourceCode}>org.require_two_factor_authentication</code>,{' '}
        <code className={styles.sourceCode}>audit_log_streaming.*</code>,{' '}
        <code className={styles.sourceCode}>ip_allow_list.*</code>, and{' '}
        <code className={styles.sourceCode}>protected_branch.create</code> events
      </div>
    </div>
  );
}
