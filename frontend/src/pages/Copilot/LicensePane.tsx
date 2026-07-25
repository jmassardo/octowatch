import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Modal } from '../../components/primitives/Modal';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { getCopilotROI } from '../../api/copilotMetrics';
import type { CopilotGhostMember } from '../../api/copilotMetrics';
import type { SeatUtilizationBucket } from '../../types/reports';
import { useOrg } from '../../hooks/useOrg';
import { useOrgConfig } from '../../hooks/useOrgConfig';
import { formatBucketDate } from '../../utils/dates';
import styles from './Copilot.module.css';

type LicenseDrillDown = 'total' | 'active' | 'inactive' | 'waste' | null;

const tabNums: React.CSSProperties = { fontVariantNumeric: 'tabular-nums' };
const mutedText: React.CSSProperties = { color: 'var(--fg-muted)' };

interface LicensePaneProps {
  seatBuckets: SeatUtilizationBucket[];
}

export function LicensePane({ seatBuckets }: LicensePaneProps) {
  const [drillDown, setDrillDown] = useState<LicenseDrillDown>(null);
  const costSectionRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { costPerSeat } = useOrgConfig();
  const { selectedOrg } = useOrg();
  const orgParam = selectedOrg || undefined;

  const { data: roiData } = useQuery({
    queryKey: ['copilot', 'roi', orgParam],
    queryFn: () => getCopilotROI(orgParam),
    staleTime: 30 * 60 * 1000,
  });

  const ghostMembers = roiData?.ghost_members ?? [];
  const licenseOpt = roiData?.license_optimization;
  const growthForecast =
    roiData?.growth_forecast && 'current_active' in roiData.growth_forecast
      ? roiData.growth_forecast
      : null;

  const ghostMemberColumns: ColumnDef<CopilotGhostMember>[] = useMemo(
    () => [
      {
        key: 'user',
        header: 'User',
        filterable: true,
        helpText: 'GitHub username of the ghost member with no recent Copilot activity.',
        render: (g) => <span style={{ fontWeight: 500 }}>{g.user}</span>,
        filterValue: (g) => g.user,
      },
      {
        key: 'last_activity',
        header: 'Last Activity',
        sortable: true,
        helpText: 'When this user last used Copilot. "Never" means no recorded activity.',
        render: (g) => (
          <span style={{ ...mutedText, ...tabNums }}>
            {g.last_activity === 'Never' ? 'Never' : g.last_activity.split('T')[0]}
          </span>
        ),
        sortValue: (g) => g.days_inactive,
      },
      {
        key: 'days_inactive',
        header: 'Days Inactive',
        sortable: true,
        helpText: 'Number of days since last Copilot activity.',
        render: (g) => (
          <span
            style={{
              ...tabNums,
              color: g.days_inactive >= 90 ? 'var(--danger)' : 'var(--warning)',
            }}
          >
            {g.days_inactive >= 999 ? '—' : `${g.days_inactive}d`}
          </span>
        ),
        sortValue: (g) => g.days_inactive,
      },
      {
        key: 'action',
        header: 'Suggested Action',
        helpText: 'Recommended action for this ghost member seat.',
        render: () => (
          <span style={{ fontSize: 12, color: 'var(--danger)', fontWeight: 500 }}>Revoke</span>
        ),
      },
    ],
    [],
  );

  const dateColumn: ColumnDef<SeatUtilizationBucket> = useMemo(
    () => ({
      key: 'date',
      header: 'Date',
      filterable: true,
      helpText:
        'The date of this daily Copilot usage snapshot. Synced once per day from the GitHub Copilot API.',
      render: (b) => <span style={mutedText}>{formatBucketDate(b.bucket)}</span>,
      filterValue: (b) => formatBucketDate(b.bucket),
    }),
    [],
  );

  const totalColumns: ColumnDef<SeatUtilizationBucket>[] = useMemo(
    () => [
      dateColumn,
      {
        key: 'provisioned',
        header: 'Provisioned',
        sortable: true,
        helpText:
          'Total Copilot seats provisioned (assigned) on this day. From the GitHub Copilot seat management API.',
        render: (b) => <span style={tabNums}>{b.provisioned_seat_count ?? '—'}</span>,
        sortValue: (b) => b.provisioned_seat_count,
      },
    ],
    [dateColumn],
  );

  const activeColumns: ColumnDef<SeatUtilizationBucket>[] = useMemo(
    () => [
      dateColumn,
      {
        key: 'active',
        header: 'Active',
        sortable: true,
        helpText:
          'Number of seats with recorded Copilot activity on this day. From daily usage sync.',
        render: (b) => <span style={tabNums}>{b.active_seat_count ?? '—'}</span>,
        sortValue: (b) => b.active_seat_count,
      },
      {
        key: 'utilization',
        header: 'Utilization %',
        sortable: true,
        helpText:
          'Percentage of provisioned Copilot seats that were active. Synced daily from GitHub Copilot API. Target 70%+ utilization to maximize ROI.',
        render: (b) => (
          <span style={tabNums}>
            {b.utilization_pct != null ? `${Math.round(b.utilization_pct)}%` : '—'}
          </span>
        ),
        sortValue: (b) => b.utilization_pct,
      },
    ],
    [dateColumn],
  );

  const inactiveColumns: ColumnDef<SeatUtilizationBucket>[] = useMemo(
    () => [
      dateColumn,
      {
        key: 'inactive',
        header: 'Inactive',
        sortable: true,
        helpText:
          'Number of provisioned seats with no Copilot activity. Calculated as provisioned minus active. Consider reclaiming these seats.',
        render: (b) => (
          <span style={tabNums}>{b.provisioned_seat_count - b.active_seat_count}</span>
        ),
        sortValue: (b) => b.provisioned_seat_count - b.active_seat_count,
      },
      {
        key: 'provisioned',
        header: 'Provisioned',
        sortable: true,
        helpText:
          'Total Copilot seats provisioned (assigned) on this day. From the GitHub Copilot seat management API.',
        render: (b) => <span style={tabNums}>{b.provisioned_seat_count ?? '—'}</span>,
        sortValue: (b) => b.provisioned_seat_count,
      },
    ],
    [dateColumn],
  );

  const wasteColumns: ColumnDef<SeatUtilizationBucket>[] = useMemo(
    () => [
      dateColumn,
      {
        key: 'inactive',
        header: 'Inactive',
        sortable: true,
        helpText:
          'Number of provisioned seats with no Copilot activity. Calculated as provisioned minus active. Consider reclaiming these seats.',
        render: (b) => (
          <span style={tabNums}>{b.provisioned_seat_count - b.active_seat_count}</span>
        ),
        sortValue: (b) => b.provisioned_seat_count - b.active_seat_count,
      },
      {
        key: 'monthlyCost',
        header: 'Monthly cost',
        sortable: true,
        helpText:
          'Estimated cost of unused Copilot seats. Based on provisioned vs. active seat counts from daily sync data.',
        render: (b) => {
          const bucketInactive = b.provisioned_seat_count - b.active_seat_count;
          return <span style={tabNums}>${(bucketInactive * costPerSeat).toLocaleString()}</span>;
        },
        sortValue: (b) => (b.provisioned_seat_count - b.active_seat_count) * costPerSeat,
      },
    ],
    [dateColumn, costPerSeat],
  );

  if (!seatBuckets || seatBuckets.length === 0) {
    return (
      <Card style={{ padding: 24, textAlign: 'center' }}>
        <div style={{ fontSize: 14, color: 'var(--fg-muted)', lineHeight: 1.6 }}>
          No Copilot seat data available. Import a Copilot Metrics file on the{' '}
          <span
            role="link"
            tabIndex={0}
            style={{ color: 'var(--accent)', cursor: 'pointer', textDecoration: 'underline' }}
            onClick={() => navigate('/settings/integrations')}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                navigate('/settings/integrations');
              }
            }}
          >
            Integrations page
          </span>
          , or connect the Copilot Metrics API.
        </div>
      </Card>
    );
  }

  // Derive seat metrics from real API data
  const latestBucket = seatBuckets[seatBuckets.length - 1];
  const totalSeats = latestBucket?.provisioned_seat_count ?? 0;
  const activeSeats = latestBucket?.active_seat_count ?? 0;
  const inactiveSeats = totalSeats - activeSeats;
  const monthlyWaste = inactiveSeats * costPerSeat;
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
      title: `Revoke ${inactiveSeats} inactive seats to save $${(inactiveSeats * costPerSeat).toLocaleString()}/month`,
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
      {seatBuckets.length === 0 && (
        <SampleDataBanner message="No seat utilization data available. Seat data will populate once synced." />
      )}

      {/* Summary metrics */}
      <div className={styles.metricStrip}>
        <MetricCard
          value={totalSeats > 0 ? String(totalSeats) : '—'}
          label="Total seats"
          delta="provisioned"
          deltaDir="neutral"
          onClick={() => setDrillDown('total')}
          helpText="Total Copilot seats currently provisioned in your organization. From the GitHub Copilot seat management API, synced daily."
        />
        <MetricCard
          value={activeSeats > 0 ? String(activeSeats) : '—'}
          label="Active seats"
          delta={
            totalSeats > 0 ? `${Math.round((activeSeats / totalSeats) * 100)}% utilization` : '—'
          }
          deltaDir="neutral"
          onClick={() => setDrillDown('active')}
          helpText="Number of provisioned seats with recorded Copilot activity in the last 30 days. From daily usage sync. Target 70%+ of total seats."
        />
        <MetricCard
          value={inactiveSeats > 0 ? String(inactiveSeats) : '—'}
          label="Inactive seats"
          delta="provisioned but not active in 30d"
          deltaDir={inactiveSeats > 0 ? 'down' : 'neutral'}
          onClick={() => setDrillDown('inactive')}
          helpText="Number of provisioned seats with no Copilot activity in the last 30 days. These are candidates for seat reclamation to reduce costs."
        />
        <MetricCard
          value={monthlyWaste > 0 ? `$${monthlyWaste.toLocaleString()}` : '—'}
          label="Monthly waste"
          delta={
            annualSavings > 0 ? `$${annualSavings.toLocaleString()}/year potential savings` : '—'
          }
          deltaDir={monthlyWaste > 0 ? 'down' : 'neutral'}
          accent
          onClick={() => {
            if (costSectionRef.current) {
              costSectionRef.current.scrollIntoView({ behavior: 'smooth' });
            }
          }}
          helpText="Estimated cost of unused Copilot seats. Based on provisioned vs. active seat counts from daily sync data. Revoke inactive seats to reclaim this spend."
        />
      </div>

      {/* Drill-down modal */}
      <Modal
        open={drillDown !== null}
        onClose={() => setDrillDown(null)}
        title={drillDownTitle()}
        width={600}
      >
        {drillDown === 'total' && (
          <DataTable<SeatUtilizationBucket>
            columns={totalColumns}
            data={seatBuckets}
            rowKey={(b) => b.bucket}
            className={styles.tableWrap}
          />
        )}
        {drillDown === 'active' && (
          <DataTable<SeatUtilizationBucket>
            columns={activeColumns}
            data={seatBuckets}
            rowKey={(b) => b.bucket}
            className={styles.tableWrap}
          />
        )}
        {drillDown === 'inactive' && (
          <DataTable<SeatUtilizationBucket>
            columns={inactiveColumns}
            data={seatBuckets}
            rowKey={(b) => b.bucket}
            className={styles.tableWrap}
          />
        )}
        {drillDown === 'waste' && (
          <DataTable<SeatUtilizationBucket>
            columns={wasteColumns}
            data={seatBuckets}
            rowKey={(b) => b.bucket}
            className={styles.tableWrap}
          />
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
                ${(totalSeats * costPerSeat).toLocaleString()}
              </span>
            </div>
            <div className={styles.costRow}>
              <span className={styles.costLabel}>Optimized monthly spend</span>
              <span className={styles.costValue} style={{ color: 'var(--success)' }}>
                ${(activeSeats * costPerSeat).toLocaleString()}
              </span>
            </div>
            <div className={[styles.costRow, styles.costRowHighlight].join(' ')}>
              <span className={styles.costLabel}>Potential monthly savings</span>
              <span
                className={styles.costValue}
                style={{ color: 'var(--success)', fontWeight: 600 }}
              >
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

      {/* Savings Opportunity */}
      {licenseOpt && licenseOpt.ghost_member_count > 0 && (
        <div className={styles.metricStrip} style={{ marginTop: 20 }}>
          <MetricCard
            value={`$${licenseOpt.inactive_savings_monthly.toLocaleString()}`}
            label="Monthly Savings"
            delta={`Reclaim ${licenseOpt.ghost_member_count} ghost seats`}
            deltaDir="down"
            accent
            helpText="Estimated monthly savings if all ghost member seats (60+ days inactive) are reclaimed."
          />
          <MetricCard
            value={`$${licenseOpt.inactive_savings_annual.toLocaleString()}`}
            label="Annual Savings"
            delta="projected yearly impact"
            deltaDir="down"
            helpText="Estimated annual savings from reclaiming ghost member seats."
          />
        </div>
      )}

      {/* Growth Forecast */}
      {growthForecast && (
        <Card style={{ marginBottom: 20 }}>
          <CardHeader>Growth Forecast</CardHeader>
          <div style={{ padding: '0 16px 16px' }}>
            <div className={styles.metricStrip}>
              <div className={styles.statCard}>
                <div className={styles.statValue}>{growthForecast.current_active}</div>
                <div className={styles.statLabel}>Current Active</div>
              </div>
              <div className={styles.statCard}>
                <div className={styles.statValue}>{growthForecast.projected_30d}</div>
                <div className={styles.statLabel}>30-Day Projection</div>
              </div>
              <div className={styles.statCard}>
                <div className={styles.statValue}>{growthForecast.projected_90d}</div>
                <div className={styles.statLabel}>90-Day Projection</div>
              </div>
              <div className={styles.statCard}>
                <div
                  className={styles.statValue}
                  style={{
                    color:
                      growthForecast.monthly_growth_pct >= 0 ? 'var(--success)' : 'var(--danger)',
                  }}
                >
                  {growthForecast.monthly_growth_pct > 0 ? '+' : ''}
                  {growthForecast.monthly_growth_pct}%
                </div>
                <div className={styles.statLabel}>Monthly Growth</div>
              </div>
            </div>
            {growthForecast.weeks_to_capacity !== null && (
              <div style={{ marginTop: 12, fontSize: 13, color: 'var(--fg-muted)' }}>
                ⚠️ At current growth rate, you will reach seat capacity in approximately{' '}
                <strong>{growthForecast.weeks_to_capacity} weeks</strong>.
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Ghost Members */}
      {ghostMembers.length > 0 && (
        <Card style={{ marginBottom: 20 }}>
          <CardHeader>
            Ghost Members{' '}
            <span style={{ fontWeight: 400, fontSize: 12, color: 'var(--fg-muted)' }}>
              ({ghostMembers.length} users with 60+ days of inactivity)
            </span>
          </CardHeader>
          <DataTable<CopilotGhostMember>
            columns={ghostMemberColumns}
            data={ghostMembers}
            rowKey={(g) => g.user}
          />
        </Card>
      )}
    </>
  );
}
