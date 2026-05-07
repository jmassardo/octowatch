import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getEventVolume } from '../../api/telemetry';
import type { TopAction } from '../../api/telemetry';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Telemetry.module.css';

const topActionColumns: ColumnDef<TopAction>[] = [
  {
    key: 'action',
    header: 'Action',
    sortable: true,
    render: (row) => row.action,
    sortValue: (row) => row.action,
  },
  {
    key: 'count',
    header: 'Count',
    sortable: true,
    render: (row) => row.count.toLocaleString(),
    sortValue: (row) => row.count,
  },
];

export function EventVolumeTab() {
  const [hours, setHours] = useState(24);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['telemetry', 'event-volume', hours],
    queryFn: () => getEventVolume('hour', hours),
    refetchInterval: 60_000,
  });

  if (isLoading) return <Spinner />;
  if (error) return <ErrorBanner message="Failed to load event volume" onRetry={() => refetch()} />;

  const volumeData = data?.volume ?? [];
  const topActions = data?.top_actions ?? [];

  const bucketSet = [...new Set(volumeData.map((v) => v.bucket_time))].sort();
  const categories = [...new Set(volumeData.map((v) => v.category))];

  const xAxisData = bucketSet.map((b) => {
    const d = new Date(b);
    return hours <= 24
      ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit' });
  });

  const series = categories.slice(0, 8).map((cat) => {
    const catData = new Map(
      volumeData.filter((v) => v.category === cat).map((v) => [v.bucket_time, v.event_count]),
    );
    return {
      name: cat,
      data: bucketSet.map((b) => catData.get(b) ?? 0),
      areaOpacity: 0.3,
    };
  });

  return (
    <div>
      <div className={styles.chartSection}>
        <div className={styles.chartHeader}>
          Event Volume
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            style={{ marginLeft: 12, fontSize: 12 }}
          >
            <option value={6}>Last 6h</option>
            <option value={12}>Last 12h</option>
            <option value={24}>Last 24h</option>
            <option value={48}>Last 48h</option>
            <option value={168}>Last 7d</option>
          </select>
        </div>
        {volumeData.length === 0 ? (
          <div className={styles.emptyState}>No event data available for this period.</div>
        ) : (
          <LineAreaChart xAxisData={xAxisData} series={series} height={280} />
        )}
      </div>

      <div className={styles.sectionTitle}>Top Event Actions</div>
      {topActions.length === 0 ? (
        <div className={styles.emptyState}>No events recorded.</div>
      ) : (
        <DataTable columns={topActionColumns} data={topActions} rowKey={(r) => r.action} />
      )}
    </div>
  );
}
