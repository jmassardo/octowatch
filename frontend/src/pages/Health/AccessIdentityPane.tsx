import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { BarChart } from '../../components/charts/BarChart';
import {
  getPatHealth,
  getBypassOffenders,
  getExternalCollaborators,
  getDormantCollaborators,
} from '../../api/healthSignals';
import type {
  PatToken,
  BypassOffender,
  ExternalCollaborator,
  DormantCollaborator,
  CollabSummary,
} from '../../api/healthSignals';
import styles from './AccessIdentityPane.module.css';

/* ---------- helpers ---------- */

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatDaysAgo(days: number | null): string {
  if (days === null) return '—';
  if (days === 0) return 'Today';
  if (days === 1) return '1 day ago';
  return `${days} days ago`;
}

function daysLabel(days: number): string {
  if (days === 1) return '1 day';
  return `${days} days`;
}

function riskBadgeVariant(collab: ExternalCollaborator): 'danger' | 'attention' | 'muted' {
  const days = collab.days_since_last_event;
  if (days !== null && days > 90) return 'danger';
  if (collab.role === 'admin') return 'danger';
  if (days !== null && days > 30) return 'attention';
  return 'muted';
}

function riskBadgeText(collab: ExternalCollaborator): string {
  const days = collab.days_since_last_event;
  if (days !== null && days > 90) return 'stale & dormant';
  if (collab.role === 'admin') return 'admin, review required';
  if (days !== null && days > 30) return 'active, unreviewed';
  return 'active';
}

/**
 * Build buckets for PAT age distribution chart.
 * Groups tokens into age ranges.
 */
function buildPatAgeBuckets(tokens: PatToken[]): { labels: string[]; counts: number[] } {
  const buckets = [
    { label: '0–30d', min: 0, max: 30 },
    { label: '31–90d', min: 31, max: 90 },
    { label: '91–180d', min: 91, max: 180 },
    { label: '181–365d', min: 181, max: 365 },
    { label: '365d+', min: 366, max: Infinity },
  ];

  const counts = buckets.map(
    (b) => tokens.filter((t) => t.age_days >= b.min && t.age_days <= b.max).length,
  );

  return { labels: buckets.map((b) => b.label), counts };
}

/* ---------- sub-components ---------- */

function MemberActivityOverview({ dormant }: { dormant: DormantCollaborator[] }) {
  const dormantCount = dormant.filter((d) => d.days_inactive >= 90).length;
  const atRiskCount = dormant.filter((d) => d.days_inactive >= 60 && d.days_inactive < 90).length;
  const newCount = dormant.filter((d) => d.days_inactive < 30).length;

  return (
    <Card>
      <CardHeader>Member activity overview</CardHeader>
      <div className={styles.statusList}>
        <div className={`${styles.statusRow} ${styles.statusRowDanger}`}>
          <Label variant="danger">dormant</Label>
          <div className={styles.statusBody}>
            <strong>{dormantCount} {dormantCount === 1 ? 'member' : 'members'}</strong> no activity in 90+ days
          </div>
          <span className={styles.statusNote}>still licensed</span>
        </div>
        <div className={`${styles.statusRow} ${styles.statusRowAttention}`}>
          <Label variant="attention">at risk</Label>
          <div className={styles.statusBody}>
            <strong>{atRiskCount} {atRiskCount === 1 ? 'member' : 'members'}</strong> no activity in 60–90 days
          </div>
          <span className={styles.statusNote}>trending dormant</span>
        </div>
        <div className={`${styles.statusRow} ${styles.statusRowSuccess}`}>
          <Label variant="success">new</Label>
          <div className={styles.statusBody}>
            <strong>{newCount} {newCount === 1 ? 'member' : 'members'}</strong> joined in last 30 days
          </div>
          <span className={styles.statusNote}>onboarding period</span>
        </div>
      </div>
      <div className={styles.cardFooter}>
        ℹ Derived from <code className={styles.codeSnippet}>org.add_member</code>,{' '}
        <code className={styles.codeSnippet}>user.login</code>, and per-actor event timestamps
      </div>
    </Card>
  );
}

