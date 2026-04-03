import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardHeader } from '../../components/primitives/Card';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Modal } from '../../components/primitives/Modal';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import type { SeatUtilizationBucket } from '../../types/reports';
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

  const dateColumn: ColumnDef<SeatUtilizationBucket> = useMemo(
    () => ({
      key: 'date',
      header: 'Date',
      filterable: true,
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
        render: (b) => (
          <span style={tabNums}>{b.provisioned_seat_count ?? '—'}</span>
        ),
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
        render: (b) => (
          <span style={tabNums}>{b.active_seat_count ?? '—'}</span>
        ),
        sortValue: (b) => b.active_seat_count,
      },
      {
        key: 'utilization',
        header: 'Utilization %',
        sortable: true,
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
        render: (b) => (
          <span style={tabNums}>
            {b.provisioned_seat_count - b.active_seat_count}
          </span>
        ),
        sortValue: (b) => b.provisioned_seat_count - b.active_seat_count,
      },
      {
        key: 'provisioned',
        header: 'Provisioned',
        sortable: true,
        render: (b) => (
          <span style={tabNums}>{b.provisioned_seat_count ?? '—'}</span>
        ),
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
        render: (b) => (
          <span style={tabNums}>
            {b.provisioned_seat_count - b.active_seat_count}
          </span>
        ),
        sortValue: (b) => b.provisioned_seat_count - b.active_seat_count,
      },
      {
        key: 'monthlyCost',
        header: 'Monthly cost',
        sortable: true,
        render: (b) => {
          const bucketInactive = b.provisioned_seat_count - b.active_seat_count;
          return (
            <span style={tabNums}>
              ${(bucketInactive * costPerSeat).toLocaleString()}
            </span>
          );
        },
        sortValue: (b) =>
          (b.provisioned_seat_count - b.active_seat_count) * costPerSeat,
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
            onClick={() => navigate('/integrations')}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                navigate('/integrations');
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
      <SampleDataBanner message="Cost-per-seat ($19) is a default estimate. Requires Copilot Metrics API integration for actual pricing and seat-level activity data." />

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
          delta={
            totalSeats > 0 ? `${Math.round((activeSeats / totalSeats) * 100)}% utilization` : '—'
          }
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
    </>
  );
}
