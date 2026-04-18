import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Modal } from '../../components/primitives/Modal';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { Button } from '../../components/primitives/Button';
import { DataTable } from '../../components/primitives/DataTable';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import type { SeatUtilizationBucket, CopilotSeatsBucket } from '../../types/reports';
import { getCopilotOverview } from '../../api/copilotMetrics';
import { useOrgConfig } from '../../hooks/useOrgConfig';
import { formatBucketDate, formatWeekday } from '../../utils/dates';
import styles from './Copilot.module.css';
type DrillDownType = 'active-seats' | 'assigned' | 'revoked' | 'net' | null;
type OverviewModal = 'seat-waste' | 'correlation-seats' | 'correlation-cycle' | 'language' | null;

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
  const { costPerSeat } = useOrgConfig();
  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['copilot', 'overview'],
    queryFn: getCopilotOverview,
    staleTime: 30 * 60 * 1000,
  });

  const languages = overview?.languages ?? [];
  const acceptanceRateDays = overview?.acceptance_rate_days ?? [];
  const acceptanceRateValues = overview?.acceptance_rate_values ?? [];
  const acceptanceThresholdLine = Array.from(
    { length: acceptanceRateDays.length },
    () => overview?.acceptance_threshold ?? 25,
  );

  const [drillDown, setDrillDown] = useState<DrillDownType>(null);
  const [overviewModal, setOverviewModal] = useState<OverviewModal>(null);
  const [selectedLang, setSelectedLang] = useState<string | null>(null);
  const seatTableRef = useRef<HTMLDivElement>(null);

  const latestSeatBucket = seatBuckets[seatBuckets.length - 1];
  const avgUtilPct =
    seatBuckets.length > 0
      ? (
          seatBuckets.reduce((s, b) => s + (b.utilization_pct ?? 0), 0) / seatBuckets.length
        ).toFixed(1)
      : null;

  const totalAssigned = copilotBuckets.reduce((s, b) => s + (b.seats_assigned ?? 0), 0);
  const totalRevoked = copilotBuckets.reduce((s, b) => s + (b.seats_revoked ?? 0), 0);
  const netSeats = copilotBuckets.reduce((s, b) => s + (b.seats_net ?? 0), 0);

  const activeSeats = latestSeatBucket?.active_seat_count;
  const provisionedSeats = latestSeatBucket?.provisioned_seat_count;
  const seatLabel =
    activeSeats != null && provisionedSeats != null ? `${activeSeats} / ${provisionedSeats}` : '—';

  // Derive waste metrics from real API data
  const inactiveSeats = (provisionedSeats ?? 0) - (activeSeats ?? 0);
  const monthlyWaste = inactiveSeats * costPerSeat;

  function handleActiveSeatsClick() {
    if (seatTableRef.current) {
      seatTableRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }

  function drillDownTitle(): string {
    switch (drillDown) {
      case 'active-seats':
        return 'Active / total seats — all data';
      case 'assigned':
        return 'Seats assigned — 30-day history';
      case 'revoked':
        return 'Seats revoked — 30-day history';
      case 'net':
        return 'Net seat change — 30-day history';
      default:
        return '';
    }
  }

  function handleExportInactive() {
    const rows = [
      'Category,Seats,Cost Per Seat ($/mo),Monthly Cost ($)',
      `Inactive (provisioned - active),${inactiveSeats},${costPerSeat},${monthlyWaste}`,
      `Active seats,${activeSeats ?? 0},${costPerSeat},${(activeSeats ?? 0) * costPerSeat}`,
      `Provisioned seats,${provisionedSeats ?? 0},${costPerSeat},${(provisionedSeats ?? 0) * costPerSeat}`,
    ];
    const csv = rows.join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'inactive-seats.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // Derive seat utilization trend from real API data
  const seatTrendDays = seatBuckets.slice(-7).map((b) => formatWeekday(b.bucket));
  const seatTrendActive = seatBuckets.slice(-7).map((b) => b.active_seat_count);
  const seatTrendInactive = seatBuckets
    .slice(-7)
    .map((b) => b.provisioned_seat_count - b.active_seat_count);

  return (
    <>
      {overview?.error && (
        <SampleDataBanner
          message={
            overview.message ?? 'Copilot metrics data is unavailable. Displaying limited data.'
          }
        />
      )}

      {/* Seat waste alert banner — derived from real API data */}
      {latestSeatBucket && inactiveSeats > 0 && (
        <div className={styles.wasteAlert}>
          <span style={{ fontSize: 18, lineHeight: 1 }}>⚠️</span>
          <div className={styles.wasteBody}>
            <div className={styles.wasteTitle}>
              Seat waste detected —{' '}
              <span
                className={styles.clickableStat}
                role="button"
                tabIndex={0}
                onClick={() => setOverviewModal('seat-waste')}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setOverviewModal('seat-waste');
                  }
                }}
              >
                ${monthlyWaste.toLocaleString()}/month
              </span>{' '}
              in unused licenses
            </div>
            <div className={styles.wasteDesc}>
              <span
                className={styles.clickableStat}
                role="button"
                tabIndex={0}
                onClick={() => setOverviewModal('seat-waste')}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setOverviewModal('seat-waste');
                  }
                }}
              >
                {inactiveSeats} seats
              </span>{' '}
              inactive (provisioned but not active in last 30 days) at ${costPerSeat}/seat/month
            </div>
          </div>
          <Button size="sm" variant="danger" onClick={handleExportInactive}>
            Export inactive list
          </Button>
        </div>
      )}

      {isError && <ErrorBanner message="Failed to load Copilot data" onRetry={onRetry} />}
      {isLoading && <Spinner />}

      {/* Metric strip */}
      <div className={styles.metricStrip}>
        <MetricCard
          value={seatLabel}
          label="Active / total seats (latest)"
          delta={avgUtilPct != null ? `${avgUtilPct}% avg utilization` : '—'}
          deltaDir="neutral"
          onClick={handleActiveSeatsClick}
          helpText="Currently active vs. total provisioned Copilot seats. Synced daily from the GitHub Copilot API. Click to scroll to the utilization table."
        />
        <MetricCard
          value={totalAssigned > 0 ? String(totalAssigned) : '—'}
          label="Seats assigned (30d)"
          delta="cumulative"
          deltaDir="up"
          onClick={() => setDrillDown('assigned')}
          helpText="Total Copilot seats assigned in the last 30 days. From daily seat-change sync. A rising trend indicates growing adoption."
        />
        <MetricCard
          value={totalRevoked > 0 ? String(totalRevoked) : '—'}
          label="Seats revoked (30d)"
          delta="cumulative"
          deltaDir={totalRevoked > 0 ? 'down' : 'neutral'}
          onClick={() => setDrillDown('revoked')}
          helpText="Total Copilot seats revoked in the last 30 days. From daily seat-change sync. Review revocations to ensure intentional offboarding."
        />
        <MetricCard
          value={netSeats !== 0 ? `${netSeats > 0 ? '+' : ''}${netSeats}` : '—'}
          label="Net seat change (30d)"
          delta="assigned minus revoked"
          deltaDir={netSeats > 0 ? 'up' : netSeats < 0 ? 'down' : 'neutral'}
          onClick={() => setDrillDown('net')}
          helpText="Net change in Copilot seats (assigned minus revoked) over 30 days. From daily sync data. Positive means fleet is growing."
        />
      </div>

      {/* Drill-down modal */}
      <Modal
        open={drillDown !== null}
        onClose={() => setDrillDown(null)}
        title={drillDownTitle()}
        width={640}
      >
        {drillDown === 'active-seats' && (
          <DataTable<SeatUtilizationBucket>
            columns={[
              {
                key: 'date',
                header: 'Date',
                filterable: true,
                helpText:
                  'The date of this daily Copilot usage snapshot. Synced once per day from the GitHub Copilot API.',
                render: (b) => (
                  <span style={{ color: 'var(--fg-muted)' }}>{formatBucketDate(b.bucket)}</span>
                ),
                filterValue: (b) => formatBucketDate(b.bucket),
              },
              {
                key: 'active',
                header: 'Active',
                sortable: true,
                helpText:
                  'Number of seats with recorded Copilot activity on this day. From daily usage sync.',
                render: (b) => (
                  <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {b.active_seat_count ?? '—'}
                  </span>
                ),
                sortValue: (b) => b.active_seat_count ?? 0,
              },
              {
                key: 'provisioned',
                header: 'Provisioned',
                sortable: true,
                helpText:
                  'Total Copilot seats provisioned (assigned) on this day. From the GitHub Copilot seat management API.',
                render: (b) => (
                  <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {b.provisioned_seat_count ?? '—'}
                  </span>
                ),
                sortValue: (b) => b.provisioned_seat_count ?? 0,
              },
              {
                key: 'utilization',
                header: 'Utilization %',
                sortable: true,
                helpText:
                  'Percentage of provisioned Copilot seats that were active. Synced daily from GitHub Copilot API. Target 70%+ utilization to maximize ROI.',
                render: (b) => (
                  <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {b.utilization_pct != null ? `${Math.round(b.utilization_pct)}%` : '—'}
                  </span>
                ),
                sortValue: (b) => b.utilization_pct ?? 0,
              },
            ]}
            data={seatBuckets}
            rowKey={(b) => b.bucket}
          />
        )}
        {drillDown === 'assigned' && (
          <DataTable<CopilotSeatsBucket>
            columns={[
              {
                key: 'date',
                header: 'Date',
                filterable: true,
                helpText:
                  'The date of this daily Copilot seat-change snapshot. Synced once per day from the GitHub Copilot API.',
                render: (b) => (
                  <span style={{ color: 'var(--fg-muted)' }}>{formatBucketDate(b.bucket)}</span>
                ),
                filterValue: (b) => formatBucketDate(b.bucket),
              },
              {
                key: 'assigned',
                header: 'Assigned',
                sortable: true,
                helpText:
                  'Number of new Copilot seats assigned on this day. From daily seat-change sync.',
                render: (b) => (
                  <span style={{ color: 'var(--success)', fontVariantNumeric: 'tabular-nums' }}>
                    +{b.seats_assigned ?? 0}
                  </span>
                ),
                sortValue: (b) => b.seats_assigned ?? 0,
              },
            ]}
            data={copilotBuckets}
            rowKey={(b) => b.bucket}
          />
        )}
        {drillDown === 'revoked' && (
          <DataTable<CopilotSeatsBucket>
            columns={[
              {
                key: 'date',
                header: 'Date',
                filterable: true,
                helpText:
                  'The date of this daily Copilot seat-change snapshot. Synced once per day from the GitHub Copilot API.',
                render: (b) => (
                  <span style={{ color: 'var(--fg-muted)' }}>{formatBucketDate(b.bucket)}</span>
                ),
                filterValue: (b) => formatBucketDate(b.bucket),
              },
              {
                key: 'revoked',
                header: 'Revoked',
                sortable: true,
                helpText:
                  'Number of Copilot seats revoked on this day. From daily seat-change sync. Spikes may indicate offboarding events.',
                render: (b) => (
                  <span
                    style={{
                      color: b.seats_revoked > 0 ? 'var(--danger)' : undefined,
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {b.seats_revoked > 0 ? `-${b.seats_revoked}` : '—'}
                  </span>
                ),
                sortValue: (b) => b.seats_revoked ?? 0,
              },
            ]}
            data={copilotBuckets}
            rowKey={(b) => b.bucket}
          />
        )}
        {drillDown === 'net' && (
          <DataTable<CopilotSeatsBucket>
            columns={[
              {
                key: 'date',
                header: 'Date',
                filterable: true,
                helpText:
                  'The date of this daily Copilot seat-change snapshot. Synced once per day from the GitHub Copilot API.',
                render: (b) => (
                  <span style={{ color: 'var(--fg-muted)' }}>{formatBucketDate(b.bucket)}</span>
                ),
                filterValue: (b) => formatBucketDate(b.bucket),
              },
              {
                key: 'assigned',
                header: 'Assigned',
                sortable: true,
                helpText:
                  'Number of new Copilot seats assigned on this day. From daily seat-change sync.',
                render: (b) => (
                  <span style={{ color: 'var(--success)', fontVariantNumeric: 'tabular-nums' }}>
                    +{b.seats_assigned ?? 0}
                  </span>
                ),
                sortValue: (b) => b.seats_assigned ?? 0,
              },
              {
                key: 'revoked',
                header: 'Revoked',
                sortable: true,
                helpText:
                  'Number of Copilot seats revoked on this day. From daily seat-change sync.',
                render: (b) => (
                  <span
                    style={{
                      color: b.seats_revoked > 0 ? 'var(--danger)' : undefined,
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {b.seats_revoked > 0 ? `-${b.seats_revoked}` : '—'}
                  </span>
                ),
                sortValue: (b) => b.seats_revoked ?? 0,
              },
              {
                key: 'net',
                header: 'Net',
                sortable: true,
                helpText:
                  'Net seat change (assigned minus revoked) for this day. Positive values indicate fleet growth.',
                render: (b) => (
                  <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {b.seats_net > 0 ? `+${b.seats_net}` : b.seats_net}
                  </span>
                ),
                sortValue: (b) => b.seats_net ?? 0,
              },
            ]}
            data={copilotBuckets}
            rowKey={(b) => b.bucket}
          />
        )}
      </Modal>

      {/* Charts row */}
      <div className={styles.grid2}>
        <Card>
          <CardHeader>Acceptance rate — 7-day rolling average</CardHeader>
          {overviewLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
              <Spinner />
            </div>
          ) : acceptanceRateDays.length > 0 ? (
            <LineAreaChart
              xAxisData={acceptanceRateDays}
              series={[
                {
                  name: 'Acceptance rate',
                  data: acceptanceRateValues,
                  color: '#bc8cff',
                  areaOpacity: 0.15,
                },
                {
                  name: `${overview?.acceptance_threshold ?? 25}% good threshold`,
                  data: acceptanceThresholdLine,
                  color: '#3fb950',
                  dashed: true,
                },
              ]}
              yAxisFormatter={(v: number) => `${v}%`}
              height={200}
            />
          ) : (
            <div style={{ color: 'var(--fg-muted)', padding: '24px 0', textAlign: 'center' }}>
              No acceptance rate data available.
            </div>
          )}
        </Card>
        <Card>
          <CardHeader>Seat utilization trend</CardHeader>
          <LineAreaChart
            xAxisData={seatTrendDays}
            series={[
              { name: 'Active', data: seatTrendActive, color: '#58a6ff', areaOpacity: 0.1 },
              { name: 'Inactive', data: seatTrendInactive, color: '#d29922' },
            ]}
            height={200}
          />
        </Card>
      </div>

      {/* Seat utilization table */}
      {seatBuckets.length > 0 && (
        <div ref={seatTableRef}>
          <div className={styles.sectionTitle}>Seat utilization — last 30 days</div>
          <Card style={{ marginBottom: 20 }}>
            <CardHeader>Active seats / provisioned seats over time</CardHeader>
            <DataTable<SeatUtilizationBucket>
              columns={[
                {
                  key: 'date',
                  header: 'Date',
                  filterable: true,
                  helpText:
                    'The date of this daily Copilot usage snapshot. Synced once per day from the GitHub Copilot API.',
                  render: (b) => (
                    <span style={{ color: 'var(--fg-muted)' }}>{formatBucketDate(b.bucket)}</span>
                  ),
                  filterValue: (b) => formatBucketDate(b.bucket),
                },
                {
                  key: 'active',
                  header: 'Active seats',
                  sortable: true,
                  helpText:
                    'Number of seats with recorded Copilot activity on this day. From daily usage sync.',
                  render: (b) => (
                    <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {b.active_seat_count ?? '—'}
                    </span>
                  ),
                  sortValue: (b) => b.active_seat_count ?? 0,
                },
                {
                  key: 'provisioned',
                  header: 'Provisioned',
                  sortable: true,
                  helpText:
                    'Total Copilot seats provisioned (assigned) on this day. From the GitHub Copilot seat management API.',
                  render: (b) => (
                    <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {b.provisioned_seat_count ?? '—'}
                    </span>
                  ),
                  sortValue: (b) => b.provisioned_seat_count ?? 0,
                },
                {
                  key: 'utilization',
                  header: 'Utilization',
                  sortable: true,
                  helpText:
                    'Percentage of provisioned Copilot seats that were active. Synced daily from GitHub Copilot API. Target 70%+ utilization to maximize ROI.',
                  render: (b) => (
                    <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {b.utilization_pct != null ? `${Math.round(b.utilization_pct)}%` : '—'}
                    </span>
                  ),
                  sortValue: (b) => b.utilization_pct ?? 0,
                },
              ]}
              data={seatBuckets.slice(-10)}
              rowKey={(b) => b.bucket}
            />
          </Card>
        </div>
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
          {overviewLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
              <Spinner />
            </div>
          ) : languages.length > 0 ? (
            <div className={styles.langBars}>
              {languages.map((l) => (
                <div
                  key={l.lang}
                  className={`${styles.langRow} ${styles.langRowClickable}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    setSelectedLang(l.lang);
                    setOverviewModal('language');
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelectedLang(l.lang);
                      setOverviewModal('language');
                    }
                  }}
                >
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
          ) : (
            <div style={{ color: 'var(--fg-muted)', padding: '12px 0' }}>
              No language data available.
            </div>
          )}
          <div className={styles.langNote}>
            Language data from Copilot telemetry (not available via audit log)
          </div>
        </Card>
        <Card>
          <CardHeader>Seat change history (30d)</CardHeader>
          {copilotBuckets.length > 0 ? (
            <DataTable<CopilotSeatsBucket>
              columns={[
                {
                  key: 'date',
                  header: 'Date',
                  filterable: true,
                  helpText:
                    'The date of this daily Copilot seat-change snapshot. Synced once per day from the GitHub Copilot API.',
                  render: (b) => (
                    <span style={{ color: 'var(--fg-muted)' }}>{formatBucketDate(b.bucket)}</span>
                  ),
                  filterValue: (b) => formatBucketDate(b.bucket),
                },
                {
                  key: 'assigned',
                  header: 'Assigned',
                  sortable: true,
                  helpText:
                    'Number of new Copilot seats assigned on this day. From daily seat-change sync.',
                  render: (b) => (
                    <span style={{ color: 'var(--success)', fontVariantNumeric: 'tabular-nums' }}>
                      +{b.seats_assigned ?? 0}
                    </span>
                  ),
                  sortValue: (b) => b.seats_assigned ?? 0,
                },
                {
                  key: 'revoked',
                  header: 'Revoked',
                  sortable: true,
                  helpText:
                    'Number of Copilot seats revoked on this day. From daily seat-change sync.',
                  render: (b) => (
                    <span
                      style={{
                        color: b.seats_revoked ? 'var(--danger)' : undefined,
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      {b.seats_revoked > 0 ? `-${b.seats_revoked}` : '—'}
                    </span>
                  ),
                  sortValue: (b) => b.seats_revoked ?? 0,
                },
                {
                  key: 'net',
                  header: 'Net',
                  sortable: true,
                  helpText:
                    'Net seat change (assigned minus revoked) for this day. Positive values indicate fleet growth.',
                  render: (b) => (
                    <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {b.seats_net > 0 ? `+${b.seats_net}` : b.seats_net}
                    </span>
                  ),
                  sortValue: (b) => b.seats_net ?? 0,
                },
              ]}
              data={copilotBuckets.slice(-7)}
              rowKey={(b) => b.bucket}
            />
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
                Teams with &gt;30% acceptance rate tend to show{' '}
                <span
                  className={styles.clickableStat}
                  role="button"
                  tabIndex={0}
                  onClick={() => setOverviewModal('correlation-cycle')}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setOverviewModal('correlation-cycle');
                    }
                  }}
                >
                  shorter cycle times
                </span>{' '}
                on average compared to teams below 20% acceptance.
              </div>
            </div>
          </div>
          <div className={styles.insightWarn}>
            <span>⚠️</span>
            <div>
              <div className={styles.insightTitle}>Active seats ≠ effective usage</div>
              <div className={styles.insightBody}>
                Some{' '}
                <span
                  className={styles.clickableStat}
                  role="button"
                  tabIndex={0}
                  onClick={() => setOverviewModal('correlation-seats')}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setOverviewModal('correlation-seats');
                    }
                  }}
                >
                  seats
                </span>{' '}
                show activity but acceptance rate is below 10% — suggesting Copilot is active but
                suggestions are being dismissed. Consider targeted training.
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* Seat waste modal */}
      <Modal
        open={overviewModal === 'seat-waste'}
        onClose={() => setOverviewModal(null)}
        title="Seat utilization breakdown"
        width={700}
      >
        <div className={styles.sampleDataNote}>
          ℹ️ Showing all seat utilization buckets from the API. Active, provisioned, and cost data
          is derived from live seat counts.
        </div>
        <DataTable<SeatUtilizationBucket>
          columns={[
            {
              key: 'date',
              header: 'Date',
              filterable: true,
              helpText:
                'The date of this daily Copilot usage snapshot. Synced once per day from the GitHub Copilot API.',
              render: (b) => (
                <span style={{ color: 'var(--fg-muted)' }}>{formatBucketDate(b.bucket)}</span>
              ),
              filterValue: (b) => formatBucketDate(b.bucket),
            },
            {
              key: 'active',
              header: 'Active',
              sortable: true,
              helpText:
                'Number of seats with recorded Copilot activity on this day. From daily usage sync.',
              render: (b) => (
                <span style={{ fontVariantNumeric: 'tabular-nums' }}>{b.active_seat_count}</span>
              ),
              sortValue: (b) => b.active_seat_count ?? 0,
            },
            {
              key: 'provisioned',
              header: 'Provisioned',
              sortable: true,
              helpText:
                'Total Copilot seats provisioned (assigned) on this day. From the GitHub Copilot seat management API.',
              render: (b) => (
                <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {b.provisioned_seat_count}
                </span>
              ),
              sortValue: (b) => b.provisioned_seat_count ?? 0,
            },
            {
              key: 'inactive',
              header: 'Inactive',
              sortable: true,
              helpText:
                'Number of provisioned seats with no Copilot activity. Calculated as provisioned minus active. Consider reclaiming these seats.',
              render: (b) => {
                const inactive = b.provisioned_seat_count - b.active_seat_count;
                return (
                  <span
                    style={{
                      fontVariantNumeric: 'tabular-nums',
                      color: inactive > 0 ? 'var(--danger)' : undefined,
                    }}
                  >
                    {inactive}
                  </span>
                );
              },
              sortValue: (b) => b.provisioned_seat_count - b.active_seat_count,
            },
            {
              key: 'utilization',
              header: 'Utilization %',
              sortable: true,
              helpText:
                'Percentage of provisioned Copilot seats that were active. Synced daily from GitHub Copilot API. Target 70%+ utilization to maximize ROI.',
              render: (b) => (
                <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {b.utilization_pct != null ? `${Math.round(b.utilization_pct)}%` : '—'}
                </span>
              ),
              sortValue: (b) => b.utilization_pct ?? 0,
            },
            {
              key: 'cost',
              header: 'Cost ($/mo)',
              sortable: true,
              helpText:
                'Estimated monthly cost based on provisioned seats times the configured cost per seat. Adjust cost per seat in org settings.',
              render: (b) => (
                <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                  ${(b.provisioned_seat_count * costPerSeat).toLocaleString()}
                </span>
              ),
              sortValue: (b) => b.provisioned_seat_count * costPerSeat,
            },
          ]}
          data={seatBuckets}
          rowKey={(b) => b.bucket}
          className={styles.modalTable}
        />
      </Modal>

      {/* Correlation insights modals */}
      <Modal
        open={overviewModal === 'correlation-seats'}
        onClose={() => setOverviewModal(null)}
        title="Correlation: Active seats with low acceptance"
        width={520}
      >
        <p style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.6, margin: 0 }}>
          Some seats show activity (suggestions served) but have an acceptance rate below 10%. This
          indicates Copilot is active on these seats but suggestions are being dismissed frequently.
          Use the <strong>Adoption</strong> and <strong>Teams</strong> tabs to identify specific
          users and teams for targeted training.
        </p>
      </Modal>

      <Modal
        open={overviewModal === 'correlation-cycle'}
        onClose={() => setOverviewModal(null)}
        title="Correlation: Acceptance rate vs cycle time"
        width={520}
      >
        <p style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.6, margin: 0 }}>
          Teams with &gt;30% acceptance rate tend to show shorter cycle times on average compared to
          teams below 20% acceptance. This correlation suggests that teams effectively using Copilot
          suggestions deliver faster. Use the <strong>Teams</strong> tab for per-team breakdowns.
        </p>
      </Modal>

      {/* Language drill-down modal */}
      <Modal
        open={overviewModal === 'language'}
        onClose={() => setOverviewModal(null)}
        title={selectedLang ? `${selectedLang} — Acceptance rate details` : 'Language details'}
        width={520}
      >
        {selectedLang &&
          (() => {
            const lang = languages.find((l) => l.lang === selectedLang);
            return lang ? (
              <div>
                <p
                  style={{
                    fontSize: 13,
                    color: 'var(--fg-muted)',
                    lineHeight: 1.6,
                    margin: '0 0 12px',
                  }}
                >
                  <strong>{lang.lang}</strong> has an acceptance rate of{' '}
                  <strong>{lang.pct}%</strong>.
                </p>
                <p style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.6, margin: 0 }}>
                  Per-language acceptance breakdowns by team and user require the Copilot Metrics
                  API. This would show which teams are most effective with {lang.lang} completions
                  and where additional training may help.
                </p>
              </div>
            ) : null;
          })()}
      </Modal>
    </>
  );
}
