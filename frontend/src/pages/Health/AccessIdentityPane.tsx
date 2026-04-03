import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { BarChart } from '../../components/charts/BarChart';
import { DrilldownModal } from '../../components/primitives/DrilldownModal';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
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
import { formatDateOnly } from '../../utils/dates';
import styles from './AccessIdentityPane.module.css';

/* ---------- helpers ---------- */

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
  const [drilldown, setDrilldown] = useState<'dormant' | 'at-risk' | 'new' | null>(null);

  const dormantMembers = dormant.filter((d) => d.days_inactive >= 90);
  const atRiskMembers = dormant.filter((d) => d.days_inactive >= 60 && d.days_inactive < 90);
  const newMembers = dormant.filter((d) => d.days_inactive < 30);

  const dormantCount = dormantMembers.length;
  const atRiskCount = atRiskMembers.length;
  const newCount = newMembers.length;

  const drilldownData =
    drilldown === 'dormant'
      ? dormantMembers
      : drilldown === 'at-risk'
        ? atRiskMembers
        : drilldown === 'new'
          ? newMembers
          : [];
  const drilldownTitle =
    drilldown === 'dormant'
      ? 'Dormant members (90+ days inactive)'
      : drilldown === 'at-risk'
        ? 'At-risk members (60–90 days inactive)'
        : 'New members (joined in last 30 days)';

  const memberColumns: ColumnDef<DormantCollaborator>[] = [
    {
      key: 'login',
      header: 'Member',
      sortable: true,
      filterable: true,
      render: (d) => `@${d.github_login}`,
      sortValue: (d) => d.github_login,
      filterValue: (d) => d.github_login,
    },
    { key: 'org', header: 'Organization', render: (d) => d.org },
    {
      key: 'role',
      header: 'Role',
      render: (d) => (d.role === 'outside_collaborator' ? 'outside collaborator' : d.role),
    },
    {
      key: 'last_seen',
      header: 'Last Seen',
      render: (d) => (d.last_event_at ? formatDateOnly(d.last_event_at) : '—'),
    },
    {
      key: 'days',
      header: 'Days Inactive',
      sortable: true,
      render: (d) => String(d.days_inactive),
      sortValue: (d) => d.days_inactive,
    },
  ];

  function handleKeyDown(e: React.KeyboardEvent, target: 'dormant' | 'at-risk' | 'new') {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setDrilldown(target);
    }
  }

  return (
    <Card>
      <CardHeader>Member activity overview</CardHeader>
      <div className={styles.statusList}>
        <div className={`${styles.statusRow} ${styles.statusRowDanger}`}>
          <Label variant="danger">dormant</Label>
          <div className={styles.statusBody}>
            <span
              className={styles.clickableStat}
              onClick={() => setDrilldown('dormant')}
              role="button"
              tabIndex={0}
              aria-label={`${dormantCount} dormant members – click to view details`}
              onKeyDown={(e) => handleKeyDown(e, 'dormant')}
            >
              <strong>
                {dormantCount} {dormantCount === 1 ? 'member' : 'members'}
              </strong>
            </span>{' '}
            no activity in 90+ days
          </div>
          <span className={styles.statusNote}>still licensed</span>
        </div>
        <div className={`${styles.statusRow} ${styles.statusRowAttention}`}>
          <Label variant="attention">at risk</Label>
          <div className={styles.statusBody}>
            <span
              className={styles.clickableStat}
              onClick={() => setDrilldown('at-risk')}
              role="button"
              tabIndex={0}
              aria-label={`${atRiskCount} at-risk members – click to view details`}
              onKeyDown={(e) => handleKeyDown(e, 'at-risk')}
            >
              <strong>
                {atRiskCount} {atRiskCount === 1 ? 'member' : 'members'}
              </strong>
            </span>{' '}
            no activity in 60–90 days
          </div>
          <span className={styles.statusNote}>trending dormant</span>
        </div>
        <div className={`${styles.statusRow} ${styles.statusRowSuccess}`}>
          <Label variant="success">new</Label>
          <div className={styles.statusBody}>
            <span
              className={styles.clickableStat}
              onClick={() => setDrilldown('new')}
              role="button"
              tabIndex={0}
              aria-label={`${newCount} new members – click to view details`}
              onKeyDown={(e) => handleKeyDown(e, 'new')}
            >
              <strong>
                {newCount} {newCount === 1 ? 'member' : 'members'}
              </strong>
            </span>{' '}
            joined in last 30 days
          </div>
          <span className={styles.statusNote}>onboarding period</span>
        </div>
      </div>
      <div className={styles.cardFooter}>
        ℹ Derived from <code className={styles.codeSnippet}>org.add_member</code>,{' '}
        <code className={styles.codeSnippet}>user.login</code>, and per-actor event timestamps
      </div>
      <DrilldownModal
        open={drilldown !== null}
        onClose={() => setDrilldown(null)}
        title={drilldownTitle}
        data={drilldownData}
        columns={memberColumns}
        rowKey={(d) => `${d.github_login}-${d.org}`}
      />
    </Card>
  );
}

