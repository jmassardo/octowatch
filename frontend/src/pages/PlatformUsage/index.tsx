import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import { useOrg } from '../../hooks/useOrg';
import { PageHeader } from '../../components/common/PageHeader';
import { SkeletonCard } from '../../components/common/SkeletonCard';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { Label } from '../../components/primitives/Label';
import {
  fetchUsageSummary,
  fetchUsageTrends,
  fetchTopConsumers,
  fetchAnomalies,
} from '../../api/platformUsage';
import type { FeatureSummary, Consumer, Anomaly } from '../../api/platformUsage';

type TabId = 'overview' | 'actions' | 'copilot' | 'security' | 'trends' | 'anomalies';

const TABS: readonly { id: TabId; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'actions', label: 'Actions' },
  { id: 'copilot', label: 'Copilot' },
  { id: 'security', label: 'Security' },
  { id: 'trends', label: 'Trends' },
  { id: 'anomalies', label: 'Anomalies' },
];

const SEVERITY_VARIANTS: Record<string, 'danger' | 'attention' | 'success' | 'muted'> = {
  critical: 'danger',
  high: 'danger',
  medium: 'attention',
  low: 'success',
  info: 'muted',
};

const TIME_RANGES = [
  { value: 7, label: 'Last 7 days' },
  { value: 14, label: 'Last 14 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 60, label: 'Last 60 days' },
  { value: 90, label: 'Last 90 days' },
];

function formatNumber(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

export function PlatformUsagePage() {
  const { selectedOrg } = useOrg();
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [days, setDays] = useState(30);

  // ─── Queries ──────────────────────────────────────────────────────────────

  const {
    data: summaryData,
    isLoading: summaryLoading,
    error: summaryError,
  } = useQuery({
    queryKey: ['platform-usage', 'summary', selectedOrg, days],
    queryFn: () => fetchUsageSummary({ org: selectedOrg || undefined, days }),
    staleTime: 60_000,
  });

  const {
    data: trendsData,
    isLoading: trendsLoading,
    error: trendsError,
  } = useQuery({
    queryKey: ['platform-usage', 'trends', selectedOrg, days],
    queryFn: () => fetchUsageTrends({ org: selectedOrg || undefined, days }),
    staleTime: 60_000,
    enabled: activeTab === 'trends' || activeTab === 'overview',
  });

  const {
    data: actionsConsumers,
    isLoading: actionsLoading,
    error: actionsError,
  } = useQuery({
    queryKey: ['platform-usage', 'top-consumers', 'actions', selectedOrg, days],
    queryFn: () =>
      fetchTopConsumers({ feature_area: 'actions', org: selectedOrg || undefined, days }),
    staleTime: 60_000,
    enabled: activeTab === 'actions' || activeTab === 'overview',
  });

  const {
    data: copilotConsumers,
    isLoading: copilotLoading,
    error: copilotError,
  } = useQuery({
    queryKey: ['platform-usage', 'top-consumers', 'copilot', selectedOrg, days],
    queryFn: () =>
      fetchTopConsumers({ feature_area: 'copilot', org: selectedOrg || undefined, days }),
    staleTime: 60_000,
    enabled: activeTab === 'copilot',
  });

  const {
    data: anomaliesData,
    isLoading: anomaliesLoading,
    error: anomaliesError,
  } = useQuery({
    queryKey: ['platform-usage', 'anomalies', selectedOrg, days],
    queryFn: () => fetchAnomalies({ org: selectedOrg || undefined, days, limit: 50 }),
    staleTime: 60_000,
    enabled: activeTab === 'anomalies',
  });

  // ─── Table columns ────────────────────────────────────────────────────────

  const consumerColumns: ColumnDef<Consumer>[] = useMemo(
    () => [
      {
        key: 'actor_login',
        header: 'User',
        sortable: true,
        filterable: true,
        render: (row) => <strong>{row.actor_login}</strong>,
        sortValue: (row) => row.actor_login,
        filterValue: (row) => row.actor_login,
      },
      {
        key: 'org_slug',
        header: 'Org',
        sortable: true,
        filterable: true,
        render: (row) => row.org_slug,
        sortValue: (row) => row.org_slug,
        filterValue: (row) => row.org_slug,
        width: '120px',
      },
      {
        key: 'total_actions_minutes',
        header: 'Actions (min)',
        sortable: true,
        render: (row) => formatNumber(row.total_actions_minutes),
        sortValue: (row) => row.total_actions_minutes,
        width: '120px',
      },
      {
        key: 'total_actions_runs',
        header: 'Runs',
        sortable: true,
        render: (row) => formatNumber(row.total_actions_runs),
        sortValue: (row) => row.total_actions_runs,
        width: '100px',
      },
      {
        key: 'total_copilot_credits',
        header: 'Copilot Credits',
        sortable: true,
        render: (row) => formatNumber(row.total_copilot_credits),
        sortValue: (row) => row.total_copilot_credits,
        width: '130px',
      },
      {
        key: 'active_days',
        header: 'Active Days',
        sortable: true,
        render: (row) => row.active_days,
        sortValue: (row) => row.active_days,
        width: '100px',
      },
    ],
    [],
  );

  const anomalyColumns: ColumnDef<Anomaly>[] = useMemo(
    () => [
      {
        key: 'triggered_at',
        header: 'Triggered',
        sortable: true,
        render: (row) => new Date(row.triggered_at).toLocaleString(),
        sortValue: (row) => row.triggered_at,
        width: '180px',
      },
      {
        key: 'severity',
        header: 'Severity',
        sortable: true,
        filterable: true,
        render: (row) => (
          <Label variant={SEVERITY_VARIANTS[row.severity] ?? 'muted'}>{row.severity}</Label>
        ),
        sortValue: (row) => row.severity,
        filterValue: (row) => row.severity,
        width: '100px',
      },
      {
        key: 'actor',
        header: 'Actor',
        sortable: true,
        filterable: true,
        render: (row) => <strong>{row.actor}</strong>,
        sortValue: (row) => row.actor,
        filterValue: (row) => row.actor,
      },
      {
        key: 'rule_name',
        header: 'Rule',
        sortable: true,
        filterable: true,
        render: (row) => row.rule_name,
        sortValue: (row) => row.rule_name,
        filterValue: (row) => row.rule_name,
      },
      {
        key: 'category',
        header: 'Category',
        sortable: true,
        filterable: true,
        render: (row) => row.category,
        sortValue: (row) => row.category,
        filterValue: (row) => row.category,
        width: '130px',
      },
      {
        key: 'confidence_score',
        header: 'Confidence',
        sortable: true,
        render: (row) => `${Math.round(row.confidence_score * 100)}%`,
        sortValue: (row) => row.confidence_score,
        width: '100px',
      },
    ],
    [],
  );

  // ─── Chart options ────────────────────────────────────────────────────────

  const trendsChartOption = useMemo(() => {
    if (!trendsData?.trends.length) return null;

    const dates = [...new Set(trendsData.trends.map((t) => t.date))].sort();
    const featureAreas = [...new Set(trendsData.trends.map((t) => t.feature_area))];

    const series = featureAreas.map((area) => {
      const areaData = trendsData.trends.filter((t) => t.feature_area === area);
      const dataMap = new Map(areaData.map((t) => [t.date, t.unique_actors]));
      return {
        name: area,
        type: 'line' as const,
        smooth: true,
        data: dates.map((d) => dataMap.get(d) ?? 0),
      };
    });

    return {
      tooltip: { trigger: 'axis' as const },
      legend: { data: featureAreas, bottom: 0 },
      grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
      xAxis: { type: 'category' as const, data: dates },
      yAxis: { type: 'value' as const, name: 'Unique Actors' },
      series,
    };
  }, [trendsData]);

  // ─── Helpers ──────────────────────────────────────────────────────────────

  function getFeatureMetric(features: FeatureSummary[], area: string): FeatureSummary | undefined {
    return features.find((f) => f.feature_area === area);
  }

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div>
      <PageHeader
        title="Platform Usage"
        description="Monitor platform resource consumption across Actions, Copilot, GHAS, Git, and Packages."
      />

      {/* Time range selector */}
      <div style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <label htmlFor="usage-time-range">Time range:</label>
        <select
          id="usage-time-range"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          style={{ padding: '0.25rem 0.5rem' }}
        >
          {TIME_RANGES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </div>

      {/* Tabs */}
      <div role="tablist" style={{ display: 'flex', gap: '0.25rem', marginBottom: '1.5rem' }}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '0.5rem 1rem',
              border: 'none',
              borderBottom:
                activeTab === tab.id ? '2px solid var(--accent)' : '2px solid transparent',
              background: 'none',
              cursor: 'pointer',
              fontWeight: activeTab === tab.id ? 600 : 400,
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div role="tabpanel">
        {/* ─── Overview Tab ─────────────────────────────────────────────────── */}
        {activeTab === 'overview' && (
          <>
            {summaryLoading ? (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                  gap: '1rem',
                }}
              >
                <SkeletonCard lines={2} />
                <SkeletonCard lines={2} />
                <SkeletonCard lines={2} />
                <SkeletonCard lines={2} />
                <SkeletonCard lines={2} />
              </div>
            ) : summaryError ? (
              <div role="alert" style={{ color: 'var(--danger)', padding: '1rem' }}>
                Failed to load usage summary. Ensure platform usage data has been ingested.
              </div>
            ) : (
              <>
                <div
                  data-testid="feature-summary-cards"
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                    gap: '1rem',
                    marginBottom: '2rem',
                  }}
                >
                  {summaryData?.features.map((feature) => (
                    <div
                      key={feature.feature_area}
                      data-testid={`feature-card-${feature.feature_area}`}
                      style={{
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        padding: '1.25rem',
                        background: 'var(--surface)',
                      }}
                    >
                      <div
                        style={{
                          fontSize: '0.75rem',
                          textTransform: 'uppercase',
                          color: 'var(--text-secondary)',
                          marginBottom: '0.5rem',
                        }}
                      >
                        {feature.feature_area}
                      </div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>
                        {feature.unique_actors}
                      </div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                        unique actors · {feature.active_days} active days
                      </div>
                    </div>
                  ))}
                </div>

                {/* Trends mini-chart */}
                {trendsLoading ? (
                  <SkeletonCard lines={4} />
                ) : trendsChartOption ? (
                  <div
                    style={{
                      border: '1px solid var(--border)',
                      borderRadius: '8px',
                      padding: '1rem',
                      background: 'var(--surface)',
                    }}
                  >
                    <h3 style={{ margin: '0 0 0.5rem' }}>Daily Activity Trends</h3>
                    <ReactECharts option={trendsChartOption} style={{ height: 300 }} />
                  </div>
                ) : null}
              </>
            )}
          </>
        )}

        {/* ─── Actions Tab ──────────────────────────────────────────────────── */}
        {activeTab === 'actions' && (
          <>
            {summaryLoading ? (
              <SkeletonCard lines={3} />
            ) : summaryError ? (
              <div role="alert" style={{ color: 'var(--danger)', padding: '1rem' }}>
                Failed to load Actions metrics.
              </div>
            ) : (
              (() => {
                const actions = getFeatureMetric(summaryData?.features ?? [], 'actions');
                return actions ? (
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
                      gap: '1rem',
                      marginBottom: '1.5rem',
                    }}
                  >
                    <div
                      style={{
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        padding: '1rem',
                        background: 'var(--surface)',
                      }}
                    >
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        Total Minutes
                      </div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>
                        {formatNumber(actions.total_actions_minutes)}
                      </div>
                    </div>
                    <div
                      style={{
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        padding: '1rem',
                        background: 'var(--surface)',
                      }}
                    >
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        Total Runs
                      </div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>
                        {formatNumber(actions.total_actions_runs)}
                      </div>
                    </div>
                    <div
                      style={{
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        padding: '1rem',
                        background: 'var(--surface)',
                      }}
                    >
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        Unique Actors
                      </div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>
                        {actions.unique_actors}
                      </div>
                    </div>
                  </div>
                ) : null;
              })()
            )}

            <h3>Top Actions Consumers</h3>
            {actionsLoading ? (
              <SkeletonCard lines={6} />
            ) : actionsError ? (
              <div role="alert" style={{ color: 'var(--danger)', padding: '1rem' }}>
                Failed to load top consumers.
              </div>
            ) : (
              <DataTable
                columns={consumerColumns}
                data={actionsConsumers?.consumers ?? []}
                rowKey={(row) => `${row.actor_login}-${row.org_slug}`}
                emptyMessage="No Actions consumption data available for this period."
              />
            )}
          </>
        )}

        {/* ─── Copilot Tab ──────────────────────────────────────────────────── */}
        {activeTab === 'copilot' && (
          <>
            {summaryLoading ? (
              <SkeletonCard lines={3} />
            ) : summaryError ? (
              <div role="alert" style={{ color: 'var(--danger)', padding: '1rem' }}>
                Failed to load Copilot metrics.
              </div>
            ) : (
              (() => {
                const copilot = getFeatureMetric(summaryData?.features ?? [], 'copilot');
                return copilot ? (
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
                      gap: '1rem',
                      marginBottom: '1.5rem',
                    }}
                  >
                    <div
                      style={{
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        padding: '1rem',
                        background: 'var(--surface)',
                      }}
                    >
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        Suggestions
                      </div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>
                        {formatNumber(copilot.total_copilot_suggestions)}
                      </div>
                    </div>
                    <div
                      style={{
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        padding: '1rem',
                        background: 'var(--surface)',
                      }}
                    >
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        Acceptances
                      </div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>
                        {formatNumber(copilot.total_copilot_acceptances)}
                      </div>
                    </div>
                    <div
                      style={{
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        padding: '1rem',
                        background: 'var(--surface)',
                      }}
                    >
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        Credits Used
                      </div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>
                        {formatNumber(copilot.total_copilot_credits)}
                      </div>
                    </div>
                    <div
                      style={{
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        padding: '1rem',
                        background: 'var(--surface)',
                      }}
                    >
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        Unique Actors
                      </div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>
                        {copilot.unique_actors}
                      </div>
                    </div>
                  </div>
                ) : null;
              })()
            )}

            <h3>Top Copilot Consumers</h3>
            {copilotLoading ? (
              <SkeletonCard lines={6} />
            ) : copilotError ? (
              <div role="alert" style={{ color: 'var(--danger)', padding: '1rem' }}>
                Failed to load Copilot consumers.
              </div>
            ) : (
              <DataTable
                columns={consumerColumns}
                data={copilotConsumers?.consumers ?? []}
                rowKey={(row) => `${row.actor_login}-${row.org_slug}`}
                emptyMessage="No Copilot consumption data available for this period."
              />
            )}
          </>
        )}

        {/* ─── Security Tab ─────────────────────────────────────────────────── */}
        {activeTab === 'security' && (
          <>
            {summaryLoading ? (
              <SkeletonCard lines={3} />
            ) : summaryError ? (
              <div role="alert" style={{ color: 'var(--danger)', padding: '1rem' }}>
                Failed to load Security metrics.
              </div>
            ) : (
              (() => {
                const ghas = getFeatureMetric(summaryData?.features ?? [], 'ghas');
                return ghas ? (
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
                      gap: '1rem',
                      marginBottom: '1.5rem',
                    }}
                  >
                    <div
                      style={{
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        padding: '1rem',
                        background: 'var(--surface)',
                      }}
                    >
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        Unique Actors
                      </div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>
                        {ghas.unique_actors}
                      </div>
                    </div>
                    <div
                      style={{
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        padding: '1rem',
                        background: 'var(--surface)',
                      }}
                    >
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        Active Days
                      </div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{ghas.active_days}</div>
                    </div>
                  </div>
                ) : (
                  <div
                    style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}
                  >
                    No GHAS/Security data available for this period.
                  </div>
                );
              })()
            )}
          </>
        )}

        {/* ─── Trends Tab ───────────────────────────────────────────────────── */}
        {activeTab === 'trends' && (
          <>
            {trendsLoading ? (
              <SkeletonCard lines={6} />
            ) : trendsError ? (
              <div role="alert" style={{ color: 'var(--danger)', padding: '1rem' }}>
                Failed to load trend data.
              </div>
            ) : trendsChartOption ? (
              <div
                style={{
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  padding: '1rem',
                  background: 'var(--surface)',
                }}
              >
                <h3 style={{ margin: '0 0 0.5rem' }}>Daily Usage Trends</h3>
                <ReactECharts option={trendsChartOption} style={{ height: 400 }} />
              </div>
            ) : (
              <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                No trend data available for this period.
              </div>
            )}
          </>
        )}

        {/* ─── Anomalies Tab ────────────────────────────────────────────────── */}
        {activeTab === 'anomalies' && (
          <>
            {anomaliesLoading ? (
              <SkeletonCard lines={8} />
            ) : anomaliesError ? (
              <div role="alert" style={{ color: 'var(--danger)', padding: '1rem' }}>
                Failed to load anomaly detections.
              </div>
            ) : (
              <DataTable
                columns={anomalyColumns}
                data={anomaliesData?.anomalies ?? []}
                rowKey={(row) => String(row.id)}
                emptyMessage="No anomalies detected in this period."
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
