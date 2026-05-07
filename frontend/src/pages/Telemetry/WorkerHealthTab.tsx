import { useQuery } from '@tanstack/react-query';
import { getWorkerHealth } from '../../api/telemetry';
import type { ActiveWorker, HealthEvent } from '../../api/telemetry';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Telemetry.module.css';

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

function timeSince(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

const workerColumns: ColumnDef<ActiveWorker>[] = [
  {
    key: 'worker_type',
    header: 'Worker Type',
    sortable: true,
    render: (row) => row.worker_type,
    sortValue: (row) => row.worker_type,
  },
  {
    key: 'tasks_processed_24h',
    header: 'Tasks (24h)',
    sortable: true,
    render: (row) => row.tasks_processed_24h.toLocaleString(),
    sortValue: (row) => row.tasks_processed_24h,
  },
  {
    key: 'last_heartbeat',
    header: 'Last Heartbeat',
    sortable: true,
    render: (row) => (
      <span className={styles.workerStatus}>
        <span
          className={`${styles.statusDot} ${
            styles[
              Date.now() - new Date(row.last_heartbeat).getTime() < 300_000
                ? 'statusGreen'
                : 'statusRed'
            ]
          }`}
        />
        {timeSince(row.last_heartbeat)}
      </span>
    ),
    sortValue: (row) => row.last_heartbeat,
  },
  {
    key: 'first_seen_24h',
    header: 'Uptime (since)',
    sortable: true,
    render: (row) => formatTimestamp(row.first_seen_24h),
    sortValue: (row) => row.first_seen_24h,
  },
];

const healthEventColumns: ColumnDef<HealthEvent>[] = [
  {
    key: 'signal_type',
    header: 'Signal',
    sortable: true,
    render: (row) => row.signal_type,
    sortValue: (row) => row.signal_type,
  },
  {
    key: 'severity',
    header: 'Severity',
    sortable: true,
    render: (row) => (
      <span
        className={`${styles.errorSeverity} ${
          row.severity === 'critical' ? styles.severityCritical : styles.severityError
        }`}
      >
        {row.severity}
      </span>
    ),
    sortValue: (row) => row.severity,
  },
  {
    key: 'org',
    header: 'Org',
    sortable: true,
    render: (row) => row.org ?? '—',
    sortValue: (row) => row.org ?? '',
  },
  {
    key: 'occurred_at',
    header: 'Occurred',
    sortable: true,
    render: (row) => timeSince(row.occurred_at),
    sortValue: (row) => row.occurred_at,
  },
];

export function WorkerHealthTab() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['telemetry', 'worker-health'],
    queryFn: getWorkerHealth,
    refetchInterval: 30_000,
  });

  if (isLoading) return <Spinner />;
  if (error)
    return <ErrorBanner message="Failed to load worker health" onRetry={() => refetch()} />;

  const workers = data?.active_workers ?? [];
  const healthEvents = data?.health_events ?? [];

  return (
    <div>
      <div className={styles.sectionTitle}>Active Workers</div>
      {workers.length === 0 ? (
        <div className={styles.emptyState}>No active workers detected in the last 24 hours.</div>
      ) : (
        <DataTable columns={workerColumns} data={workers} rowKey={(r) => r.worker_type} />
      )}

      {healthEvents.length > 0 && (
        <>
          <div className={styles.sectionTitle} style={{ marginTop: 24 }}>
            Worker Health Events
          </div>
          <DataTable
            columns={healthEventColumns}
            data={healthEvents}
            rowKey={(r) => `${r.signal_type}-${r.occurred_at}`}
          />
        </>
      )}
    </div>
  );
}
