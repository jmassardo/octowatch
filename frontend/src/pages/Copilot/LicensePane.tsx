import { Card, CardHeader } from '../../components/primitives/Card';
import { MetricCard } from '../../components/primitives/MetricCard';
import {
  TOTAL_SEATS,
  ACTIVE_SEATS,
  WASTED_SEATS,
  MONTHLY_WASTE,
  INACTIVE_SEATS,
  NEVER_USED_SEATS,
  COST_PER_SEAT,
} from './copilotData';
import styles from './Copilot.module.css';

const ANNUAL_SAVINGS = MONTHLY_WASTE * 12;

const RECOMMENDATIONS = [
  {
    icon: '🔴',
    title: `Revoke ${NEVER_USED_SEATS} never-used seats`,
    description: `Save $${(NEVER_USED_SEATS * COST_PER_SEAT).toLocaleString()}/month — these seats have never generated a single suggestion.`,
  },
  {
    icon: '🟡',
    title: `Review ${INACTIVE_SEATS} inactive seats`,
    description: 'Send reactivation campaign or revoke after 14-day grace period.',
  },
  {
    icon: '🟢',
    title: 'Enable just-in-time provisioning',
    description: 'Auto-assign seats on first IDE open, auto-revoke after 30d of inactivity.',
  },
  {
    icon: '🔵',
    title: 'Consolidate model usage',
    description: 'Route low-complexity completions to GPT-4o-mini to reduce per-seat cost overhead.',
  },
];

export function LicensePane() {
  return (
    <>
      {/* Summary metrics */}
      <div className={styles.metricStrip}>
        <MetricCard
          value={String(TOTAL_SEATS)}
          label="Total seats"
          delta="provisioned"
          deltaDir="neutral"
        />
        <MetricCard
          value={String(ACTIVE_SEATS)}
          label="Active seats"
          delta={`${Math.round((ACTIVE_SEATS / TOTAL_SEATS) * 100)}% utilization`}
          deltaDir="neutral"
        />
        <MetricCard
          value={String(WASTED_SEATS)}
          label="Unused seats"
          delta={`${INACTIVE_SEATS} inactive + ${NEVER_USED_SEATS} never used`}
          deltaDir="down"
        />
        <MetricCard
          value={`$${MONTHLY_WASTE.toLocaleString()}`}
          label="Monthly waste"
          delta={`$${ANNUAL_SAVINGS.toLocaleString()}/year potential savings`}
          deltaDir="down"
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
              ${(TOTAL_SEATS * COST_PER_SEAT).toLocaleString()}
            </span>
          </div>
          <div className={styles.costRow}>
            <span className={styles.costLabel}>Optimized monthly spend</span>
            <span className={styles.costValue} style={{ color: 'var(--success)' }}>
              ${((TOTAL_SEATS - WASTED_SEATS) * COST_PER_SEAT).toLocaleString()}
            </span>
          </div>
          <div className={[styles.costRow, styles.costRowHighlight].join(' ')}>
            <span className={styles.costLabel}>Potential monthly savings</span>
            <span className={styles.costValue} style={{ color: 'var(--success)', fontWeight: 600 }}>
              ${MONTHLY_WASTE.toLocaleString()}
            </span>
          </div>
        </div>
      </Card>

      {/* Recommendations */}
      <div className={styles.sectionTitle}>Recommendations</div>
      <div className={styles.recList}>
        {RECOMMENDATIONS.map((rec) => (
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