function PatHealthSnapshot({
  noExpiryCount,
  expiredCount,
  stale90dCount,
  tokens,
}: {
  noExpiryCount: number;
  expiredCount: number;
  stale90dCount: number;
  tokens: PatToken[];
}) {
  const [drilldown, setDrilldown] = useState<'no-expiry' | 'expiring' | 'stale' | null>(null);

  const noExpiryTokens = tokens.filter((t) => t.signal_type === 'no_expiry');
  const expiringTokens = tokens.filter((t) => t.signal_type === 'expired');
  const staleTokens = tokens.filter((t) => t.signal_type === 'stale_90d');

  const drilldownData =
    drilldown === 'no-expiry'
      ? noExpiryTokens
      : drilldown === 'expiring'
        ? expiringTokens
        : drilldown === 'stale'
          ? staleTokens
          : [];
  const drilldownTitle =
    drilldown === 'no-expiry'
      ? 'Tokens with no expiration date'
      : drilldown === 'expiring'
        ? 'Tokens expiring within 30 days'
        : 'Stale tokens (unused 90+ days)';

  const tokenColumns: ColumnDef<PatToken>[] = [
    {
      key: 'user',
      header: 'User',
      sortable: true,
      filterable: true,
      render: (t) => t.github_login,
      sortValue: (t) => t.github_login,
      filterValue: (t) => t.github_login,
    },
    { key: 'token_name', header: 'Token Name', render: (t) => t.token_name ?? '—' },
    { key: 'token_type', header: 'Type', render: (t) => t.token_type ?? '—' },
    { key: 'created', header: 'Created', render: (t) => formatDateOnly(t.created_at) },
    {
      key: 'age',
      header: 'Age (days)',
      sortable: true,
      render: (t) => String(t.age_days),
      sortValue: (t) => t.age_days,
    },
  ];

  function handleKeyDown(e: React.KeyboardEvent, target: 'no-expiry' | 'expiring' | 'stale') {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setDrilldown(target);
    }
  }

  return (
    <Card>
      <CardHeader>PAT health snapshot</CardHeader>
      <div className={styles.statusList}>
        <div className={`${styles.statusRow} ${styles.statusRowDanger}`}>
          <Label variant="danger">no expiry</Label>
          <div className={styles.statusBody}>
            <span
              className={styles.clickableStat}
              onClick={() => setDrilldown('no-expiry')}
              role="button"
              tabIndex={0}
              aria-label={`${noExpiryCount} tokens with no expiry – click to view details`}
              onKeyDown={(e) => handleKeyDown(e, 'no-expiry')}
            >
              <strong>
                {noExpiryCount} {noExpiryCount === 1 ? 'token' : 'tokens'}
              </strong>
            </span>{' '}
            with no expiration date
          </div>
          <span className={styles.statusNote}>never rotate</span>
        </div>
        <div className={`${styles.statusRow} ${styles.statusRowSevere}`}>
          <Label variant="severe">expiring soon</Label>
          <div className={styles.statusBody}>
            <span
              className={styles.clickableStat}
              onClick={() => setDrilldown('expiring')}
              role="button"
              tabIndex={0}
              aria-label={`${expiredCount} tokens expiring soon – click to view details`}
              onKeyDown={(e) => handleKeyDown(e, 'expiring')}
            >
              <strong>
                {expiredCount} {expiredCount === 1 ? 'token' : 'tokens'}
              </strong>
            </span>{' '}
            expire within 30 days
          </div>
          <span className={styles.statusNote}>may break automations</span>
        </div>
        <div className={`${styles.statusRow} ${styles.statusRowMuted}`}>
          <Label variant="muted">stale</Label>
          <div className={styles.statusBody}>
            <span
              className={styles.clickableStat}
              onClick={() => setDrilldown('stale')}
              role="button"
              tabIndex={0}
              aria-label={`${stale90dCount} stale tokens – click to view details`}
              onKeyDown={(e) => handleKeyDown(e, 'stale')}
            >
              <strong>
                {stale90dCount} {stale90dCount === 1 ? 'token' : 'tokens'}
              </strong>
            </span>{' '}
            not used in 90+ days
          </div>
          <span className={styles.statusNote}>candidates for revocation</span>
        </div>
      </div>
      <div className={styles.cardFooter}>
        ℹ Derived from <code className={styles.codeSnippet}>personal_access_token.*</code> events
        and <code className={styles.codeSnippet}>authentication.token</code> usage in audit log
      </div>
      <DrilldownModal
        open={drilldown !== null}
        onClose={() => setDrilldown(null)}
        title={drilldownTitle}
        data={drilldownData}
        columns={tokenColumns}
        rowKey={(t) => t.token_id ?? `${t.github_login}-${t.created_at}`}
      />
    </Card>
  );
}

