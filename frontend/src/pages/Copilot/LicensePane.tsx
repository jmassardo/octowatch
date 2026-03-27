import { Card, CardHeader } from '../../components/primitives/Card';
import { MetricCard } from '../../components/primitives/MetricCard';
import type { SeatUtilizationBucket } from '../../types/reports';
import { COST_PER_SEAT } from './copilotData';
import styles from './Copilot.module.css';

interface LicensePaneProps {
  seatBuckets: SeatUtilizationBucket[];
}

export function LicensePane({ seatBuckets }: LicensePaneProps) {
  // Derive seat metrics from real API data
  const latestBucket = seatBuckets[seatBuckets.length - 1];
  const totalSeats = latestBucket?.provisioned_seat_count ?? 0;
  const activeSeats = latestBucket?.active_seat_count ?? 0;
  const inactiveSeats = totalSeats - activeSeats;
  const monthlyWaste = inactiveSeats * COST_PER_SEAT;
  const annualSavings = monthlyWaste * 12;

  // Generate recommendations dynamically based on real data
  const recommendations: { icon: string; title: string; description: string }[] = [];
  if (inactiveSeats > 0) {
    recommendations.push({
      icon: '🔴',
      title: `Revoke ${inactiveSeats} inactive seats to save $${(inactiveSeats * COST_PER_SEAT).toLocaleString()}/month`,
      description: 'These seats have shown no activity in the last 30 days.',
    });
  }
  recommendations.push({
    icon: '🟢',
    title: 'Consider just-in-time provisioning',
    description: 'Auto-assign seats on first IDE open, auto-revoke after 30d of inactivity.',
  });
  return (
    <>
      {/* Summary metrics */}
      <div className={styles.metricStrip}>
        <MetricCard
          value={totalSeats > 0 ? String(totalSeats) : '—'}
          label="Total seats"
          delta="provisioned"
          deltaDir="neutral"
        />
        <MetricCard
          value={activeSeats > 0 ? String(activeSeats) : '—'}
          label="Active seats"
          delta={totalSeats > 0 ? `${Math.round((activeSeats / totalSeats) * 100)}% utilization` : '—'}
          deltaDir="neutral"
        />
        <MetricCard
          value={inactiveSeats > 0 ? String(inactiveSeats) : '—'}
          label="Inactive seats"
          delta="provisioned but not active in 30d"
          deltaDir={inactiveSeats > 0 ? 'down' : 'neutral'}
        />
        <MetricCard
          value={monthlyWaste > 0 ? `$${monthlyWaste.toLocaleString()}` : '—'}
          label="Monthly waste"
          delta={annualSavings > 0 ? `$${annualSavings.toLocaleString()}/year potential savings` : '—'}
          deltaDir={monthlyWaste > 0 ? 'down' : 'neutral'}
          accent
        />
      </div>

      {/* Cost breakdown */}
      <Card style={{ marginBottom: 20 }}>
        <CardHeader>Cost optimization summary</CardHeader>
        <div className={styles.costSummary}>
          <div className={styles.costRow}>
            <span className={styles.costLabel}>Current monthly spend</span>
            <span className={styles.costValue}>
              ${(totalSeats * COST_PER_SEAT).toLocaleString()}
            </span>
          </div>
          <div className={styles.costRow}>
            <span className={styles.costLabel}>Optimized monthly spend</span>
            <span className={styles.costValue} style={{ color: 'var(--success)' }}>
              ${(activeSeats * COST_PER_SEAT).toLocaleString()}
            </span>
          </div>
          <div className={[styles.costRow, styles.costRowHighlight].join(' ')}>
            <span className={styles.costLabel}>Potential monthly savings</span>
            <span className={styles.costValue} style={{ color: 'var(--success)', fontWeight: 600 }}>
              ${monthlyWaste.toLocaleString()}
            </span>
          </div>
        </div>
      </Card>

      {/* Recommendations */}
      <div className={styles.sectionTitle}>Recommendations</div>
      <div className={styles.recList}>
        {recommendations.map((rec) => (
          <div key={rec.title} className={styles.recItem}>
            <span className={styles.recIcon}>{rec.icon}</span>
            <div className={styles.recContent}>
              <div className={styles.recTitle}>{rec.title}</div>
              <div className={styles.recDesc}>{rec.description}</div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
