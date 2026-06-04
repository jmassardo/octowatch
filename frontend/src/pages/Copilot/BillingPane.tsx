import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import {
  getCopilotBillingOverview,
  getCopilotUserBudgets,
  getCopilotBillingTrends,
} from '../../api/copilotMetrics';
import type { CopilotUserBudget, CopilotBillingTrendDay } from '../../api/copilotMetrics';
import styles from './Copilot.module.css';

const tabNums: React.CSSProperties = { fontVariantNumeric: 'tabular-nums' };

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    ok: 'var(--color-success)',
    warning: 'var(--color-warning)',
    near: 'var(--color-warning)',
    over: 'var(--color-danger)',
    blocked: 'var(--color-danger)',
  };
  const labelMap: Record<string, string> = {
    ok: 'OK',
    warning: 'Warning',
    near: 'Near Limit',
    over: 'Over Budget',
    blocked: 'Blocked',
  };

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.25rem',
        padding: '0.125rem 0.5rem',
        borderRadius: '9999px',
        fontSize: '0.75rem',
        fontWeight: 500,
        backgroundColor: `color-mix(in srgb, ${colorMap[status] ?? 'var(--fg-muted)'} 15%, transparent)`,
        color: colorMap[status] ?? 'var(--fg-muted)',
      }}
    >
      <span
        style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          backgroundColor: colorMap[status] ?? 'var(--fg-muted)',
        }}
      />
      {labelMap[status] ?? status}
    </span>
  );
}