function PatHealthSnapshot({
  noExpiryCount,
  expiredCount,
  stale90dCount,
}: {
  noExpiryCount: number;
  expiredCount: number;
  stale90dCount: number;
}) {
  return (
    <Card>
      <CardHeader>PAT health snapshot</CardHeader>
      <div className={styles.statusList}>
        <div className={`${styles.statusRow} ${styles.statusRowDanger}`}>
          <Label variant="danger">no expiry</Label>
          <div className={styles.statusBody}>
            <strong>{noExpiryCount} {noExpiryCount === 1 ? 'token' : 'tokens'}</strong> with no expiration date
          </div>
          <span className={styles.statusNote}>never rotate</span>
        </div>
        <div className={`${styles.statusRow} ${styles.statusRowSevere}`}>
          <Label variant="severe">expiring soon</Label>
          <div className={styles.statusBody}>
            <strong>{expiredCount} {expiredCount === 1 ? 'token' : 'tokens'}</strong> expire within 30 days
          </div>
          <span className={styles.statusNote}>may break automations</span>
        </div>
        <div className={`${styles.statusRow} ${styles.statusRowMuted}`}>
          <Label variant="muted">stale</Label>
          <div className={styles.statusBody}>
            <strong>{stale90dCount} {stale90dCount === 1 ? 'token' : 'tokens'}</strong> not used in 90+ days
          </div>
          <span className={styles.statusNote}>candidates for revocation</span>
        </div>
      </div>
      <div className={styles.cardFooter}>
        ℹ Derived from <code className={styles.codeSnippet}>personal_access_token.*</code> events
        and <code className={styles.codeSnippet}>authentication.token</code> usage in audit log
      </div>
    </Card>
  );
}

