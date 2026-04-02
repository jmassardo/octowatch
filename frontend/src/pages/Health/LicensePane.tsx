import { useQuery } from '@tanstack/react-query';
import { Card } from '../../components/primitives/Card';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { getSeatUtilizationReport, getCopilotSeatsReport } from '../../api/reports';
import { getGhostMembers, getLicenseConsumption } from '../../api/healthSignals';
import type {
  SeatUtilizationBucket,
  CopilotSeatsBucket,
  ReportEnvelope,
} from '../../types/reports';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { useOrgConfig } from '../../hooks/useOrgConfig';
import { formatDateOnly } from '../../utils/dates';
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
  const { costPerSeat } = useOrgConfig();

  const { data: licenseData } = useQuery({
    queryKey: ['health', 'license-consumption'],
    queryFn: () => getLicenseConsumption(),
    staleTime: 60_000,
  });

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

  // Prefer GHEC license consumption data from enterprise sync; fall back to
  // the report-based seat utilization buckets when license sync data is
  // unavailable.
  const hasLicenseSync = (licenseData?.total_seats_purchased ?? 0) > 0;
  const latestSeat = seatBuckets[seatBuckets.length - 1];

  const totalSeats = hasLicenseSync
    ? licenseData!.total_seats_consumed
    : (latestSeat?.provisioned_seat_count ?? 0);
  const seatLimit = hasLicenseSync
    ? licenseData!.total_seats_purchased
    : Math.max(latestSeat?.provisioned_seat_count ?? 0, 1);
  const activeSeats = hasLicenseSync
    ? licenseData!.total_seats_consumed
    : (latestSeat?.active_seat_count ?? 0);
  const utilPct = hasLicenseSync
    ? licenseData!.utilization_pct
    : (latestSeat?.utilization_pct ?? 0);
  const seatsRemaining = Math.max(0, seatLimit - totalSeats);

  const ghostMembers = ghostData?.ghost_members ?? [];
  const ghostCount = ghostMembers.length;
  const ghostCost = ghostCount * costPerSeat;

  // Copilot cross-reference
  const latestCopilot = copilotBuckets[copilotBuckets.length - 1];
  const copilotTotal = latestCopilot?.seats_net ?? 0;

  // Show sample-data banner when all API queries returned no real data
  // (not during loading or error — only when fallback zeros are displayed)
  const isSampleData =
    !isLoadingGhosts &&
    !isGhostError &&
    !hasLicenseSync &&
    seatBuckets.length === 0 &&
    copilotBuckets.length === 0 &&
    ghostMembers.length === 0;

  return (
    <>
      {isSampleData && (
        <SampleDataBanner message="This data is illustrative. Connect your GitHub organization to see real license metrics." />
      )}
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
            {utilPct}% utilized ·{' '}
            <span style={{ color: 'var(--attention)' }}>{seatsRemaining} seats until limit</span>
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
          <div className={styles.cardSub}>Members with recent activity</div>
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
                  <td
                    colSpan={2}
                    style={{ textAlign: 'center', color: 'var(--fg-muted)', padding: 24 }}
                  >
                    No ghost members detected
                  </td>
                </tr>
              )}
              {ghostMembers.map((m) => (
                <tr key={m.actor}>
                  <td style={{ fontWeight: 500 }}>{m.actor}</td>
                  <td style={{ color: 'var(--fg-muted)' }}>
                    {m.last_active ? formatDateOnly(m.last_active) : 'Never'}
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
        <strong style={{ color: 'var(--fg)' }}>{copilotTotal} Copilot seats</strong> provisioned —
        see Copilot Insights → License Optimization for full detail.
      </div>

      <div className={styles.sourceNote}>
        ℹ️ License seat data is derived from{' '}
        {hasLicenseSync ? (
          <>
            the GHEC <code className={styles.sourceCode}>consumed-licenses</code> API
            {licenseData?.synced_at && <> (last synced: {formatDateOnly(licenseData.synced_at)})</>}
            .
          </>
        ) : (
          <>
            <code className={styles.sourceCode}>org.add_member</code>,{' '}
            <code className={styles.sourceCode}>org.remove_member</code>, and the one-time baseline
            import for seat counts.
          </>
        )}
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
