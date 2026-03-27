import { Card, CardHeader } from '../../components/primitives/Card';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { Button } from '../../components/primitives/Button';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import type { SeatUtilizationBucket, CopilotSeatsBucket } from '../../types/reports';
import {
  LANGUAGES,
  ACCEPTANCE_RATE_DAYS,
  ACCEPTANCE_RATE_VALUES,
  ACCEPTANCE_THRESHOLD_LINE,
  SEAT_TREND_DAYS,
  SEAT_TREND_ACTIVE,
  SEAT_TREND_INACTIVE,
  SEAT_TREND_NEVER,
  WASTED_SEATS,
  MONTHLY_WASTE,
  INACTIVE_SEATS,
  NEVER_USED_SEATS,
  COST_PER_SEAT,
} from './copilotData';
import styles from './Copilot.module.css';

interface OverviewPaneProps {
  seatBuckets: SeatUtilizationBucket[];
  copilotBuckets: CopilotSeatsBucket[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

export function OverviewPane({
  seatBuckets,
  copilotBuckets,
  isLoading,
  isError,
  onRetry,
}: OverviewPaneProps) {
  const latestSeatBucket = seatBuckets[seatBuckets.length - 1];
  const avgUtilPct =
    seatBuckets.length > 0
      ? (seatBuckets.reduce((s, b) => s + (b.utilization_pct ?? 0), 0) / seatBuckets.length).toFixed(1)
      : null;

  const totalAssigned = copilotBuckets.reduce((s, b) => s + (b.seats_assigned ?? 0), 0);
  const totalRevoked = copilotBuckets.reduce((s, b) => s + (b.seats_revoked ?? 0), 0);
  const netSeats = copilotBuckets.reduce((s, b) => s + (b.seats_net ?? 0), 0);

  const activeSeats = latestSeatBucket?.active_seat_count;
  const provisionedSeats = latestSeatBucket?.provisioned_seat_count;
  const seatLabel =
    activeSeats != null && provisionedSeats != null ? `${activeSeats} / ${provisionedSeats}` : '—';

  return (
    <>
      <SampleDataBanner />

      {/* Seat waste alert banner */}
      <div className={styles.wasteAlert}>
        <span style={{ fontSize: 18, lineHeight: 1 }}>⚠️</span>
        <div className={styles.wasteBody}>
          <div className={styles.wasteTitle}>
            Seat waste detected — ${MONTHLY_WASTE.toLocaleString()}/month in unused licenses
          </div>
          <div className={styles.wasteDesc}>
            {WASTED_SEATS} seats unused ({INACTIVE_SEATS} inactive 30d+ and {NEVER_USED_SEATS} never
            used) at ${COST_PER_SEAT}/seat/month
          </div>
        </div>
        <Button size="sm" variant="danger">
          Export inactive list
        </Button>
      </div>

      {isError && <ErrorBanner message="Failed to load Copilot data" onRetry={onRetry} />}
      {isLoading && <Spinner />}

      {/* Metric strip */}
      <div className={styles.metricStrip}>
        <MetricCard
          value={seatLabel}
          label="Active / total seats (latest)"
          delta={avgUtilPct != null ? `${avgUtilPct}% avg utilization` : '—'}
          deltaDir="neutral"
        />
        <MetricCard
          value={totalAssigned > 0 ? String(totalAssigned) : '—'}
          label="Seats assigned (30d)"
          delta="cumulative"
          deltaDir="up"
        />
        <MetricCard
          value={totalRevoked > 0 ? String(totalRevoked) : '—'}
          label="Seats revoked (30d)"
          delta="cumulative"
          deltaDir={totalRevoked > 0 ? 'down' : 'neutral'}
        />
        <MetricCard
          value={netSeats !== 0 ? `${netSeats > 0 ? '+' : ''}${netSeats}` : '—'}
          label="Net seat change (30d)"
          delta="assigned minus revoked"
          deltaDir={netSeats > 0 ? 'up' : netSeats < 0 ? 'down' : 'neutral'}
        />
      </div>

      {/* Charts row */}
      <div className={styles.grid2}>
        <Card>
          <CardHeader>Acceptance rate — 7-day rolling average</CardHeader>
          <LineAreaChart
            xAxisData={ACCEPTANCE_RATE_DAYS}
            series={[
              {
                name: 'Acceptance rate',
                data: ACCEPTANCE_RATE_VALUES,
                color: '#bc8cff',
                areaOpacity: 0.15,
              },
              {
                name: '25% good threshold',
                data: ACCEPTANCE_THRESHOLD_LINE,
                color: '#3fb950',
                dashed: true,
              },
            ]}
            yAxisFormatter={(v: number) => `${v}%`}
            height={200}
          />
        </Card>
        <Card>
          <CardHeader>Seat utilization trend</CardHeader>
          <LineAreaChart
            xAxisData={SEAT_TREND_DAYS}
            series={[
              { name: 'Active', data: SEAT_TREND_ACTIVE, color: '#58a6ff', areaOpacity: 0.1 },
              { name: 'Inactive 30d', data: SEAT_TREND_INACTIVE, color: '#d29922' },
              { name: 'Never used', data: SEAT_TREND_NEVER, color: '#f85149' },
            ]}
            height={200}
          />
        </Card>
      </div>

      {/* Seat utilization table */}
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
                      <td style={{ color: 'var(--fg-muted)' }}>
                        {new Date(b.bucket).toLocaleDateString()}
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {b.active_seat_count ?? '—'}
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {b.provisioned_seat_count ?? '—'}
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {b.utilization_pct != null ? `${Math.round(b.utilization_pct)}%` : '—'}
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
        <div style={{ color: 'var(--fg-muted)', padding: '16px 0' }}>
          No seat utilization data for the selected period.
        </div>
      )}

      {/* Bottom grid: language bars + seat change history */}
      <div className={styles.grid2}>
        <Card>
          <CardHeader>Acceptance rate by language</CardHeader>
          <div className={styles.langBars}>
            {LANGUAGES.map((l) => (
              <div key={l.lang} className={styles.langRow}>
                <span className={styles.langName}>{l.lang}</span>
                <div className={styles.langTrack}>
                  <div
                    style={{
                      width: `${l.pct}%`,
                      height: '100%',
                      background: l.color,
                      borderRadius: 4,
                    }}
                  />
                </div>
                <span className={styles.langPct}>{l.pct}%</span>
              </div>
            ))}
          </div>
          <div className={styles.langNote}>
            Language data from Copilot telemetry (not available via audit log)
          </div>
        </Card>
        <Card>
          <CardHeader>Seat change history (30d)</CardHeader>
          {copilotBuckets.length > 0 ? (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Assigned</th>
                    <th>Revoked</th>
                    <th>Net</th>
                  </tr>
                </thead>
                <tbody>
                  {copilotBuckets.slice(-7).map((b, i) => (
                    <tr key={i}>
                      <td style={{ color: 'var(--fg-muted)' }}>
                        {new Date(b.bucket).toLocaleDateString()}
                      </td>
                      <td
                        style={{
                          color: 'var(--success)',
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        +{b.seats_assigned ?? 0}
                      </td>
                      <td
                        style={{
                          color: b.seats_revoked ? 'var(--danger)' : undefined,
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        {b.seats_revoked > 0 ? `-${b.seats_revoked}` : '—'}
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {b.seats_net > 0 ? `+${b.seats_net}` : b.seats_net}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ color: 'var(--fg-muted)', padding: '12px 0' }}>
              No seat change data available.
            </div>
          )}
        </Card>
      </div>

      {/* Correlation insights */}
      <Card style={{ marginBottom: 20 }}>
        <CardHeader>Correlation insights</CardHeader>
        <div className={styles.insightNote}>
          Cross-referencing Copilot usage with delivery metrics
        </div>
        <div className={styles.insights}>
          <div className={styles.insightSuccess}>
            <span>✅</span>
            <div>
              <div className={styles.insightTitle}>
                Acceptance rate ↑ correlates with cycle time ↓
              </div>
              <div className={styles.insightBody}>
                Teams with &gt;30% acceptance rate show 23% shorter cycle times on average compared
                to teams below 20% acceptance.
              </div>
            </div>
          </div>
          <div className={styles.insightWarn}>
            <span>⚠️</span>
            <div>
              <div className={styles.insightTitle}>Active seats ≠ effective usage</div>
              <div className={styles.insightBody}>
                38 seats show activity but acceptance rate is below 10% — suggesting Copilot is
                active but suggestions are being dismissed. Consider targeted training.
              </div>
            </div>
          </div>
        </div>
      </Card>
    </>
  );
}