function UtilizationHistogram({ buckets }: { buckets: Record<string, number> }) {
  const bucketOrder = ['0-50', '50-80', '80-90', '90-100', '100+'];
  const bucketLabels: Record<string, string> = {
    '0-50': '0–50%',
    '50-80': '50–80%',
    '80-90': '80–90%',
    '90-100': '90–100%',
    '100+': '100%+',
  };
  const bucketColors: Record<string, string> = {
    '0-50': 'var(--color-success)',
    '50-80': '#58a6ff',
    '80-90': 'var(--color-warning)',
    '90-100': '#f0883e',
    '100+': 'var(--color-danger)',
  };

  const maxCount = Math.max(...bucketOrder.map((b) => buckets[b] ?? 0), 1);

  return (
    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end', height: '120px' }}>
      {bucketOrder.map((bucket) => {
        const count = buckets[bucket] ?? 0;
        const height = maxCount > 0 ? Math.max((count / maxCount) * 100, 4) : 4;
        return (
          <div
            key={bucket}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              flex: 1,
              height: '100%',
              justifyContent: 'flex-end',
            }}
          >
            <span style={{ fontSize: '0.7rem', fontWeight: 600, marginBottom: '0.25rem' }}>
              {count}
            </span>
            <div
              style={{
                width: '100%',
                height: `${height}%`,
                backgroundColor: bucketColors[bucket],
                borderRadius: '4px 4px 0 0',
                minHeight: '4px',
              }}
            />
            <span
              style={{
                fontSize: '0.65rem',
                color: 'var(--fg-muted)',
                marginTop: '0.25rem',
                whiteSpace: 'nowrap',
              }}
            >
              {bucketLabels[bucket]}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function SpendTrendChart({ trends }: { trends: CopilotBillingTrendDay[] }) {
  if (trends.length === 0) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--fg-muted)' }}>
        No trend data available yet.
      </div>
    );
  }

  const maxTotal = Math.max(...trends.map((t) => t.total), 1);

  return (
    <div
      style={{
        position: 'relative',
        height: '160px',
        display: 'flex',
        alignItems: 'flex-end',
        gap: '2px',
      }}
    >
      {trends.map((day) => {
        const height = (day.total / maxTotal) * 100;
        return (
          <div
            key={day.date}
            title={`${day.date}: $${day.total.toFixed(2)} (${day.active_users} users)`}
            style={{
              flex: 1,
              height: `${Math.max(height, 2)}%`,
              background: 'linear-gradient(to top, var(--color-success), #58a6ff)',
              borderRadius: '2px 2px 0 0',
              minWidth: '3px',
            }}
          />
        );
      })}
    </div>
  );
}

export function BillingPane() {
  const [searchTerm, setSearchTerm] = useState('');

  const {
    data: overview,
    isLoading: loadingOverview,
    isError: errorOverview,
  } = useQuery({
    queryKey: ['copilot', 'billing-overview'],
    queryFn: getCopilotBillingOverview,
    staleTime: 5 * 60 * 1000,
  });

  const { data: budgets, isLoading: loadingBudgets } = useQuery({
    queryKey: ['copilot', 'user-budgets'],
    queryFn: getCopilotUserBudgets,
    staleTime: 5 * 60 * 1000,
  });

  const { data: trends, isLoading: loadingTrends } = useQuery({
    queryKey: ['copilot', 'billing-trends'],
    queryFn: getCopilotBillingTrends,
    staleTime: 5 * 60 * 1000,
  });

  const isLoading = loadingOverview || loadingBudgets || loadingTrends;

  const columns: ColumnDef<CopilotUserBudget>[] = useMemo(
    () => [
      {
        key: 'login',
        header: 'User',
        filterable: true,
        render: (row) => (
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <img
              src={`https://github.com/${row.login}.png?size=24`}
              alt={row.login}
              style={{ width: 20, height: 20, borderRadius: '50%' }}
            />
            <span style={{ fontWeight: 500 }}>{row.login}</span>
          </span>
        ),
      },
      {
        key: 'budget',
        header: 'Budget ($)',
        render: (row) => (
          <span style={tabNums}>{row.budget != null ? `$${row.budget.toFixed(2)}` : '—'}</span>
        ),
      },
      {
        key: 'consumed',
        header: 'Consumed ($)',
        render: (row) => <span style={tabNums}>${row.consumed.toFixed(2)}</span>,
      },
      {
        key: 'utilization_pct',
        header: 'Utilization',
        render: (row) => <span style={tabNums}>{row.utilization_pct.toFixed(1)}%</span>,
      },
      {
        key: 'status',
        header: 'Status',
        render: (row) => <StatusBadge status={row.status} />,
      },
      {
        key: 'org_slug',
        header: 'Organization',
        render: (row) => <span>{row.org_slug}</span>,
      },
    ],
    [],
  );

  const filteredUsers = useMemo(() => {
    const users = budgets?.users ?? [];
    if (!searchTerm) return users;
    const term = searchTerm.toLowerCase();
    return users.filter(
      (u) => u.login.toLowerCase().includes(term) || u.org_slug.toLowerCase().includes(term),
    );
  }, [budgets?.users, searchTerm]);

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
        <Spinner />
      </div>
    );
  }

  if (errorOverview || overview?.error) {
    return <ErrorBanner message={overview?.message ?? 'Failed to load billing data.'} />;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Pool Overview Cards */}
      <div className={styles.metricStrip}>
        <MetricCard
          label="AI Credit Pool"
          value={`$${(overview?.pool_total ?? 0).toLocaleString()}`}
          helpText="Total allocated credits"
        />
        <MetricCard
          label="Consumed This Period"
          value={`$${(overview?.total_consumed ?? 0).toLocaleString()}`}
          delta={`${overview?.utilization_pct ?? 0}% of pool`}
          deltaDir="neutral"
        />
        <MetricCard
          label="Projected End-of-Month"
          value={`$${(overview?.projected_eom ?? 0).toLocaleString()}`}
          delta={`$${(overview?.daily_rate ?? 0).toFixed(0)}/day avg`}
          deltaDir="neutral"
        />
        <MetricCard
          label="Pool Remaining"
          value={`$${(overview?.pool_remaining ?? 0).toLocaleString()}`}
          delta={`${overview?.unique_users ?? 0} active users`}
          deltaDir="neutral"
        />
      </div>

      {/* Utilization Histogram + Spend Trend */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '1rem' }}>
        <Card>
          <CardHeader>Budget Utilization Distribution</CardHeader>
          <div style={{ padding: '1rem' }}>
            <UtilizationHistogram buckets={budgets?.buckets ?? {}} />
            <p
              style={{
                fontSize: '0.75rem',
                color: 'var(--fg-muted)',
                marginTop: '0.75rem',
                textAlign: 'center',
              }}
            >
              {budgets?.total_users ?? 0} users across all organizations
            </p>
          </div>
        </Card>

        <Card>
          <CardHeader>Daily Credit Consumption (30 days)</CardHeader>
          <div style={{ padding: '1rem' }}>
            <SpendTrendChart trends={trends?.trends ?? []} />
          </div>
        </Card>
      </div>

      {/* User Budget Table */}
      <Card>
        <CardHeader>User Budgets</CardHeader>
        <div style={{ padding: '0.75rem 1rem 0' }}>
          <input
            type="text"
            placeholder="Search users..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              width: '100%',
              maxWidth: '320px',
              padding: '0.5rem 0.75rem',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              fontSize: '0.875rem',
              background: 'var(--bg-surface)',
              color: 'var(--fg)',
            }}
          />
        </div>
        <DataTable
          columns={columns}
          data={filteredUsers}
          rowKey={(u) => `${u.org_slug}/${u.login}`}
        />
      </Card>
    </div>
  );
}
