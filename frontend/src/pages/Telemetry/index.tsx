import { useQuery } from '@tanstack/react-query';
import { useEnumQueryParam } from '../../hooks/useQueryParam';
import { getTelemetrySummary } from '../../api/telemetry';
import { PageHeader } from '../../components/common/PageHeader';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { StreamStatusTab } from './StreamStatusTab';
import { WorkerHealthTab } from './WorkerHealthTab';
import { EventVolumeTab } from './EventVolumeTab';
import { ErrorsTab } from './ErrorsTab';
import styles from './Telemetry.module.css';

type TelemetryTab = 'streams' | 'workers' | 'volume' | 'errors';
const TAB_KEYS: readonly TelemetryTab[] = ['streams', 'workers', 'volume', 'errors'];

function formatLastEvent(iso: string | null): string {
  if (!iso) return 'Never';
  const ms = Date.now() - new Date(iso).getTime();
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  return `${Math.floor(mins / 60)}h ago`;
}

function isStale(iso: string | null): boolean {
  if (!iso) return true;
  return Date.now() - new Date(iso).getTime() > 5 * 60 * 1000;
}

export function TelemetryPage() {
  const [activeTab, setActiveTab] = useEnumQueryParam('tab', TAB_KEYS, 'streams');

  const {
    data: summary,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['telemetry', 'summary'],
    queryFn: getTelemetrySummary,
    refetchInterval: 15_000,
  });

  const tabs: { key: TelemetryTab; label: string }[] = [
    { key: 'streams', label: 'Stream Status' },
    { key: 'workers', label: 'Worker Health' },
    { key: 'volume', label: 'Event Volume' },
    { key: 'errors', label: 'Errors & Gaps' },
  ];

  return (
    <div className={styles.page}>
      <PageHeader
        title="Ingestion Telemetry"
        description="Real-time monitoring of event ingestion pipeline health"
      />

      {isLoading && <Spinner />}
      {error && <ErrorBanner message="Failed to load telemetry" onRetry={() => refetch()} />}

      {summary && (
        <div className={styles.metricStrip}>
          <MetricCard value={String(summary.events_per_second)} label="Events/Second" />
          <MetricCard value={summary.events_today.toLocaleString()} label="Events Today" />
          <MetricCard value={String(summary.active_workers)} label="Active Workers" />
          <MetricCard value={String(summary.queue_depth)} label="Queue Depth" />
          <MetricCard
            value={formatLastEvent(summary.last_event_at)}
            label="Last Event"
            accent={isStale(summary.last_event_at)}
          />
          <MetricCard
            value={`${summary.error_rate}%`}
            label="Error Rate (1h)"
            accent={summary.error_rate > 5}
          />
        </div>
      )}

      <div className={styles.tabs}>
        {tabs.map((t) => (
          <button
            key={t.key}
            className={`${styles.tab} ${activeTab === t.key ? styles.tabActive : ''}`}
            onClick={() => setActiveTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className={styles.tabContent}>
        {activeTab === 'streams' && <StreamStatusTab />}
        {activeTab === 'workers' && <WorkerHealthTab />}
        {activeTab === 'volume' && <EventVolumeTab />}
        {activeTab === 'errors' && <ErrorsTab />}
      </div>
    </div>
  );
}