function BypassOffendersTable({ offenders }: { offenders: BypassOffender[] }) {
  return (
    <div>
      <div className={styles.sectionTitle}>Bypass repeat offenders</div>
      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Actor</th>
              <th>Total bypasses</th>
              <th>Push protection</th>
              <th>Branch policy</th>
              <th>Active days</th>
              <th>Last bypass</th>
            </tr>
          </thead>
          <tbody>
            {offenders.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', color: 'var(--fg-muted)', padding: 24 }}>
                  No bypass offenders found
                </td>
              </tr>
            )}
            {offenders.map((o) => (
              <tr key={o.actor}>
                <td>
                  <span className={styles.mention}>@{o.actor}</span>
                </td>
                <td className={styles.numCol}>
                  <Label variant={o.total_bypasses > 10 ? 'danger' : o.total_bypasses > 5 ? 'attention' : 'muted'}>
                    {o.total_bypasses}
                  </Label>
                </td>
                <td className={styles.numCol}>{o.push_protection_bypasses}</td>
                <td className={styles.numCol}>{o.branch_protection_overrides}</td>
                <td className={styles.numCol}>{o.active_days}</td>
                <td style={{ color: 'var(--fg-muted)' }}>{formatDate(o.last_bypass_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ExternalCollaboratorsTable({
  collaborators,
  summary,
}: {
  collaborators: ExternalCollaborator[];
  summary: CollabSummary;
}) {
  return (
    <div>
      <div className={styles.sectionTitle}>
        Outside collaborators with write/admin access
        {summary.elevated_count > 0 && (
          <span style={{ fontWeight: 400, fontSize: 12, color: 'var(--fg-muted)', marginLeft: 8 }}>
            {summary.elevated_count} elevated
          </span>
        )}
      </div>
      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Collaborator</th>
              <th>Repo</th>
              <th>Permission</th>
              <th>Added</th>
              <th>Last active</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {collaborators.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', color: 'var(--fg-muted)', padding: 24 }}>
                  No external collaborators found
                </td>
              </tr>
            )}
            {collaborators.map((c, i) => (
              <tr key={`${c.github_login}-${c.org}-${i}`}>
                <td>
                  <span className={styles.mention}>@{c.github_login}</span>
                </td>
                <td style={{ color: 'var(--fg-muted)' }}>{c.repo ?? `${c.org} (org-level)`}</td>
                <td>
                  <Label variant={c.role === 'admin' ? 'danger' : 'severe'}>{c.role}</Label>
                </td>
                <td style={{ color: 'var(--fg-muted)' }}>{formatDate(c.granted_at)}</td>
                <td style={{ color: 'var(--fg-muted)' }}>{formatDaysAgo(c.days_since_last_event)}</td>
                <td>
                  <Label variant={riskBadgeVariant(c)}>{riskBadgeText(c)}</Label>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DormantMembersTable({ dormant }: { dormant: DormantCollaborator[] }) {
  const sorted = [...dormant].sort((a, b) => b.days_inactive - a.days_inactive);

  return (
    <div>
      <div className={styles.sectionTitle}>Dormant members (90+ days inactive)</div>
      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Member</th>
              <th>Org</th>
              <th>Role</th>
              <th>Last seen</th>
              <th>Days inactive</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', color: 'var(--fg-muted)', padding: 24 }}>
                  No dormant members found
                </td>
              </tr>
            )}
            {sorted.map((d, i) => {
              const statusVariant = d.days_inactive >= 90 ? 'danger' : 'attention';
              const statusText = d.days_inactive >= 90 ? 'dormant' : 'at risk';
              return (
                <tr key={`${d.github_login}-${d.org}-${i}`}>
                  <td>
                    <span className={styles.mention}>@{d.github_login}</span>
                  </td>
                  <td style={{ color: 'var(--fg-muted)' }}>{d.org}</td>
                  <td>
                    <Label variant={d.role === 'outside_collaborator' ? 'severe' : 'muted'}>
                      {d.role === 'outside_collaborator' ? 'outside collaborator' : d.role}
                    </Label>
                  </td>
                  <td style={{ color: 'var(--fg-muted)' }}>{formatDate(d.last_event_at)}</td>
                  <td className={styles.numCol}>
                    <Label variant={d.days_inactive >= 90 ? 'danger' : 'attention'}>
                      {daysLabel(d.days_inactive)}
                    </Label>
                  </td>
                  <td>
                    <Label variant={statusVariant}>{statusText}</Label>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TokenAgeDistribution({ tokens }: { tokens: PatToken[] }) {
  const { labels, counts } = buildPatAgeBuckets(tokens);

  return (
    <div>
      <div className={styles.sectionTitle}>Token age distribution</div>
      <div className={styles.chartWrap}>
        <BarChart
          xAxisData={labels}
          series={[
            {
              name: 'Tokens',
              data: counts,
              color: '#58a6ff',
            },
          ]}
          height={180}
        />
      </div>
    </div>
  );
}

/* ---------- main pane ---------- */

export function AccessIdentityPane() {
  const patQuery = useQuery({
    queryKey: ['health', 'pat-health'],
    queryFn: () => getPatHealth(),
    staleTime: 60_000,
  });

  const bypassQuery = useQuery({
    queryKey: ['health', 'bypass-offenders'],
    queryFn: () => getBypassOffenders(),
    staleTime: 60_000,
  });

  const collabQuery = useQuery({
    queryKey: ['health', 'external-collaborators'],
    queryFn: () => getExternalCollaborators(),
    staleTime: 60_000,
  });

  const dormantQuery = useQuery({
    queryKey: ['health', 'dormant-collaborators'],
    queryFn: () => getDormantCollaborators(),
    staleTime: 60_000,
  });

  const isLoading =
    patQuery.isLoading || bypassQuery.isLoading || collabQuery.isLoading || dormantQuery.isLoading;
  const isError =
    patQuery.isError || bypassQuery.isError || collabQuery.isError || dormantQuery.isError;

  if (isLoading) {
    return (
      <div className={styles.centered}>
        <Spinner size={28} />
      </div>
    );
  }

  if (isError) {
    const retryAll = () => {
      void patQuery.refetch();
      void bypassQuery.refetch();
      void collabQuery.refetch();
      void dormantQuery.refetch();
    };
    return <ErrorBanner message="Failed to load access & identity data" onRetry={retryAll} />;
  }

  const patData = patQuery.data;
  const offenders = bypassQuery.data?.offenders ?? [];
  const collaborators = collabQuery.data?.collaborators ?? [];
  const collabSummary = collabQuery.data?.summary ?? {
    total_active: 0,
    org_level_count: 0,
    elevated_count: 0,
    dormant_count: 0,
  };
  const dormant = dormantQuery.data?.dormant ?? [];
  const allTokens = patData?.tokens ?? [];

  return (
    <div className={styles.pane}>
      <SampleDataBanner message="Member activity metrics are derived from audit log actor timestamps. Connect additional data sources for license seat counts and detailed role information." />

      <div className={styles.grid2}>
        <MemberActivityOverview dormant={dormant} />
        <PatHealthSnapshot
          noExpiryCount={patData?.summary.no_expiry_count ?? 0}
          expiredCount={patData?.summary.expired_count ?? 0}
          stale90dCount={patData?.summary.stale_90d_count ?? 0}
        />
      </div>

      <DormantMembersTable dormant={dormant} />

      <BypassOffendersTable offenders={offenders} />

      <ExternalCollaboratorsTable collaborators={collaborators} summary={collabSummary} />

      <TokenAgeDistribution tokens={allTokens} />
    </div>
  );
}
