import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { getCopilotTeams } from '../../api/copilotMetrics';
import type { CopilotTeam } from '../../api/copilotMetrics';
import { ApiError } from '../../api/client';
import styles from './Copilot.module.css';

const teamColumns: ColumnDef<CopilotTeam>[] = [
  {
    key: 'team_name',
    header: 'Team',
    sortable: true,
    filterable: true,
    helpText: 'The name of the team',
    render: (team) => <span style={{ fontWeight: 600 }}>{team.team_name}</span>,
    sortValue: (team) => team.team_name,
    filterValue: (team) => team.team_name,
  },
  {
    key: 'org',
    header: 'Org',
    sortable: true,
    filterable: true,
    helpText: 'The organization the team belongs to',
    render: (team) => <span style={{ color: 'var(--fg-muted)' }}>{team.org}</span>,
    sortValue: (team) => team.org,
    filterValue: (team) => team.org,
  },
  {
    key: 'total_members',
    header: 'Members',
    sortable: true,
    filterable: true,
    helpText: 'Total number of team members',
    render: (team) => <>{team.total_members}</>,
    sortValue: (team) => team.total_members,
    filterValue: (team) => String(team.total_members),
  },
  {
    key: 'active_users',
    header: 'Active',
    sortable: true,
    filterable: true,
    helpText: 'Number of members actively using Copilot',
    render: (team) => <span style={{ color: 'var(--success)' }}>{team.active_users}</span>,
    sortValue: (team) => team.active_users,
    filterValue: (team) => String(team.active_users),
  },
  {
    key: 'inactive_users',
    header: 'Inactive',
    sortable: true,
    filterable: true,
    helpText: 'Number of members not using Copilot',
    render: (team) => (
      <span style={{ color: team.inactive_users > 0 ? 'var(--danger)' : undefined }}>
        {team.inactive_users}
      </span>
    ),
    sortValue: (team) => team.inactive_users,
    filterValue: (team) => String(team.inactive_users),
  },
  {
    key: 'adoption_pct',
    header: 'Adoption',
    sortable: true,
    filterable: true,
    helpText: 'Percentage of team members actively using Copilot',
    render: (team) => (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div
          style={{
            width: 60,
            height: 6,
            background: 'var(--bg-tertiary)',
            borderRadius: 3,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${Math.min(team.adoption_pct, 100)}%`,
              height: '100%',
              background:
                team.adoption_pct >= 70
                  ? 'var(--success)'
                  : team.adoption_pct >= 30
                    ? 'var(--warning)'
                    : 'var(--danger)',
              borderRadius: 3,
            }}
          />
        </div>
        <span style={{ fontVariantNumeric: 'tabular-nums', fontSize: 12 }}>
          {team.adoption_pct}%
        </span>
      </div>
    ),
    sortValue: (team) => team.adoption_pct,
    filterValue: (team) => `${team.adoption_pct}%`,
  },
  {
    key: 'avg_days_since_activity',
    header: 'Avg Days Since Activity',
    sortable: true,
    filterable: true,
    helpText: 'Average number of days since team members last used Copilot',
    render: (team) => (
      <span style={{ fontVariantNumeric: 'tabular-nums' }}>{team.avg_days_since_activity}d</span>
    ),
    sortValue: (team) => team.avg_days_since_activity,
    filterValue: (team) => `${team.avg_days_since_activity}d`,
  },
  {
    key: 'status',
    header: 'Status',
    sortable: true,
    filterable: true,
    helpText: 'Whether the team is at risk based on adoption metrics',
    render: (team) =>
      team.at_risk ? (
        <span
          style={{
            background: 'rgba(248, 81, 73, 0.15)',
            color: 'var(--danger)',
            padding: '2px 8px',
            borderRadius: 12,
            fontSize: 11,
            fontWeight: 600,
          }}
        >
          At Risk
        </span>
      ) : (
        <span
          style={{
            background: 'rgba(63, 185, 80, 0.15)',
            color: 'var(--success)',
            padding: '2px 8px',
            borderRadius: 12,
            fontSize: 11,
            fontWeight: 600,
          }}
        >
          Healthy
        </span>
      ),
    sortValue: (team) => (team.at_risk ? 1 : 0),
    filterValue: (team) => (team.at_risk ? 'At Risk' : 'Healthy'),
  },
];

export function TeamsPane() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['copilot', 'teams'],
    queryFn: getCopilotTeams,
    staleTime: 30 * 60 * 1000,
  });

  if (isLoading) return <Spinner />;

  // For 404/soft unavailability, show the empty-state card rather than an error banner
  if (isError) {
    const is404 = error instanceof ApiError && error.status === 404;
    if (is404) {
      return (
        <Card>
          <CardHeader>No team data available</CardHeader>
          <p style={{ padding: '16px', color: 'var(--fg-muted)' }}>
            Team data requires synced org teams and Copilot seat information.
          </p>
        </Card>
      );
    }
    return <ErrorBanner message="Failed to load team data" onRetry={() => void refetch()} />;
  }

  if (data?.error) {
    return (
      <Card>
        <CardHeader>No team data available</CardHeader>
        <p style={{ padding: '16px', color: 'var(--fg-muted)' }}>
          {data.message ?? 'Team data requires synced org teams and Copilot seat information.'}
        </p>
      </Card>
    );
  }

  const teams = data?.teams ?? [];
  const atRiskCount = data?.at_risk_count ?? 0;

  return (
    <>
      <div className={styles.metricStrip}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{data?.total_teams ?? 0}</div>
          <div className={styles.statLabel}>Total Teams</div>
        </div>
        <div className={styles.statCard}>
          <div
            className={styles.statValue}
            style={{ color: atRiskCount > 0 ? 'var(--danger)' : undefined }}
          >
            {atRiskCount}
          </div>
          <div className={styles.statLabel}>At-Risk Teams</div>
        </div>
      </div>

      {teams.length === 0 ? (
        <Card>
          <CardHeader>No team data available</CardHeader>
          <p style={{ padding: '16px', color: 'var(--fg-muted)' }}>
            Team data requires synced org teams and Copilot seat information.
          </p>
        </Card>
      ) : (
        <Card>
          <CardHeader>Team Adoption Breakdown</CardHeader>
          <div style={{ overflowX: 'auto' }}>
            <DataTable<CopilotTeam>
              columns={teamColumns}
              data={teams}
              rowKey={(team) => `${team.org}/${team.team_slug}`}
              emptyMessage="No team data available"
            />
          </div>
        </Card>
      )}
    </>
  );
}
