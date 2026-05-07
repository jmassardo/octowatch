import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { getRuleAnalytics } from '../../api/rules';
import type { TopItem } from '../../api/rules';
import type { RuleResponse } from '../../types/detections';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { Button } from '../../components/primitives/Button';
import { DataTable } from '../../components/primitives/DataTable';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import styles from './Rules.module.css';

function formatPercent(value: number): string {
  const percentValue = value <= 1 ? value * 100 : value;
  return `${percentValue.toFixed(1)}%`;
}

function TopItemsTable({ data, emptyMessage }: { data: TopItem[]; emptyMessage: string }) {
  return (
    <DataTable
      columns={[
        { key: 'name', header: 'Name', render: (item) => item.name || '—' },
        {
          key: 'count',
          header: 'Count',
          sortable: true,
          sortValue: (item) => item.count,
          render: (item) => item.count,
        },
      ]}
      data={data}
      rowKey={(item) => `${item.name}-${item.count}`}
      emptyMessage={emptyMessage}
    />
  );
}

export function RuleAnalytics({ rule }: { rule: RuleResponse }) {
  const [days, setDays] = useState(30);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['rule-analytics', rule.id, days],
    queryFn: () => getRuleAnalytics(rule.id, days),
  });

  if (isLoading) {
    return <Spinner />;
  }

  if (isError || !data) {
    return <ErrorBanner message="Failed to load rule analytics" onRetry={() => refetch()} />;
  }

  return (
    <div className={styles.analyticsPanel}>
      <div className={styles.analyticsTimeRange}>
        <span className={styles.formLabel}>Time range</span>
        {[30, 60, 90].map((value) => (
          <Button
            key={value}
            type="button"
            size="sm"
            variant={days === value ? 'primary' : 'default'}
            onClick={() => setDays(value)}
          >
            {value}d
          </Button>
        ))}
      </div>

      <div className={styles.analyticsMetrics}>
        <MetricCard value={String(data.total_detections)} label="Total Detections" />
        <MetricCard value={data.avg_detections_per_day.toFixed(1)} label="Avg/Day" />
        <MetricCard value={formatPercent(data.false_positive_rate)} label="FP Rate" />
        <MetricCard
          value={
            data.mean_time_to_triage_hours == null ? '—' : data.mean_time_to_triage_hours.toFixed(1)
          }
          label="MTTT (hours)"
        />
      </div>

      <div className={styles.analyticsSection}>
        <div className={styles.analyticsSectionHeader}>Detection Trend</div>
        <div style={{ padding: 16 }}>
          <LineAreaChart
            title="Detections per day"
            xAxisData={data.detections_by_day.map((item) => item.date)}
            series={[
              {
                name: 'Detections',
                data: data.detections_by_day.map((item) => item.count),
                areaOpacity: 0.2,
              },
            ]}
            height={240}
          />
        </div>
      </div>

      <div className={styles.analyticsSection}>
        <div className={styles.analyticsSectionHeader}>Top Actors</div>
        <TopItemsTable data={data.top_actors} emptyMessage="No actor data available" />
      </div>

      <div className={styles.analyticsSection}>
        <div className={styles.analyticsSectionHeader}>Top Repositories</div>
        <TopItemsTable data={data.top_repos} emptyMessage="No repository data available" />
      </div>

      <div className={styles.analyticsSection}>
        <div className={styles.analyticsSectionHeader}>Top Actions</div>
        <TopItemsTable data={data.top_actions} emptyMessage="No action data available" />
      </div>
    </div>
  );
}
