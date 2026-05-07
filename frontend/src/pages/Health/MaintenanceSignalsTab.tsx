import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { getMaintenanceSignals } from '../../api/healthSignals';
import type {
  MaintenanceStaleRepo,
  MaintenanceEmptyRepo,
  MaintenanceArchivedCandidate,
} from '../../api/healthSignals';
import { formatDateOnly } from '../../utils/dates';
import styles from './MaintenanceSignalsTab.module.css';

const staleColumns: ColumnDef<MaintenanceStaleRepo>[] = [
  {
    key: 'repo',
    header: 'Repository',
    sortable: true,
    filterable: true,
    render: (row) => (
      <strong>
        {row.org}/{row.repo}
      </strong>
    ),
    sortValue: (row) => `${row.org}/${row.repo}`,
    filterValue: (row) => `${row.org}/${row.repo}`,
    helpText: 'Repository with no event activity beyond the staleness threshold.',
  },
  {
    key: 'last_activity',
    header: 'Last Activity',
    sortable: true,
    render: (row) => (
      <span style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(row.last_event_at)}</span>
    ),
    sortValue: (row) => row.last_event_at,
    helpText: 'Date of the most recent audit log event for this repository.',
  },
  {
    key: 'days_inactive',
    header: 'Days Inactive',
    sortable: true,
    render: (row) => (
      <Label variant={row.days_since_activity > 365 ? 'danger' : 'attention'}>
        {row.days_since_activity} days
      </Label>
    ),
    sortValue: (row) => row.days_since_activity,
    helpText: 'Number of days since the last event. Consider archiving repos inactive >365 days.',
  },
  {
    key: 'action',
    header: 'Action',
    render: (row) => (
      <span style={{ fontSize: 12, color: 'var(--fg-muted)' }}>
        {row.days_since_activity > 365 ? 'Archive or delete' : 'Review and assess'}
      </span>
    ),
    helpText: 'Suggested action based on the inactivity period.',
  },
];

const emptyColumns: ColumnDef<MaintenanceEmptyRepo>[] = [
  {
    key: 'repo',
    header: 'Repository',
    sortable: true,
    filterable: true,
    render: (row) => (
      <strong>
        {row.org}/{row.repo}
      </strong>
    ),
    sortValue: (row) => `${row.org}/${row.repo}`,
    filterValue: (row) => `${row.org}/${row.repo}`,
    helpText: 'Repository created but never pushed to within 30 days.',
  },
  {
    key: 'created',
    header: 'Created',
    sortable: true,
    render: (row) => (
      <span style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(row.created_at)}</span>
    ),
    sortValue: (row) => row.created_at,
    helpText: 'Date the repository was created.',
  },
  {
    key: 'action',
    header: 'Action',
    render: () => (
      <span style={{ fontSize: 12, color: 'var(--fg-muted)' }}>Delete or populate</span>
    ),
    helpText: 'Empty repositories should be deleted or populated with initial content.',
  },
];

const archivedCandidateColumns: ColumnDef<MaintenanceArchivedCandidate>[] = [
  {
    key: 'repo',
    header: 'Repository',
    sortable: true,
    filterable: true,
    render: (row) => (
      <strong>
        {row.org}/{row.repo}
      </strong>
    ),
    sortValue: (row) => `${row.org}/${row.repo}`,
    filterValue: (row) => `${row.org}/${row.repo}`,
    helpText: 'Repository with minimal activity that may be a candidate for archiving.',
  },
  {
    key: 'events',
    header: 'Events (180d)',
    sortable: true,
    render: (row) => <span style={{ fontVariantNumeric: 'tabular-nums' }}>{row.event_count}</span>,
    sortValue: (row) => row.event_count,
    helpText: 'Total number of audit log events in the last 180 days.',
  },
  {
    key: 'last_activity',
    header: 'Last Activity',
    sortable: true,
    render: (row) => (
      <span style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(row.last_event_at)}</span>
    ),
    sortValue: (row) => row.last_event_at,
    helpText: 'Most recent event date for this repository.',
  },
  {
    key: 'action',
    header: 'Action',
    render: () => (
      <span style={{ fontSize: 12, color: 'var(--fg-muted)' }}>Consider archiving</span>
    ),
    helpText: 'Repositories with minimal activity may be candidates for archiving.',
  },
];

export function MaintenanceSignalsTab() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['health', 'maintenance-signals'],
    queryFn: () => getMaintenanceSignals(),
    staleTime: 60_000,
  });

  const staleRepos = data?.stale_repos ?? [];
  const emptyRepos = data?.empty_repos ?? [];
  const archivedCandidates = data?.archived_candidates ?? [];
  const summary = data?.summary;
  const staleCount = summary?.stale_count ?? staleRepos.length;
  const emptyCount = summary?.empty_count ?? emptyRepos.length;
  const archivedCount = summary?.archived_candidate_count ?? archivedCandidates.length;
  const totalIssues = staleCount + emptyCount + archivedCount;

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
          value={String(staleCount)}
          label="Stale repos"
          accent={staleCount > 0}
          helpText="Repositories with no activity in the last 180 days."
        />
        <MetricCard
          value={String(emptyCount)}
          label="Empty repos"
          accent={emptyCount > 0}
          helpText="Repositories created but never pushed to."
        />
        <MetricCard
          value={String(archivedCount)}
          label="Archive candidates"
          helpText="Repositories with minimal activity that could be archived."
        />
        <MetricCard
          value={String(totalIssues)}
          label="Total issues"
          accent={totalIssues > 0}
          helpText="Combined count of all maintenance issues requiring attention."
        />
      </div>

      {isError && (
        <ErrorBanner message="Failed to load maintenance signals" onRetry={() => void refetch()} />
      )}

      {!isError && totalIssues === 0 && (
        <div style={{ color: 'var(--fg-muted)', fontSize: 13, padding: 16, textAlign: 'center' }}>
          No maintenance issues detected — all repositories are healthy
        </div>
      )}

      {!isError && staleRepos.length > 0 && (
        <>
          <div className={styles.sectionTitle}>Stale repositories (no activity &gt; 180 days)</div>
          <div className={styles.tableWrap}>
            <DataTable
              columns={staleColumns}
              data={staleRepos}
              rowKey={(row) => `${row.org}/${row.repo}`}
              emptyMessage="No stale repositories"
            />
          </div>
        </>
      )}

      {!isError && emptyRepos.length > 0 && (
        <>
          <div className={styles.sectionTitle}>Empty repositories</div>
          <div className={styles.tableWrap}>
            <DataTable
              columns={emptyColumns}
              data={emptyRepos}
              rowKey={(row) => `${row.org}/${row.repo}`}
              emptyMessage="No empty repositories"
            />
          </div>
        </>
      )}

      {!isError && archivedCandidates.length > 0 && (
        <>
          <div className={styles.sectionTitle}>Archive candidates</div>
          <div className={styles.tableWrap}>
            <DataTable
              columns={archivedCandidateColumns}
              data={archivedCandidates}
              rowKey={(row) => `${row.org}/${row.repo}`}
              emptyMessage="No archive candidates"
            />
          </div>
        </>
      )}

      <div className={styles.sourceNote}>
        ℹ️ Derived from repository event activity patterns. Stale threshold: 180 days. Empty repos
        identified by creation event with no subsequent push within 30 days.
      </div>
    </div>
  );
}
