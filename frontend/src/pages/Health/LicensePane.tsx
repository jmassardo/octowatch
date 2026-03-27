import { useQuery } from '@tanstack/react-query';
import { Card } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { MetricCard } from '../../components/primitives/MetricCard';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { getSeatUtilizationReport, getCopilotSeatsReport } from '../../api/reports';
import type { SeatUtilizationBucket, CopilotSeatsBucket, ReportEnvelope } from '../../types/reports';
import {
  LICENSE_SAMPLE,
  COST_PER_SEAT_DEFAULT,
  GHOST_MEMBERS,
  COPILOT_CROSS_REF,
} from './healthData';
import styles from './LicensePane.module.css';

/** Extract typed buckets from the generic report envelope. */
function toSeatBuckets(env: ReportEnvelope | undefined): SeatUtilizationBucket[] {
  if (!env?.data) return [];
  return env.data as unknown as SeatUtilizationBucket[];
}

function toCopilotBuckets(env: ReportEnvelope | undefined): CopilotSeatsBucket[] {
  if (!env?.data) return [];
  return env.data as unknown as CopilotSeatsBucket[];
}

export function LicensePane() {
  const { data: seatEnv } = useQuery({
    queryKey: ['reports', 'seat-util-health'],
    queryFn: () => getSeatUtilizationReport({ window_days: 30 }),
    staleTime: 60_000,
  });

  const { data: copilotEnv } = useQuery({
    queryKey: ['reports', 'copilot-seats-health'],
    queryFn: () => getCopilotSeatsReport({ window_days: 30 }),
    staleTime: 60_000,
  });

  const seatBuckets = toSeatBuckets(seatEnv);
  const copilotBuckets = toCopilotBuckets(copilotEnv);

  // Use real data when available, fall back to sample data
  const latestSeat = seatBuckets[seatBuckets.length - 1];
  const hasRealSeatData = !!latestSeat;

  const totalSeats = latestSeat?.provisioned_seat_count ?? LICENSE_SAMPLE.totalSeats;
  const activeSeats = latestSeat?.active_seat_count ?? (LICENSE_SAMPLE.totalSeats - LICENSE_SAMPLE.ghostCount);
  const utilPct = latestSeat?.utilization_pct ?? LICENSE_SAMPLE.utilizationPct;
  const seatLimit = LICENSE_SAMPLE.seatLimit;
  const seatsRemaining = seatLimit - totalSeats;

  const ghostCount = hasRealSeatData ? totalSeats - activeSeats : LICENSE_SAMPLE.ghostCount;
  const ghostCost = ghostCount * COST_PER_SEAT_DEFAULT;

  // Copilot cross-reference
  const latestCopilot = copilotBuckets[copilotBuckets.length - 1];
  const copilotTotal = latestCopilot?.seats_net ?? COPILOT_CROSS_REF.totalSeats;
  const copilotInactive = COPILOT_CROSS_REF.inactiveSeats;

  return (
    <>
      <SampleDataBanner message="License seat data shown below uses sample values. Connect your GitHub audit log source and perform a baseline import to see real seat utilization." />

      {/* Summary metric cards */}
      <div className={styles.grid3}>
        <Card>
          <div className={styles.cardTitle} style={{ color: 'var(--fg-muted)' }}>
            Total seats (GitHub)
          </div>
          <div className={styles.cardValue}>
            {totalSeats}
            <span style={{ fontSize: 16, color: 'var(--fg-muted)' }}> / {seatLimit}</span>
          </div>
          <div className={styles.gaugeTrack}>
            <div
              className={styles.gaugeBar}
              style={{
                width: `${utilPct}%`,
                background: utilPct > 90 ? 'var(--danger)' : 'var(--attention)',
              }}
            />
          </div>
          <div className={styles.cardSub}>
            {utilPct}% utilized · <span style={{ color: 'var(--attention)' }}>{seatsRemaining} seats until limit</span>
          </div>
        </Card>

        <Card style={{ borderColor: 'rgba(248, 81, 73, 0.3)' }}>
          <div className={styles.cardTitle} style={{ color: 'var(--danger)' }}>
            Ghost members
          </div>
          <div className={styles.cardValue} style={{ color: 'var(--danger)' }}>
            {ghostCount}
          </div>
          <div className={styles.cardSub}>Dormant 90d+ still consuming a seat</div>
          <div className={styles.cardSub} style={{ color: 'var(--danger)', marginTop: 2 }}>
            ≈ ${ghostCost}/month recoverable
          </div>
        </Card>

        <Card>
          <div className={styles.cardTitle} style={{ color: 'var(--fg-muted)' }}>
            Growth forecast
          </div>
          <div className={styles.cardValue} style={{ color: 'var(--attention)' }}>
            ~{LICENSE_SAMPLE.growthForecastDays}d
          </div>
          <div className={styles.cardSub}>
            Until license limit at current +{LICENSE_SAMPLE.growthRate}/month rate
          </div>
          <div style={{ fontSize: 12, color: 'var(--fg-subtle)', marginTop: 2 }}>
            Based on <code className={styles.sourceCode}>org.add_member</code> event frequency
          </div>
        </Card>
      </div>

      {/* Ghost members table */}
      <div className={styles.sectionTitle}>Ghost members — consuming seats with no activity</div>
      <div className={styles.tableWrap} style={{ marginBottom: 20 }}>
        <table>
          <thead>
            <tr>
              <th>Member</th>
              <th>Org</th>
              <th>Role</th>
              <th>Last seen</th>
              <th>Days inactive</th>
              <th>Licenses held</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {GHOST_MEMBERS.map((m) => (
              <tr key={m.member}>
                <td style={{ fontWeight: 500 }}>{m.member}</td>
                <td style={{ color: 'var(--fg-muted)' }}>{m.org}</td>
                <td style={{ color: 'var(--fg-muted)' }}>{m.role}</td>
                <td style={{ color: 'var(--fg-muted)' }}>{m.lastSeen}</td>
                <td style={{ fontVariantNumeric: 'tabular-nums' }}>{m.daysInactive}</td>
                <td style={{ color: 'var(--fg-muted)' }}>{m.licensesHeld}</td>
                <td>
                  <Label variant="danger">{m.status}</Label>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Copilot seat cross-reference */}
      <div className={styles.sectionTitle}>Copilot seat waste for reference</div>
      <div className={styles.copilotCrossRef}>
        <strong style={{ color: 'var(--fg)' }}>
          {copilotInactive} of {copilotTotal} Copilot seats
        </strong>{' '}
        are inactive or never-used — see Copilot Insights → License Optimization for full detail.
      </div>

      <div className={styles.sourceNote}>
        ℹ️ License seat data is derived from{' '}
        <code className={styles.sourceCode}>org.add_member</code>,{' '}
        <code className={styles.sourceCode}>org.remove_member</code>, and the one-time baseline
        import for seat counts.
      </div>

      {/* Summary metrics row */}
      <div className={styles.metricStrip}>
        <MetricCard
          value={`${utilPct}%`}
          label="Seat utilization"
          delta={`${totalSeats} of ${seatLimit} seats`}
          deltaDir={utilPct > 90 ? 'down' : 'neutral'}
        />
        <MetricCard
          value={String(ghostCount)}
          label="Ghost members"
          delta={`$${ghostCost}/mo recoverable`}
          deltaDir="down"
          accent
        />
        <MetricCard
          value={`~${LICENSE_SAMPLE.growthForecastDays}d`}
          label="Days to limit"
          delta={`+${LICENSE_SAMPLE.growthRate}/mo growth`}
          deltaDir="down"
        />
        <MetricCard
          value={String(copilotInactive)}
          label="Copilot waste"
          delta={`of ${copilotTotal} seats`}
          deltaDir="down"
        />
      </div>
    </>
  );
}
