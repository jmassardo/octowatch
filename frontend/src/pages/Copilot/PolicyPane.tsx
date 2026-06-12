import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { getCopilotPolicyChanges } from '../../api/copilotMetrics';
import type { PolicyChange } from '../../api/copilotMetrics';
import { useOrg } from '../../hooks/useOrg';
import styles from './Copilot.module.css';

function formatTimestamp(ts: string): string {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return ts;
  }
}

export function PolicyPane() {
  const { selectedOrg } = useOrg();
  const orgParam = selectedOrg || undefined;
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['copilot', 'policy-changes', orgParam],
    queryFn: () => getCopilotPolicyChanges(orgParam),
    staleTime: 30 * 60 * 1000,
  });

  if (isLoading) return <Spinner />;
  if (isError)
    return <ErrorBanner message="Failed to load policy changes" onRetry={() => void refetch()} />;
  if (data?.error) return <ErrorBanner message={data.message ?? 'Policy data unavailable'} />;

  const timeline = data?.timeline ?? [];

  return (
    <>
      <div className={styles.metricStrip}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{data?.total_changes ?? 0}</div>
          <div className={styles.statLabel}>Total Policy Changes</div>
        </div>
      </div>

      {timeline.length === 0 ? (
        <Card>
          <CardHeader>No policy changes recorded</CardHeader>
          <p style={{ padding: '16px', color: 'var(--fg-muted)' }}>
            No Copilot-related audit events found. Policy changes will appear here as they are
            recorded in the audit log.
          </p>
        </Card>
      ) : (
        <Card>
          <CardHeader>Copilot Policy Change Timeline</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            {timeline.map((event: PolicyChange, idx: number) => (
              <div
                key={event.id}
                style={{
                  display: 'flex',
                  gap: 16,
                  padding: '12px 0',
                  borderBottom: idx < timeline.length - 1 ? '1px solid var(--border)' : undefined,
                }}
              >
                {/* Timeline dot and line */}
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    width: 20,
                    flexShrink: 0,
                  }}
                >
                  <div
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      background: 'var(--accent)',
                      marginTop: 4,
                    }}
                  />
                  {idx < timeline.length - 1 && (
                    <div
                      style={{
                        width: 2,
                        flex: 1,
                        background: 'var(--border)',
                        marginTop: 4,
                      }}
                    />
                  )}
                </div>

                {/* Event details */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{event.description}</span>
                    <span
                      style={{
                        fontSize: 11,
                        color: 'var(--fg-muted)',
                        background: 'var(--bg-tertiary)',
                        padding: '1px 6px',
                        borderRadius: 4,
                      }}
                    >
                      {event.action}
                    </span>
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      color: 'var(--fg-muted)',
                      marginTop: 4,
                      display: 'flex',
                      gap: 16,
                      flexWrap: 'wrap',
                    }}
                  >
                    <span>
                      by <strong>{event.actor}</strong>
                    </span>
                    <span>{formatTimestamp(event.timestamp)}</span>
                    {event.org && <span>org: {event.org}</span>}
                  </div>
                  {(event.old_value || event.new_value) && (
                    <div
                      style={{
                        marginTop: 8,
                        fontSize: 12,
                        display: 'flex',
                        gap: 8,
                        alignItems: 'center',
                      }}
                    >
                      {event.old_value && (
                        <span
                          style={{
                            background: 'rgba(var(--danger-rgb), 0.1)',
                            color: 'var(--danger)',
                            padding: '2px 6px',
                            borderRadius: 4,
                            textDecoration: 'line-through',
                          }}
                        >
                          {String(event.old_value)}
                        </span>
                      )}
                      {event.old_value && event.new_value && <span>→</span>}
                      {event.new_value && (
                        <span
                          style={{
                            background: 'rgba(var(--success-rgb), 0.1)',
                            color: 'var(--success)',
                            padding: '2px 6px',
                            borderRadius: 4,
                          }}
                        >
                          {String(event.new_value)}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </>
  );
}
