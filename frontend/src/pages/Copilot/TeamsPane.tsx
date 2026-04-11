import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { getCopilotTeams } from '../../api/copilotMetrics';
import type { CopilotTeam } from '../../api/copilotMetrics';
import styles from './Copilot.module.css';

export function TeamsPane() {
  const {
    data,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['copilot', 'teams'],
    queryFn: getCopilotTeams,
    staleTime: 300_000,
  });

  if (isLoading) return <Spinner />;
  if (isError) return <ErrorBanner message="Failed to load team data" onRetry={() => void refetch()} />;
  if (data?.error) return <ErrorBanner message={data.message ?? 'Team data unavailable'} />;

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
          <div className={styles.statValue} style={{ color: atRiskCount > 0 ? 'var(--danger)' : undefined }}>
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
            <table className={styles.dataTable}>
              <thead>
                <tr>
                  <th>Team</th>
                  <th>Org</th>
                  <th>Members</th>
                  <th>Active</th>
                  <th>Inactive</th>
                  <th>Adoption</th>
                  <th>Avg Days Since Activity</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {teams.map((team: CopilotTeam) => (
                  <tr key={`${team.org}/${team.team_slug}`}>
                    <td style={{ fontWeight: 600 }}>{team.team_name}</td>
                    <td style={{ color: 'var(--fg-muted)' }}>{team.org}</td>
                    <td>{team.total_members}</td>
                    <td style={{ color: 'var(--success)' }}>{team.active_users}</td>
                    <td style={{ color: team.inactive_users > 0 ? 'var(--danger)' : undefined }}>
                      {team.inactive_users}
                    </td>
                    <td>
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
                    </td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {team.avg_days_since_activity}d
                    </td>
                    <td>
                      {team.at_risk ? (
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
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
