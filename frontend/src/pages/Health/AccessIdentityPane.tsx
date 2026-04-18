import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { BarChart } from '../../components/charts/BarChart';
import { DrilldownDrawer } from '../../components/primitives/DrilldownDrawer';
import { Drawer } from '../../components/primitives/Drawer';
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
      helpText: 'GitHub username of the organization member. Derived from audit log actor fields.',
    },
    {
      key: 'org',
      header: 'Organization',
      render: (d) => d.org,
      helpText: 'The GitHub organization this member belongs to.',
    },
    {
      key: 'role',
      header: 'Role',
      render: (d) => (d.role === 'outside_collaborator' ? 'outside collaborator' : d.role),
      helpText:
        'Member role within the organization. Outside collaborators have limited access and should be reviewed periodically.',
    },
    {
      key: 'last_seen',
      header: 'Last Seen',
      render: (d) => (d.last_event_at ? formatDateOnly(d.last_event_at) : '—'),
      helpText:
        'Last recorded activity for this user from audit log events. Users inactive for 90+ days may be candidates for access review.',
    },
    {
      key: 'days',
      header: 'Days Inactive',
      sortable: true,
      render: (d) => String(d.days_inactive),
      sortValue: (d) => d.days_inactive,
      helpText:
        'Number of days since the last audit log event for this user. Consider removing access for users inactive 90+ days.',
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
      <DrilldownDrawer
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
      helpText: 'The GitHub user who owns this personal access token.',
    },
    {
      key: 'token_name',
      header: 'Token Name',
      render: (t) => t.token_name ?? '—',
      helpText:
        'Name assigned to the personal access token. Derived from personal_access_token.* audit events.',
    },
    {
      key: 'token_type',
      header: 'Type',
      render: (t) => t.token_type ?? '—',
      helpText:
        'Token type (classic or fine-grained). Fine-grained tokens are recommended for least-privilege access.',
    },
    {
      key: 'created',
      header: 'Created',
      render: (t) => formatDateOnly(t.created_at),
      helpText:
        'Date the token was created. Older tokens may have broader scopes and should be audited.',
    },
    {
      key: 'age',
      header: 'Age (days)',
      sortable: true,
      render: (t) => String(t.age_days),
      sortValue: (t) => t.age_days,
      helpText:
        'Number of days since token creation. Tokens older than 90 days without rotation increase risk.',
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
      <DrilldownDrawer
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
  const [selectedRow, setSelectedRow] = useState<BypassOffender | null>(null);
  const columns: ColumnDef<BypassOffender>[] = [
    {
      key: 'actor',
      header: 'Actor',
      sortable: true,
      filterable: true,
      render: (o) => <span className={styles.mention}>@{o.actor}</span>,
      sortValue: (o) => o.actor,
      filterValue: (o) => o.actor,
      helpText:
        'GitHub user who bypassed branch protection or push protection. Derived from audit log actor fields.',
    },
    {
      key: 'total_bypasses',
      header: 'Total bypasses',
      sortable: true,
      render: (o) => (
        <span className={styles.numCol}>
          <Label
            variant={
              o.total_bypasses > 10 ? 'danger' : o.total_bypasses > 5 ? 'attention' : 'muted'
            }
          >
            {o.total_bypasses}
          </Label>
        </span>
      ),
      sortValue: (o) => o.total_bypasses,
      helpText:
        'Combined count of push protection and branch policy bypasses. Users with 10+ bypasses should be reviewed.',
    },
    {
      key: 'push_protection',
      header: 'Push protection',
      sortable: true,
      render: (o) => <span className={styles.numCol}>{o.push_protection_bypasses}</span>,
      sortValue: (o) => o.push_protection_bypasses,
      helpText:
        'Number of push protection bypasses. Derived from secret_scanning_push_protection.bypass events.',
    },
    {
      key: 'branch_policy',
      header: 'Branch policy',
      sortable: true,
      render: (o) => <span className={styles.numCol}>{o.branch_protection_overrides}</span>,
      sortValue: (o) => o.branch_protection_overrides,
      helpText:
        'Number of branch protection overrides. Derived from protected_branch.policy_override events.',
    },
    {
      key: 'active_days',
      header: 'Active days',
      sortable: true,
      render: (o) => <span className={styles.numCol}>{o.active_days}</span>,
      sortValue: (o) => o.active_days,
      helpText:
        'Number of distinct days this actor performed bypasses. Frequent bypass activity warrants a policy review.',
    },
    {
      key: 'last_bypass',
      header: 'Last bypass',
      sortable: true,
      render: (o) => (
        <span style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(o.last_bypass_at)}</span>
      ),
      sortValue: (o) => o.last_bypass_at,
      helpText:
        'Date of the most recent bypass event. Recent bypasses may need immediate investigation.',
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
          onRowClick={(row) => setSelectedRow(row)}
        />
      </div>
      <Drawer
        open={!!selectedRow}
        onClose={() => setSelectedRow(null)}
        title="Bypass Offender Details"
      >
        {selectedRow && (
          <dl style={{ padding: '16px' }}>
            {Object.entries(selectedRow).map(([key, value]) => (
              <div key={key} style={{ marginBottom: 8 }}>
                <dt style={{ fontSize: '0.8em', color: 'var(--fg-muted)', marginBottom: 2 }}>
                  {key}
                </dt>
                <dd style={{ margin: 0 }}>{String(value ?? '—')}</dd>
              </div>
            ))}
          </dl>
        )}
      </Drawer>
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
  const [selectedRow, setSelectedRow] = useState<ExternalCollaborator | null>(null);
  const columns: ColumnDef<ExternalCollaborator>[] = [
    {
      key: 'collaborator',
      header: 'Collaborator',
      sortable: true,
      filterable: true,
      render: (c) => <span className={styles.mention}>@{c.github_login}</span>,
      sortValue: (c) => c.github_login,
      filterValue: (c) => c.github_login,
      helpText:
        'GitHub username of the outside collaborator. Derived from org.add_outside_collaborator audit events.',
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
      helpText:
        'Repository or org-level scope of access. Org-level collaborators have broader access and should be reviewed.',
    },
    {
      key: 'permission',
      header: 'Permission',
      sortable: true,
      render: (c) => <Label variant={c.role === 'admin' ? 'danger' : 'severe'}>{c.role}</Label>,
      sortValue: (c) => c.role,
      helpText:
        'Permission level granted. Admin-level access for outside collaborators is high risk and should be time-limited.',
    },
    {
      key: 'added',
      header: 'Added',
      sortable: true,
      render: (c) => (
        <span style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(c.granted_at)}</span>
      ),
      sortValue: (c) => c.granted_at,
      helpText:
        'Date the collaborator was granted access. Derived from member.add or org.add_outside_collaborator events.',
    },
    {
      key: 'last_active',
      header: 'Last active',
      sortable: true,
      render: (c) => (
        <span style={{ color: 'var(--fg-muted)' }}>{formatDaysAgo(c.days_since_last_event)}</span>
      ),
      sortValue: (c) => c.days_since_last_event ?? Infinity,
      helpText:
        'Days since last activity from audit log events. Collaborators inactive 90+ days are candidates for access removal.',
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
      helpText:
        'Computed risk level based on inactivity duration and permission level. Admin access with dormancy is highest risk.',
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
          onRowClick={(row) => setSelectedRow(row)}
        />
      </div>
      <Drawer
        open={!!selectedRow}
        onClose={() => setSelectedRow(null)}
        title="External Collaborator Details"
      >
        {selectedRow && (
          <dl style={{ padding: '16px' }}>
            {Object.entries(selectedRow).map(([key, value]) => (
              <div key={key} style={{ marginBottom: 8 }}>
                <dt style={{ fontSize: '0.8em', color: 'var(--fg-muted)', marginBottom: 2 }}>
                  {key}
                </dt>
                <dd style={{ margin: 0 }}>{String(value ?? '—')}</dd>
              </div>
            ))}
          </dl>
        )}
      </Drawer>
    </div>
  );
}

function DormantMembersTable({ dormant }: { dormant: DormantCollaborator[] }) {
  const [selectedRow, setSelectedRow] = useState<DormantCollaborator | null>(null);
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
      helpText: 'GitHub login of the dormant member. Derived from audit log actor fields.',
    },
    {
      key: 'org',
      header: 'Org',
      sortable: true,
      filterable: true,
      render: (d) => <span style={{ color: 'var(--fg-muted)' }}>{d.org}</span>,
      sortValue: (d) => d.org,
      filterValue: (d) => d.org,
      helpText:
        'Organization the member belongs to. Members may be dormant in one org but active in another.',
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
      helpText:
        'Organization role of the dormant member. Outside collaborators should be reviewed first for removal.',
    },
    {
      key: 'last_seen',
      header: 'Last seen',
      sortable: true,
      render: (d) => (
        <span style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(d.last_event_at)}</span>
      ),
      sortValue: (d) => d.last_event_at ?? '',
      helpText:
        'Last recorded activity for this user from audit log events. Users inactive for 90+ days may be candidates for access review.',
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
      helpText:
        'Number of days since the last audit log event. 90+ days qualifies as dormant; consider removing access to reclaim licenses.',
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
      helpText:
        'Dormancy status based on inactivity threshold. "Dormant" (90+ days) members still consume a license seat.',
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
          onRowClick={(row) => setSelectedRow(row)}
        />
      </div>
      <Drawer
        open={!!selectedRow}
        onClose={() => setSelectedRow(null)}
        title="Dormant Member Details"
      >
        {selectedRow && (
          <dl style={{ padding: '16px' }}>
            {Object.entries(selectedRow).map(([key, value]) => (
              <div key={key} style={{ marginBottom: 8 }}>
                <dt style={{ fontSize: '0.8em', color: 'var(--fg-muted)', marginBottom: 2 }}>
                  {key}
                </dt>
                <dd style={{ margin: 0 }}>{String(value ?? '—')}</dd>
              </div>
            ))}
          </dl>
        )}
      </Drawer>
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
