import { useQuery } from '@tanstack/react-query';
import { Card } from '../../components/primitives/Card';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { getSeatUtilizationReport, getCopilotSeatsReport } from '../../api/reports';
import { getGhostMembers } from '../../api/healthSignals';
import type { SeatUtilizationBucket, CopilotSeatsBucket, ReportEnvelope } from '../../types/reports';
import {
  COST_PER_SEAT_DEFAULT,
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

  const {
    data: ghostData,
    isLoading: isLoadingGhosts,
    isError: isGhostError,
    refetch: refetchGhosts,
  } = useQuery({
    queryKey: ['health', 'ghost-members'],
    queryFn: () => getGhostMembers(),
    staleTime: 60_000,
  });

  const seatBuckets = toSeatBuckets(seatEnv);
  const copilotBuckets = toCopilotBuckets(copilotEnv);

  // Use real data when available
  const latestSeat = seatBuckets[seatBuckets.length - 1];

  const totalSeats = latestSeat?.provisioned_seat_count ?? 0;
  const activeSeats = latestSeat?.active_seat_count ?? 0;
  const utilPct = latestSeat?.utilization_pct ?? 0;
  const seatLimit = Math.max(totalSeats, 1);
  const seatsRemaining = Math.max(0, seatLimit - totalSeats);

  const ghostMembers = ghostData?.ghost_members ?? [];
  const ghostCount = ghostMembers.length;
  const ghostCost = ghostCount * COST_PER_SEAT_DEFAULT;

  // Copilot cross-reference
  const latestCopilot = copilotBuckets[copilotBuckets.length - 1];
  const copilotTotal = latestCopilot?.seats_net ?? 0;

  return (
    <>
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
            Active seats
          </div>
          <div className={styles.cardValue} style={{ color: 'var(--attention)' }}>
            {activeSeats}
          </div>
          <div className={styles.cardSub}>
            Members with recent activity
          </div>
          <div style={{ fontSize: 12, color: 'var(--fg-subtle)', marginTop: 2 }}>
            Based on <code className={styles.sourceCode}>org.add_member</code> event frequency
          </div>
        </Card>
      </div>

      {/* Ghost members table */}
      <div className={styles.sectionTitle}>Ghost members — consuming seats with no activity</div>
      {isLoadingGhosts && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}>
          <Spinner size={24} />
        </div>
      )}
      {isGhostError && (
        <ErrorBanner message="Failed to load ghost members" onRetry={() => void refetchGhosts()} />
      )}
      {!isLoadingGhosts && !isGhostError && (
        <div className={styles.tableWrap} style={{ marginBottom: 20 }}>
          <table>
            <thead>
              <tr>
                <th>Member</th>
                <th>Last active</th>
              </tr>
            </thead>
            <tbody>
              {ghostMembers.length === 0 && (
                <tr>
                  <td colSpan={2} style={{ textAlign: 'center', color: 'var(--fg-muted)', padding: 24 }}>
                    No ghost members detected
                  </td>
                </tr>
              )}
              {ghostMembers.map((m) => (
                <tr key={m.actor}>
                  <td style={{ fontWeight: 500 }}>{m.actor}</td>
                  <td style={{ color: 'var(--fg-muted)' }}>
                    {m.last_active
                      ? new Date(m.last_active).toLocaleDateString('en-US', {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                        })
                      : 'Never'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Copilot seat cross-reference */}
      <div className={styles.sectionTitle}>Copilot seat cross-reference</div>
      <div className={styles.copilotCrossRef}>
        <strong style={{ color: 'var(--fg)' }}>
          {copilotTotal} Copilot seats
        </strong>{' '}
        provisioned — see Copilot Insights → License Optimization for full detail.
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
          value={String(activeSeats)}
          label="Active seats"
          delta="with recent activity"
          deltaDir="neutral"
        />
        <MetricCard
          value={String(copilotTotal)}
          label="Copilot seats"
          delta="provisioned"
          deltaDir="neutral"
        />
      </div>
    </>
  );
}
