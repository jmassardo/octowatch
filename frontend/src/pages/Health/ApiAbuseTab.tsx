import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { getApiAbuseSignals } from '../../api/healthSignals';
import type { AbuseSignal } from '../../api/healthSignals';
import { formatRelative } from '../../utils/dates';
import styles from './ApiAbuseTab.module.css';

function severityVariant(severity: string): 'danger' | 'attention' | 'muted' | 'severe' {
  switch (severity) {
    case 'critical':
      return 'danger';
    case 'high':
      return 'severe';
    case 'medium':
      return 'attention';
    default:
      return 'muted';
  }
}

function signalTypeLabel(type: string): string {
  switch (type) {
    case 'rate_limit_violation':
      return 'Rate Limit';
    case 'failed_auth':
      return 'Failed Auth';
    case 'bulk_operation':
      return 'Bulk Operation';
    default:
      return type;
  }
}

function signalTypeIcon(type: string): string {
  switch (type) {
    case 'rate_limit_violation':
      return '⚡';
    case 'failed_auth':
      return '🔒';
    case 'bulk_operation':
      return '📦';
    default:
      return '⚠️';
  }
}

const columns: ColumnDef<AbuseSignal>[] = [
  {
    key: 'severity',
    header: 'Severity',
    sortable: true,
    render: (row) => <Label variant={severityVariant(row.severity)}>{row.severity}</Label>,
    sortValue: (row) => {
      const order: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
      return order[row.severity] ?? 4;
    },
    helpText: 'Signal severity level based on the type and volume of abuse detected.',
  },
  {
    key: 'type',
    header: 'Type',
    sortable: true,
    filterable: true,
    render: (row) => (
      <span>
        {signalTypeIcon(row.signal_type)} {signalTypeLabel(row.signal_type)}
      </span>
    ),
    sortValue: (row) => row.signal_type,
    filterValue: (row) => row.signal_type,
    helpText:
      'Category of abuse signal: rate limit violations, failed authentication, or bulk operations.',
  },
  {
    key: 'actor',
    header: 'Actor',
    sortable: true,
    filterable: true,
    render: (row) => row.actor,
    sortValue: (row) => row.actor,
    filterValue: (row) => row.actor,
    helpText: 'GitHub user or integration associated with the abuse signal.',
  },
  {
    key: 'details',
    header: 'Details',
    render: (row) => (
      <span style={{ fontSize: 12, color: 'var(--fg-muted)' }}>
        {row.event_count} events — {row.details}
      </span>
    ),
    helpText: 'Description of the detected abuse pattern and event count.',
  },
  {
    key: 'when',
    header: 'When',
    sortable: true,
    render: (row) => (
      <span style={{ color: 'var(--fg-muted)' }}>{formatRelative(row.time_window_start)}</span>
    ),
    sortValue: (row) => row.time_window_start ?? '',
    helpText: 'When the abuse pattern was first detected in the time window.',
  },
  {
    key: 'action',
    header: 'Action',
    render: (row) => (
      <span style={{ fontSize: 12, color: 'var(--fg-muted)' }}>{row.recommended_action}</span>
    ),
    helpText: 'Recommended remediation action for this abuse signal.',
  },
];

export function ApiAbuseTab() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['health', 'api-abuse'],
    queryFn: () => getApiAbuseSignals(),
    staleTime: 60_000,
  });

  const signals = data?.signals ?? [];
  const criticalCount = signals.filter((s) => s.severity === 'critical').length;
  const highCount = signals.filter((s) => s.severity === 'high').length;
  const actorsAffected = new Set(signals.map((s) => s.actor)).size;

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spinner size={28} />
      </div>
    );
  }

  return (
    <div className={styles.pane}>
      <div className={styles.metricGrid}>
        <MetricCard
          value={String(signals.length)}
          label="Total abuse signals"
          helpText="Total number of API abuse signals detected in the last 24 hours."
        />
        <MetricCard
          value={String(criticalCount)}
          label="Critical"
          accent={criticalCount > 0}
          helpText="Number of critical severity abuse signals requiring immediate attention."
        />
        <MetricCard
          value={String(highCount)}
          label="High severity"
          helpText="Number of high severity abuse signals."
        />
        <MetricCard
          value={String(actorsAffected)}
          label="Actors affected"
          helpText="Number of distinct actors involved in abuse signals."
        />
      </div>

      {isError && (
        <ErrorBanner message="Failed to load API abuse signals" onRetry={() => void refetch()} />
      )}

      {!isError && signals.length === 0 && (
        <div style={{ color: 'var(--fg-muted)', fontSize: 13, padding: 16, textAlign: 'center' }}>
          No API abuse signals detected in the last 24 hours
        </div>
      )}

      {!isError && signals.length > 0 && (
        <div className={styles.tableWrap}>
          <DataTable
            columns={columns}
            data={signals}
            rowKey={(row) =>
              `${row.signal_type}-${row.actor}-${row.time_window_start ?? 'unknown'}`
            }
            emptyMessage="No API abuse signals detected"
          />
        </div>
      )}

      <div className={styles.sourceNote}>
        ℹ️ Derived from <code className={styles.sourceCode}>rate_limit.*</code>,{' '}
        <code className={styles.sourceCode}>authentication.failure</code>, and bulk operation audit
        events
      </div>
    </div>
  );
}
