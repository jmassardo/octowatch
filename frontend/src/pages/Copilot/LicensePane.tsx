import { useRef, useState } from 'react';
import { Card, CardHeader } from '../../components/primitives/Card';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Modal } from '../../components/primitives/Modal';
import type { SeatUtilizationBucket } from '../../types/reports';
import { COST_PER_SEAT } from './copilotData';
import styles from './Copilot.module.css';

type LicenseDrillDown = 'total' | 'active' | 'inactive' | 'waste' | null;

interface LicensePaneProps {
  seatBuckets: SeatUtilizationBucket[];
}

export function LicensePane({ seatBuckets }: LicensePaneProps) {
  const [drillDown, setDrillDown] = useState<LicenseDrillDown>(null);
  const costSectionRef = useRef<HTMLDivElement>(null);

  // Derive seat metrics from real API data
  const latestBucket = seatBuckets[seatBuckets.length - 1];
  const totalSeats = latestBucket?.provisioned_seat_count ?? 0;
  const activeSeats = latestBucket?.active_seat_count ?? 0;
  const inactiveSeats = totalSeats - activeSeats;
  const monthlyWaste = inactiveSeats * COST_PER_SEAT;
  const annualSavings = monthlyWaste * 12;

  function drillDownTitle(): string {
    switch (drillDown) {
      case 'total':
        return 'Total seats — provisioned over time';
      case 'active':
        return 'Active seats — utilization over time';
      case 'inactive':
        return 'Inactive seats — over time';
      case 'waste':
        return 'Monthly waste — over time';
      default:
        return '';
    }
  }

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
          onClick={() => setDrillDown('total')}
        />
        <MetricCard
          value={activeSeats > 0 ? String(activeSeats) : '—'}
          label="Active seats"
          delta={totalSeats > 0 ? `${Math.round((activeSeats / totalSeats) * 100)}% utilization` : '—'}
          deltaDir="neutral"
          onClick={() => setDrillDown('active')}
        />
        <MetricCard
          value={inactiveSeats > 0 ? String(inactiveSeats) : '—'}
          label="Inactive seats"
          delta="provisioned but not active in 30d"
          deltaDir={inactiveSeats > 0 ? 'down' : 'neutral'}
          onClick={() => setDrillDown('inactive')}
        />
        <MetricCard
          value={monthlyWaste > 0 ? `$${monthlyWaste.toLocaleString()}` : '—'}
          label="Monthly waste"
          delta={annualSavings > 0 ? `$${annualSavings.toLocaleString()}/year potential savings` : '—'}
          deltaDir={monthlyWaste > 0 ? 'down' : 'neutral'}
          accent
          onClick={() => {
            if (costSectionRef.current) {
              costSectionRef.current.scrollIntoView({ behavior: 'smooth' });
            }
          }}
        />
      </div>

      {/* Drill-down modal */}
      <Modal open={drillDown !== null} onClose={() => setDrillDown(null)} title={drillDownTitle()} width={600}>
        {(drillDown === 'total' || drillDown === 'active' || drillDown === 'inactive' || drillDown === 'waste') && (
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  {drillDown === 'total' && <th>Provisioned</th>}
                  {drillDown === 'active' && <><th>Active</th><th>Utilization %</th></>}
                  {drillDown === 'inactive' && <><th>Inactive</th><th>Provisioned</th></>}
                  {drillDown === 'waste' && <><th>Inactive</th><th>Monthly cost</th></>}
                </tr>
              </thead>
              <tbody>
                {seatBuckets.map((b, i) => {
                  const bucketInactive = b.provisioned_seat_count - b.active_seat_count;
                  return (
                    <tr key={i}>
                      <td style={{ color: 'var(--fg-muted)' }}>{new Date(b.bucket).toLocaleDateString()}</td>
                      {drillDown === 'total' && (
                        <td style={{ fontVariantNumeric: 'tabular-nums' }}>{b.provisioned_seat_count ?? '—'}</td>
                      )}
                      {drillDown === 'active' && (
                        <>
                          <td style={{ fontVariantNumeric: 'tabular-nums' }}>{b.active_seat_count ?? '—'}</td>
                          <td style={{ fontVariantNumeric: 'tabular-nums' }}>{b.utilization_pct != null ? `${Math.round(b.utilization_pct)}%` : '—'}</td>
                        </>
                      )}
                      {drillDown === 'inactive' && (
                        <>
                          <td style={{ fontVariantNumeric: 'tabular-nums' }}>{bucketInactive}</td>
                          <td style={{ fontVariantNumeric: 'tabular-nums' }}>{b.provisioned_seat_count ?? '—'}</td>
                        </>
                      )}
                      {drillDown === 'waste' && (
                        <>
                          <td style={{ fontVariantNumeric: 'tabular-nums' }}>{bucketInactive}</td>
                          <td style={{ fontVariantNumeric: 'tabular-nums' }}>${(bucketInactive * COST_PER_SEAT).toLocaleString()}</td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Modal>

      {/* Cost breakdown */}
      <div ref={costSectionRef}>
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
      </div>

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