function BypassOffendersTable({ offenders }: { offenders: BypassOffender[] }) {
  const columns: ColumnDef<BypassOffender>[] = [
    {
      key: 'actor',
      header: 'Actor',
      sortable: true,
      filterable: true,
      render: (o) => <span className={styles.mention}>@{o.actor}</span>,
      sortValue: (o) => o.actor,
      filterValue: (o) => o.actor,
    },
    {
      key: 'total_bypasses',
      header: 'Total bypasses',
      sortable: true,
      render: (o) => (
        <span className={styles.numCol}>
          <Label
            variant={
              o.total_bypasses > 10
                ? 'danger'
                : o.total_bypasses > 5
                  ? 'attention'
                  : 'muted'
            }
          >
            {o.total_bypasses}
          </Label>
        </span>
      ),
      sortValue: (o) => o.total_bypasses,
    },
    {
      key: 'push_protection',
      header: 'Push protection',
      sortable: true,
      render: (o) => <span className={styles.numCol}>{o.push_protection_bypasses}</span>,
      sortValue: (o) => o.push_protection_bypasses,
    },
    {
      key: 'branch_policy',
      header: 'Branch policy',
      sortable: true,
      render: (o) => <span className={styles.numCol}>{o.branch_protection_overrides}</span>,
      sortValue: (o) => o.branch_protection_overrides,
    },
    {
      key: 'active_days',
      header: 'Active days',
      sortable: true,
      render: (o) => <span className={styles.numCol}>{o.active_days}</span>,
      sortValue: (o) => o.active_days,
    },
    {
      key: 'last_bypass',
      header: 'Last bypass',
      sortable: true,
      render: (o) => (
        <span style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(o.last_bypass_at)}</span>
      ),
      sortValue: (o) => o.last_bypass_at,
    },
  ];

  return (
    <div>
      <div className={styles.sectionTitle}>Bypass repeat offenders</div>
      <div className={styles.tableWrap}>
        <DataTable
          columns={columns}
          data={offenders}
          rowKey={(o) => o.actor}
          emptyMessage="No bypass offenders found"
        />
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
  const columns: ColumnDef<ExternalCollaborator>[] = [
    {
      key: 'collaborator',
      header: 'Collaborator',
      sortable: true,
      filterable: true,
      render: (c) => <span className={styles.mention}>@{c.github_login}</span>,
      sortValue: (c) => c.github_login,
      filterValue: (c) => c.github_login,
    },
    {
      key: 'repo',
      header: 'Repo',
      sortable: true,
      filterable: true,
      render: (c) => (
        <span style={{ color: 'var(--fg-muted)' }}>{c.repo ?? `${c.org} (org-level)`}</span>
      ),
      sortValue: (c) => c.repo ?? c.org,
      filterValue: (c) => c.repo ?? c.org,
    },
    {
      key: 'permission',
      header: 'Permission',
      sortable: true,
      render: (c) => <Label variant={c.role === 'admin' ? 'danger' : 'severe'}>{c.role}</Label>,
      sortValue: (c) => c.role,
    },
    {
      key: 'added',
      header: 'Added',
      sortable: true,
      render: (c) => (
        <span style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(c.granted_at)}</span>
      ),
      sortValue: (c) => c.granted_at,
    },
    {
      key: 'last_active',
      header: 'Last active',
      sortable: true,
      render: (c) => (
        <span style={{ color: 'var(--fg-muted)' }}>
          {formatDaysAgo(c.days_since_last_event)}
        </span>
      ),
      sortValue: (c) => c.days_since_last_event ?? Infinity,
    },
    {
      key: 'risk',
      header: 'Risk',
      sortable: true,
      render: (c) => <Label variant={riskBadgeVariant(c)}>{riskBadgeText(c)}</Label>,
      sortValue: (c) => {
        const days = c.days_since_last_event;
        if (days !== null && days > 90) return 3;
        if (c.role === 'admin') return 2;
        if (days !== null && days > 30) return 1;
        return 0;
      },
    },
  ];

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
        <DataTable
          columns={columns}
          data={collaborators}
          rowKey={(c) => `${c.github_login}-${c.org}-${c.repo ?? 'org'}`}
          emptyMessage="No external collaborators found"
        />
      </div>
    </div>
  );
}

