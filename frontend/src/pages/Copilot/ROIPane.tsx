import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { getCopilotROI } from '../../api/copilotMetrics';
import type { CopilotROISummary } from '../../api/copilotMetrics';
import styles from './Copilot.module.css';

function formatCurrency(value: number): string {
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

export function ROIPane() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['copilot', 'roi'],
    queryFn: getCopilotROI,
    staleTime: 30 * 60 * 1000,
  });

  if (isLoading) return <Spinner />;
  if (isError)
    return <ErrorBanner message="Failed to load ROI data" onRetry={() => void refetch()} />;
  if (data?.error) return <ErrorBanner message={data.message ?? 'ROI data unavailable'} />;

  const summary: CopilotROISummary | undefined = data?.summary;

  if (!summary) {
    return (
      <Card>
        <CardHeader>ROI Data Unavailable</CardHeader>
        <p style={{ padding: '16px', color: 'var(--fg-muted)' }}>
          ROI calculations require both seat data and metrics data. Ensure your organization has
          Copilot seat assignments configured.
        </p>
      </Card>
    );
  }

  const recommendations = data?.recommendations ?? [];
  const optimizationPotential =
    summary.total_monthly_cost > 0
      ? (summary.wasted_monthly / summary.total_monthly_cost) * 100
      : 0;

  return (
    <>
      {/* Cost summary strip */}
      <div className={styles.metricStrip}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{formatCurrency(summary.total_monthly_cost)}</div>
          <div className={styles.statLabel}>Monthly Cost</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{summary.total_seats}</div>
          <div className={styles.statLabel}>Total Seats</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue} style={{ color: 'var(--success)' }}>
            {summary.active_seats}
          </div>
          <div className={styles.statLabel}>Active Seats</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue} style={{ color: 'var(--danger)' }}>
            {summary.inactive_seats}
          </div>
          <div className={styles.statLabel}>Inactive Seats</div>
        </div>
      </div>

      {/* Cost analysis */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 16,
        }}
      >
        <Card>
          <CardHeader>Cost Efficiency</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
              <span style={{ fontSize: 13, color: 'var(--fg-muted)' }}>Monthly Cost</span>
              <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                {formatCurrency(summary.total_monthly_cost)}/mo
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
              <span style={{ fontSize: 13, color: 'var(--fg-muted)' }}>Cost per Active User</span>
              <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                {summary.active_seats > 0 ? formatCurrency(summary.cost_per_active_user) : '—'}
                /mo
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
              <span style={{ fontSize: 13, color: 'var(--fg-muted)' }}>Utilization Rate</span>
              <span
                style={{
                  fontWeight: 600,
                  color: summary.utilization_pct >= 70 ? 'var(--success)' : 'var(--warning)',
                }}
              >
                {formatPercent(summary.utilization_pct)}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 13, color: 'var(--fg-muted)' }}>Optimization Potential</span>
              <span
                style={{
                  fontWeight: 600,
                  color: optimizationPotential > 10 ? 'var(--danger)' : 'var(--success)',
                }}
              >
                {formatPercent(optimizationPotential)}
              </span>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader>Savings Opportunity</CardHeader>
          <div style={{ padding: '0 16px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 36, fontWeight: 700, color: 'var(--danger)', marginBottom: 4 }}>
              {formatCurrency(summary.wasted_monthly)}
            </div>
            <div style={{ fontSize: 13, color: 'var(--fg-muted)', marginBottom: 16 }}>
              Monthly wasted spend on inactive seats
            </div>
            <div
              style={{
                fontSize: 24,
                fontWeight: 700,
                color: 'var(--success)',
                marginBottom: 4,
              }}
            >
              {formatCurrency(summary.annual_waste)}
            </div>
            <div style={{ fontSize: 13, color: 'var(--fg-muted)' }}>Annual savings potential</div>
          </div>
        </Card>
      </div>

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <Card>
          <CardHeader>Recommendations</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            {recommendations.map((rec, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  gap: 12,
                  padding: '10px 0',
                  borderBottom:
                    idx < recommendations.length - 1 ? '1px solid var(--border)' : undefined,
                }}
              >
                <span style={{ fontSize: 16, flexShrink: 0 }}>💡</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{rec.title}</div>
                  <div style={{ fontSize: 12, color: 'var(--fg-muted)', marginTop: 2 }}>
                    {rec.description}
                  </div>
                  <div style={{ fontSize: 11, marginTop: 4, display: 'flex', gap: 8 }}>
                    <span
                      style={{
                        background:
                          rec.priority === 'high'
                            ? 'rgba(248, 81, 73, 0.15)'
                            : rec.priority === 'medium'
                              ? 'rgba(210, 153, 34, 0.15)'
                              : 'rgba(110, 118, 129, 0.15)',
                        color:
                          rec.priority === 'high'
                            ? 'var(--danger)'
                            : rec.priority === 'medium'
                              ? 'var(--warning)'
                              : 'var(--fg-muted)',
                        padding: '1px 6px',
                        borderRadius: 4,
                        fontWeight: 600,
                      }}
                    >
                      {rec.priority}
                    </span>
                    <span style={{ color: 'var(--success)' }}>{rec.impact}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </>
  );
}
