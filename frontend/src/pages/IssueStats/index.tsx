import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getIssueStatsByOrg, getIssueStatsByRepo } from '../../api/issueStats';
import type { OrgIssueStat, RepoIssueStat } from '../../api/issueStats';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { MetricCard } from '../../components/primitives/MetricCard';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import styles from './IssueStats.module.css';

type Tab = 'by-org' | 'by-repo';

const WINDOW_OPTIONS = [
  { label: '30 days', value: 30 },
  { label: '90 days', value: 90 },
  { label: '365 days', value: 365 },
];

function formatHours(hours: number | null): string {
  if (hours === null || hours === undefined) return '—';
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

function netOpenClass(netOpen: number): string {
  if (netOpen > 0) return styles.positive;
  if (netOpen < 0) return styles.negative;
  return styles.neutral;
}

const orgColumns: ColumnDef<OrgIssueStat>[] = [
  {
    key: 'org',
    header: 'Organization',
    sortable: true,
    filterable: true,
    render: (row) => row.org,
    sortValue: (row) => row.org,
    filterValue: (row) => row.org,
  },
  {
    key: 'opened',
    header: 'Opened',
    sortable: true,
    render: (row) => String(row.opened),
    sortValue: (row) => row.opened,
    helpText: 'Number of issues opened in the time window',
  },
  {
    key: 'closed',
    header: 'Closed',
    sortable: true,
    render: (row) => String(row.closed),
    sortValue: (row) => row.closed,
    helpText: 'Number of issues closed in the time window',
  },
  {
    key: 'net_open',
    header: 'Net Open',
    sortable: true,
    render: (row) => <span className={netOpenClass(row.net_open)}>{row.net_open > 0 ? '+' : ''}{row.net_open}</span>,
    sortValue: (row) => row.net_open,
    helpText: 'Opened minus Closed (positive = growing backlog)',
  },
  {
    key: 'avg_hours_to_close',
    header: 'Avg Time to Close',
    sortable: true,
    render: (row) => <span className={styles.mono}>{formatHours(row.avg_hours_to_close)}</span>,
    sortValue: (row) => row.avg_hours_to_close ?? 999999,
    helpText: 'Average time from issue opened to closed',
  },
];

const repoColumns: ColumnDef<RepoIssueStat>[] = [
  {
    key: 'org',
    header: 'Organization',
    sortable: true,
    filterable: true,
    render: (row) => row.org,
    sortValue: (row) => row.org,
    filterValue: (row) => row.org,
  },
  {
    key: 'repo',
    header: 'Repository',
    sortable: true,
    filterable: true,
    render: (row) => row.repo,
    sortValue: (row) => row.repo,
    filterValue: (row) => row.repo,
  },
  {
    key: 'opened',
    header: 'Opened',
    sortable: true,
    render: (row) => String(row.opened),
    sortValue: (row) => row.opened,
    helpText: 'Number of issues opened in the time window',
  },
  {
    key: 'closed',
    header: 'Closed',
    sortable: true,
    render: (row) => String(row.closed),
    sortValue: (row) => row.closed,
    helpText: 'Number of issues closed in the time window',
  },
  {
    key: 'net_open',
    header: 'Net Open',
    sortable: true,
    render: (row) => <span className={netOpenClass(row.net_open)}>{row.net_open > 0 ? '+' : ''}{row.net_open}</span>,
    sortValue: (row) => row.net_open,
    helpText: 'Opened minus Closed (positive = growing backlog)',
  },
  {
    key: 'avg_hours_to_close',
    header: 'Avg Time to Close',
    sortable: true,
    render: (row) => <span className={styles.mono}>{formatHours(row.avg_hours_to_close)}</span>,
    sortValue: (row) => row.avg_hours_to_close ?? 999999,
    helpText: 'Average time from issue opened to closed',
  },
];

export function IssueStatsPage() {
  const [tab, setTab] = useState<Tab>('by-org');
  const [windowDays, setWindowDays] = useState(30);

  const orgQuery = useQuery({
    queryKey: ['issue-stats', 'by-org', windowDays],
    queryFn: () => getIssueStatsByOrg({ window_days: windowDays }),
    staleTime: 60_000,
  });

  const repoQuery = useQuery({
    queryKey: ['issue-stats', 'by-repo', windowDays],
    queryFn: () => getIssueStatsByRepo({ window_days: windowDays }),
    staleTime: 60_000,
    enabled: tab === 'by-repo',
  });

  const activeQuery = tab === 'by-org' ? orgQuery : repoQuery;
  const totalOpened = orgQuery.data?.total_opened ?? 0;
  const totalClosed = orgQuery.data?.total_closed ?? 0;
  const orgCount = orgQuery.data?.orgs.length ?? 0;

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>Issue Stats</h1>
      <p className={styles.pageSub}>
        Issue activity metrics grouped by organization and repository.
      </p>

      {/* Summary cards */}
      <div className={styles.summaryRow}>
        <MetricCard value={String(totalOpened)} label="Issues Opened" />
        <MetricCard value={String(totalClosed)} label="Issues Closed" />
        <MetricCard
          value={totalOpened - totalClosed > 0 ? `+${totalOpened - totalClosed}` : String(totalOpened - totalClosed)}
          label="Net Open"
        />
        <MetricCard value={String(orgCount)} label="Organizations" />
      </div>

      {/* Control bar */}
      <div className={styles.controlBar}>
        <div className={styles.controlLeft}>
          <label htmlFor="issue-stats-window" className={styles.tabBadge}>
            Time window
          </label>
          <select
            id="issue-stats-window"
            className={styles.filterSelect}
            value={windowDays}
            onChange={(e) => setWindowDays(Number(e.target.value))}
          >
            {WINDOW_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Tabs */}
      <div className={styles.tabs}>
        <button
          className={[styles.tab, tab === 'by-org' && styles.tabActive].filter(Boolean).join(' ')}
          onClick={() => setTab('by-org')}
        >
          By Organization
          {orgQuery.data && <span className={styles.tabBadge}>{orgQuery.data.orgs.length}</span>}
        </button>
        <button
          className={[styles.tab, tab === 'by-repo' && styles.tabActive].filter(Boolean).join(' ')}
          onClick={() => setTab('by-repo')}
        >
          By Repository
          {repoQuery.data && (
            <span className={styles.tabBadge}>{repoQuery.data.repos.length}</span>
          )}
        </button>
      </div>

      {/* Content */}
      {activeQuery.isLoading && (
        <div className={styles.loadingWrap}>
          <Spinner size={28} />
        </div>
      )}

      {activeQuery.isError && (
        <ErrorBanner
          message={`Failed to load issue stats${tab === 'by-org' ? ' by org' : ' by repo'}`}
          onRetry={() => activeQuery.refetch()}
        />
      )}

      {activeQuery.isSuccess && tab === 'by-org' && orgQuery.data && (
        <>
          {orgQuery.data.orgs.length === 0 ? (
            <div className={styles.emptyState}>
              No issue data found in the selected time window
            </div>
          ) : (
            <DataTable
              columns={orgColumns}
              data={orgQuery.data.orgs}
              rowKey={(row) => row.org}
              emptyMessage="No issue data found"
            />
          )}
        </>
      )}

      {activeQuery.isSuccess && tab === 'by-repo' && repoQuery.data && (
        <>
          {repoQuery.data.repos.length === 0 ? (
            <div className={styles.emptyState}>
              No issue data found in the selected time window
            </div>
          ) : (
            <DataTable
              columns={repoColumns}
              data={repoQuery.data.repos}
              rowKey={(row) => `${row.org}/${row.repo}`}
              emptyMessage="No issue data found"
            />
          )}
        </>
      )}
    </div>
  );
}
