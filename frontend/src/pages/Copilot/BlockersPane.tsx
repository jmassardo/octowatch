import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { getCopilotBlockers } from '../../api/copilotMetrics';
import type { CopilotBlocker } from '../../api/copilotMetrics';
import styles from './Copilot.module.css';

const SEVERITY_COLORS: Record<string, string> = {
  high: 'var(--danger)',
  medium: 'var(--warning)',
  low: 'var(--fg-muted)',
};

const CATEGORY_LABELS: Record<string, string> = {
  no_seat: 'No Seat Assigned',
  inactive_seat: 'Inactive Seat',
  policy_restricted: 'Policy Restricted',
  content_excluded: 'Content Excluded',
};

export function BlockersPane() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['copilot', 'blockers'],
    queryFn: getCopilotBlockers,
    staleTime: 30 * 60 * 1000,
  });

  if (isLoading) return <Spinner />;
  if (isError)
    return <ErrorBanner message="Failed to load blocker data" onRetry={() => void refetch()} />;
  if (data?.error) return <ErrorBanner message={data.message ?? 'Blocker data unavailable'} />;

  const blockers = data?.blockers ?? [];
  const quickWins = data?.quick_wins ?? [];
  const summary = data?.summary;

  function handleExportBlockers() {
    const header = 'Category,Title,Count,Severity,Recommendation';
    const rows = blockers.map(
      (b: CopilotBlocker) =>
        `"${CATEGORY_LABELS[b.category] ?? b.category}","${b.title}",${b.count},${b.severity},"${b.recommendation}"`,
    );
    const csv = [header, ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'copilot-blockers.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <>
      {/* Summary strip */}
      {summary && (
        <div className={styles.metricStrip}>
          <div className={styles.statCard}>
            <div className={styles.statValue}>{summary.total_blockers}</div>
            <div className={styles.statLabel}>Total Blockers</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statValue} style={{ color: 'var(--danger)' }}>
              {summary.no_seat_count}
            </div>
            <div className={styles.statLabel}>Without Seats</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statValue} style={{ color: 'var(--warning)' }}>
              {summary.inactive_count}
            </div>
            <div className={styles.statLabel}>Inactive Seats</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statValue}>{summary.policy_restricted_count}</div>
            <div className={styles.statLabel}>Policy Restricted</div>
          </div>
        </div>
      )}

      {/* Quick wins */}
      {quickWins.length > 0 && (
        <Card>
          <CardHeader>Quick Wins</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            {quickWins.map((win, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: '10px 0',
                  borderBottom: idx < quickWins.length - 1 ? '1px solid var(--border)' : undefined,
                }}
              >
                <span style={{ fontSize: 18 }}>⚡</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{win.action}</div>
                  <div style={{ fontSize: 12, color: 'var(--fg-muted)' }}>{win.description}</div>
                </div>
                <div
                  style={{
                    background: 'rgba(63, 185, 80, 0.15)',
                    color: 'var(--success)',
                    padding: '2px 8px',
                    borderRadius: 12,
                    fontSize: 11,
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {win.impact}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Blockers list */}
      {blockers.length === 0 ? (
        <Card>
          <CardHeader>No blockers detected</CardHeader>
          <p style={{ padding: '16px', color: 'var(--fg-muted)' }}>
            All team members have active Copilot seats with no policy restrictions.
          </p>
        </Card>
      ) : (
        <Card>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '12px 16px 0',
            }}
          >
            <CardHeader>Adoption Blockers</CardHeader>
            <button
              onClick={handleExportBlockers}
              style={{
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                padding: '4px 12px',
                fontSize: 12,
                cursor: 'pointer',
                color: 'var(--fg)',
              }}
            >
              Export CSV
            </button>
          </div>
          <div style={{ padding: '0 16px 16px' }}>
            {blockers.map((blocker: CopilotBlocker) => (
              <div
                key={blocker.id}
                style={{
                  padding: '12px 0',
                  borderBottom: '1px solid var(--border)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span
                    style={{
                      display: 'inline-block',
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: SEVERITY_COLORS[blocker.severity] ?? 'var(--fg-muted)',
                    }}
                  />
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{blocker.title}</span>
                  <span
                    style={{
                      fontSize: 11,
                      color: 'var(--fg-muted)',
                      background: 'var(--bg-tertiary)',
                      padding: '1px 6px',
                      borderRadius: 4,
                    }}
                  >
                    {CATEGORY_LABELS[blocker.category] ?? blocker.category}
                  </span>
                </div>
                <p style={{ fontSize: 12, color: 'var(--fg-muted)', margin: '4px 0' }}>
                  {blocker.description}
                </p>
                <p style={{ fontSize: 12, color: 'var(--accent)' }}>💡 {blocker.recommendation}</p>
                {blocker.affected_users.length > 0 && (
                  <details style={{ marginTop: 4, fontSize: 12 }}>
                    <summary style={{ cursor: 'pointer', color: 'var(--fg-muted)' }}>
                      {blocker.count} affected user{blocker.count !== 1 ? 's' : ''}
                    </summary>
                    <div
                      style={{
                        marginTop: 4,
                        display: 'flex',
                        flexWrap: 'wrap',
                        gap: 4,
                      }}
                    >
                      {blocker.affected_users.map((user: string) => (
                        <span
                          key={user}
                          style={{
                            background: 'var(--bg-tertiary)',
                            padding: '1px 6px',
                            borderRadius: 4,
                            fontSize: 11,
                          }}
                        >
                          {user}
                        </span>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </>
  );
}