function DormantMembersTable({ dormant }: { dormant: DormantCollaborator[] }) {
  const sorted = [...dormant].sort((a, b) => b.days_inactive - a.days_inactive);

  const columns: ColumnDef<DormantCollaborator>[] = [
    {
      key: 'member',
      header: 'Member',
      sortable: true,
      filterable: true,
      render: (d) => <span className={styles.mention}>@{d.github_login}</span>,
      sortValue: (d) => d.github_login,
      filterValue: (d) => d.github_login,
    },
    {
      key: 'org',
      header: 'Org',
      sortable: true,
      filterable: true,
      render: (d) => <span style={{ color: 'var(--fg-muted)' }}>{d.org}</span>,
      sortValue: (d) => d.org,
      filterValue: (d) => d.org,
    },
    {
      key: 'role',
      header: 'Role',
      sortable: true,
      render: (d) => (
        <Label variant={d.role === 'outside_collaborator' ? 'severe' : 'muted'}>
          {d.role === 'outside_collaborator' ? 'outside collaborator' : d.role}
        </Label>
      ),
      sortValue: (d) => d.role,
    },
    {
      key: 'last_seen',
      header: 'Last seen',
      sortable: true,
      render: (d) => (
        <span style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(d.last_event_at)}</span>
      ),
      sortValue: (d) => d.last_event_at ?? '',
    },
    {
      key: 'days_inactive',
      header: 'Days inactive',
      sortable: true,
      render: (d) => (
        <span className={styles.numCol}>
          <Label variant={d.days_inactive >= 90 ? 'danger' : 'attention'}>
            {daysLabel(d.days_inactive)}
          </Label>
        </span>
      ),
      sortValue: (d) => d.days_inactive,
    },
    {
      key: 'status',
      header: 'Status',
      sortable: true,
      render: (d) => {
        const statusVariant = d.days_inactive >= 90 ? 'danger' : 'attention';
        const statusText = d.days_inactive >= 90 ? 'dormant' : 'at risk';
        return <Label variant={statusVariant}>{statusText}</Label>;
      },
      sortValue: (d) => d.days_inactive,
    },
  ];

  return (
    <div>
      <div className={styles.sectionTitle}>Dormant members (90+ days inactive)</div>
      <div className={styles.tableWrap}>
        <DataTable
          columns={columns}
          data={sorted}
          rowKey={(d) => `${d.github_login}-${d.org}-${d.days_inactive}`}
          emptyMessage="No dormant members found"
        />
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
          tokens={allTokens}
        />
      </div>

      <DormantMembersTable dormant={dormant} />

      <BypassOffendersTable offenders={offenders} />

      <ExternalCollaboratorsTable collaborators={collaborators} summary={collabSummary} />

      <TokenAgeDistribution tokens={allTokens} />
    </div>
  );
}
