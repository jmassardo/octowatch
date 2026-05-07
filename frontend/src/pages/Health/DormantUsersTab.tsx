import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { getDormantUsers } from '../../api/healthSignals';
import type { DormantUser } from '../../api/healthSignals';
import { formatDateOnly } from '../../utils/dates';
import styles from './DormantUsersTab.module.css';

function inactivityVariant(days: number): 'danger' | 'attention' | 'muted' {
  if (days > 180) return 'danger';
  if (days > 90) return 'attention';
  return 'muted';
}

const columns: ColumnDef<DormantUser>[] = [
  {
    key: 'user',
    header: 'User',
    sortable: true,
    filterable: true,
    render: (row) => row.login,
    sortValue: (row) => row.login,
    filterValue: (row) => row.login,
    helpText: 'GitHub login of the dormant user.',
  },
  {
    key: 'last_activity',
    header: 'Last Activity',
    sortable: true,
    render: (row) => (
      <span style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(row.last_activity_date)}</span>
    ),
    sortValue: (row) => row.last_activity_date ?? '',
    helpText: 'Date of the most recent audit log event for this user.',
  },
  {
    key: 'days_inactive',
    header: 'Days Inactive',
    sortable: true,
    render: (row) => (
      <Label variant={inactivityVariant(row.days_inactive)}>{row.days_inactive} days</Label>
    ),
    sortValue: (row) => row.days_inactive,
    helpText: 'Number of days since the user last generated any audit log event.',
  },
  {
    key: 'seat_type',
    header: 'Seat Type',
    sortable: true,
    filterable: true,
    render: (row) => (
      <span>{row.seat_type === 'github+copilot' ? '🤖 GitHub + Copilot' : '👤 GitHub'}</span>
    ),
    sortValue: (row) => row.seat_type,
    filterValue: (row) => row.seat_type,
    helpText: 'Whether the user has a standard GitHub seat or also holds a Copilot seat.',
  },
  {
    key: 'cost',
    header: 'Monthly Cost',
    sortable: true,
    render: (row) => (
      <span style={{ fontVariantNumeric: 'tabular-nums' }}>
        ${row.estimated_monthly_cost.toFixed(0)}
      </span>
    ),
    sortValue: (row) => row.estimated_monthly_cost,
    helpText: 'Estimated monthly license cost. GitHub seat ~$21/mo, GitHub + Copilot ~$40/mo.',
  },
  {
    key: 'action',
    header: 'Recommended Action',
    render: (row) => (
      <span style={{ fontSize: 12, color: 'var(--fg-muted)' }}>{row.recommended_action}</span>
    ),
    helpText: 'Suggested next step based on the inactivity period.',
  },
];

export function DormantUsersTab() {
  const [threshold, setThreshold] = useState(90);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['health', 'dormant-users', threshold],
    queryFn: () => getDormantUsers(threshold),
    staleTime: 60_000,
  });

  const users = data?.users ?? [];
  const totalDormant = data?.summary?.total_dormant ?? 0;
  const monthlyWaste = data?.summary?.estimated_monthly_waste ?? 0;

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spinner size={28} />
      </div>
    );
  }

  return (
    <div className={styles.pane}>
      <div className={styles.sliderWrap}>
        <label htmlFor="dormancy-threshold">Inactivity threshold:</label>
        <input
          id="dormancy-threshold"
          type="range"
          min={30}
          max={365}
          step={15}
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
        />
        <span className={styles.sliderValue}>{threshold} days</span>
      </div>

      <div className={styles.metricGrid}>
        <MetricCard
          value={String(totalDormant)}
          label="Dormant users"
          accent={totalDormant > 0}
          helpText="Total users with no audit log activity beyond the selected threshold."
        />
        <MetricCard
          value={`$${monthlyWaste.toLocaleString()}`}
          label="Est. monthly waste"
          accent={monthlyWaste > 0}
          helpText="Estimated monthly license cost for all dormant users."
        />
        <MetricCard
          value={`$${(monthlyWaste * 12).toLocaleString()}`}
          label="Est. annual waste"
          helpText="Projected annual license cost if dormant seats remain active."
        />
      </div>

      {isError && (
        <ErrorBanner message="Failed to load dormant users" onRetry={() => void refetch()} />
      )}

      {!isError && users.length === 0 && (
        <div style={{ color: 'var(--fg-muted)', fontSize: 13, padding: 16, textAlign: 'center' }}>
          No dormant users detected with the current threshold ({threshold} days)
        </div>
      )}

      {!isError && users.length > 0 && (
        <div className={styles.tableWrap}>
          <DataTable
            columns={columns}
            data={users}
            rowKey={(row) => row.login}
            emptyMessage="No dormant users detected"
          />
        </div>
      )}

      <div className={styles.sourceNote}>
        ℹ️ Derived from audit log event activity per actor. Copilot seat status from{' '}
        <code className={styles.sourceCode}>copilot.cfb_seat_*</code> events.
      </div>
    </div>
  );
}
