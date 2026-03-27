import { useQuery } from '@tanstack/react-query';
import { getSeatUtilizationReport, getCopilotSeatsReport } from '../../api/reports';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import type { SeatUtilizationBucket, CopilotSeatsBucket } from '../../types/reports';
import styles from './Copilot.module.css';

const LANGUAGES = [
  { lang: 'TypeScript', pct: 38, color: '#3fb950' },
  { lang: 'Python', pct: 34, color: '#3fb950' },
  { lang: 'Go', pct: 29, color: '#26a641' },
  { lang: 'Java', pct: 21, color: '#d29922' },
  { lang: 'C++', pct: 14, color: '#f85149' },
];

export function CopilotPage() {
  const { isLoading: loadingSeatUtil, isError: seatUtilError, refetch: refetchSeatUtil, data: seatUtilData } = useQuery({
    queryKey: ['reports', 'seat-util'],
    queryFn: () => getSeatUtilizationReport({ window_days: 30 }),
  });

  const { data: copilotData, isLoading: loadingCopilot } = useQuery({
    queryKey: ['reports', 'copilot-seats'],
    queryFn: () => getCopilotSeatsReport({ window_days: 30 }),
  });

  const isLoading = loadingSeatUtil || loadingCopilot;
  const isError = seatUtilError;

  // Aggregate seat utilization
  const seatBuckets = (seatUtilData?.data ?? []) as unknown as SeatUtilizationBucket[];
  const latestSeatBucket = seatBuckets[seatBuckets.length - 1];
  const avgUtilPct = seatBuckets.length > 0
    ? (seatBuckets.reduce((s, b) => s + (b.utilization_pct ?? 0), 0) / seatBuckets.length).toFixed(1)
    : null;

  // Aggregate copilot seat changes
  const copilotBuckets = (copilotData?.data ?? []) as unknown as CopilotSeatsBucket[];
  const totalAssigned = copilotBuckets.reduce((s, b) => s + (b.seats_assigned ?? 0), 0);
  const totalRevoked = copilotBuckets.reduce((s, b) => s + (b.seats_revoked ?? 0), 0);
  const netSeats = copilotBuckets.reduce((s, b) => s + (b.seats_net ?? 0), 0);

  const activeSeats = latestSeatBucket?.active_seat_count;
  const provisionedSeats = latestSeatBucket?.provisioned_seat_count;

  const seatLabel = activeSeats != null && provisionedSeats != null
    ? `${activeSeats} / ${provisionedSeats}`
    : '—';

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Copilot Insights</div>
      <div className={styles.pageSub}>
        GitHub Copilot adoption, seat utilization, and correlation with delivery outcomes
      </div>

      <SampleDataBanner />

      {isError && <ErrorBanner message="Failed to load Copilot data" onRetry={refetchSeatUtil} />}
      {isLoading && <Spinner />}

      <div className={styles.metricStrip}>
        <MetricCard value={seatLabel} label="Active / total seats (latest)" delta={avgUtilPct != null ? `${avgUtilPct}% avg utilization` : '—'} deltaDir="neutral" />
        <MetricCard value={totalAssigned > 0 ? String(totalAssigned) : '—'} label="Seats assigned (30d)" delta="cumulative" deltaDir="up" />
        <MetricCard value={totalRevoked > 0 ? String(totalRevoked) : '—'} label="Seats revoked (30d)" delta="cumulative" deltaDir={totalRevoked > 0 ? 'down' : 'neutral'} />
        <MetricCard value={netSeats !== 0 ? `${netSeats > 0 ? '+' : ''}${netSeats}` : '—'} label="Net seat change (30d)" delta="assigned minus revoked" deltaDir={netSeats > 0 ? 'up' : netSeats < 0 ? 'down' : 'neutral'} />
      </div>

      {seatBuckets.length > 0 && (
        <>
          <div className={styles.sectionTitle}>Seat utilization — last 30 days</div>
          <Card style={{ marginBottom: 20 }}>
            <CardHeader>Active seats / provisioned seats over time</CardHeader>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Active seats</th>
                    <th>Provisioned</th>
                    <th>Utilization</th>
                  </tr>
                </thead>
                <tbody>
                  {seatBuckets.slice(-10).map((b, i) => (
                    <tr key={i}>
                      <td style={{ color: 'var(--fg-muted)' }}>{new Date(b.bucket).toLocaleDateString()}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>{b.active_seat_count ?? '—'}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>{b.provisioned_seat_count ?? '—'}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {b.utilization_pct != null
                          ? `${Math.round(b.utilization_pct)}%`
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      {seatBuckets.length === 0 && !isLoading && (
        <div style={{ color: 'var(--fg-muted)', padding: '16px 0' }}>No seat utilization data for the selected period.</div>
      )}

      <div className={styles.grid2}>
        <Card>
          <CardHeader>Acceptance rate by language</CardHeader>
          <div className={styles.langBars}>
            {LANGUAGES.map((l) => (
              <div key={l.lang} className={styles.langRow}>
                <span className={styles.langName}>{l.lang}</span>
                <div className={styles.langTrack}>
                  <div style={{ width: `${l.pct}%`, height: '100%', background: l.color, borderRadius: 4 }} />
                </div>
                <span className={styles.langPct}>{l.pct}%</span>
              </div>
            ))}
          </div>
          <div className={styles.langNote}>Language data from Copilot telemetry (not available via audit log)</div>
        </Card>
        <Card>
          <CardHeader>Seat change history (30d)</CardHeader>
          {copilotBuckets.length > 0 ? (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%' }}>
                <thead>
                  <tr><th>Date</th><th>Assigned</th><th>Revoked</th><th>Net</th></tr>
                </thead>
                <tbody>
                  {copilotBuckets.slice(-7).map((b, i) => (
                    <tr key={i}>
                      <td style={{ color: 'var(--fg-muted)' }}>{new Date(b.bucket).toLocaleDateString()}</td>
                      <td style={{ color: 'var(--success)', fontVariantNumeric: 'tabular-nums' }}>+{b.seats_assigned ?? 0}</td>
                      <td style={{ color: b.seats_revoked ? 'var(--danger)' : undefined, fontVariantNumeric: 'tabular-nums' }}>{b.seats_revoked > 0 ? `-${b.seats_revoked}` : '—'}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>{b.seats_net > 0 ? `+${b.seats_net}` : b.seats_net}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ color: 'var(--fg-muted)', padding: '12px 0' }}>No seat change data available.</div>
          )}
        </Card>
      </div>
    </div>
  );
}

