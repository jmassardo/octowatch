import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getRiskSummary,
  getRiskyUsers,
  getAnomalies,
  getPermissionDrift,
} from '../../api/userBehavior';
import type { RiskyUser, AnomalousUser, PermissionDriftUser } from '../../api/userBehavior';
import { PageHeader } from '../../components/common/PageHeader';
import { SkeletonCard } from '../../components/common/SkeletonCard';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { Label } from '../../components/primitives/Label';
import styles from './UserBehavior.module.css';

const RISK_LEVEL_VARIANTS: Record<string, 'danger' | 'attention' | 'success' | 'muted'> = {
  high: 'danger',
  medium: 'attention',
  low: 'success',
  none: 'muted',
};

const TIME_RANGES = [
  { value: 7, label: 'Last 7 days' },
  { value: 14, label: 'Last 14 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 60, label: 'Last 60 days' },
  { value: 90, label: 'Last 90 days' },
];

const RISK_FILTERS = [
  { value: '', label: 'All Risk Levels' },
  { value: 'high', label: 'High Risk' },
  { value: 'medium', label: 'Medium Risk' },
  { value: 'low', label: 'Low Risk' },
];

type TabId = 'risky-users' | 'anomalies' | 'permissions';

const PAGE_SIZE = 50;

export function UserBehaviorPage() {
  const [lookbackDays, setLookbackDays] = useState(30);
  const [riskFilter, setRiskFilter] = useState<string>('');
  const [activeTab, setActiveTab] = useState<TabId>('risky-users');
  const [page, setPage] = useState(1);

  // ─── Queries ──────────────────────────────────────────────────────────────

  const {
    data: summary,
    isLoading: summaryLoading,
    error: summaryError,
  } = useQuery({
    queryKey: ['user-behavior', 'risk-summary', lookbackDays],
    queryFn: () => getRiskSummary(lookbackDays),
    staleTime: 60_000,
  });

  const {
    data: riskyUsersData,
    isLoading: riskyUsersLoading,
    error: riskyUsersError,
  } = useQuery({
    queryKey: ['user-behavior', 'risky-users', lookbackDays, riskFilter, page],
    queryFn: () =>
      getRiskyUsers({
        lookback_days: lookbackDays,
        risk_level: riskFilter || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    staleTime: 30_000,
    enabled: activeTab === 'risky-users',
  });

  const {
    data: anomaliesData,
    isLoading: anomaliesLoading,
    error: anomaliesError,
  } = useQuery({
    queryKey: ['user-behavior', 'anomalies', lookbackDays],
    queryFn: () => getAnomalies({ lookback_days: lookbackDays }),
    staleTime: 60_000,
    enabled: activeTab === 'anomalies',
  });

  const {
    data: permissionData,
    isLoading: permissionLoading,
    error: permissionError,
  } = useQuery({
    queryKey: ['user-behavior', 'permission-drift', lookbackDays],
    queryFn: () => getPermissionDrift(lookbackDays),
    staleTime: 60_000,
    enabled: activeTab === 'permissions',
  });

  // ─── Table columns ────────────────────────────────────────────────────────

  const riskyUserColumns: ColumnDef<RiskyUser>[] = useMemo(
    () => [
      {
        key: 'user_login',
        header: 'User',
        sortable: true,
        filterable: true,
        render: (row) => <strong>{row.user_login}</strong>,
        sortValue: (row) => row.user_login,
        filterValue: (row) => row.user_login,
      },
      {
        key: 'risk_score',
        header: 'Risk Score',
        sortable: true,
        render: (row) => (
          <span className={styles.riskScore} data-level={row.risk_level}>
            {row.risk_score}
          </span>
        ),
        sortValue: (row) => row.risk_score,
        width: '100px',
      },
      {
        key: 'risk_level',
        header: 'Level',
        sortable: true,
        render: (row) => (
          <Label variant={RISK_LEVEL_VARIANTS[row.risk_level] ?? 'muted'}>{row.risk_level}</Label>
        ),
        sortValue: (row) => row.risk_level,
        width: '100px',
      },
      {
        key: 'signals',
        header: 'Top Signals',
        render: (row) => (
          <div className={styles.signalList}>
            {row.signals.slice(0, 3).map((s) => (
              <span key={s.action} className={styles.signalTag} title={`${s.count}x ${s.action}`}>
                {s.label} ({s.count})
              </span>
            ))}
            {row.signals.length > 3 && (
              <span className={styles.signalMore}>+{row.signals.length - 3} more</span>
            )}
          </div>
        ),
      },
      {
        key: 'orgs',
        header: 'Orgs',
        render: (row) => row.orgs.join(', '),
      },
      {
        key: 'last_risky_action_at',
        header: 'Last Signal',
        sortable: true,
        render: (row) =>
          row.last_risky_action_at ? new Date(row.last_risky_action_at).toLocaleDateString() : '—',
        sortValue: (row) => row.last_risky_action_at ?? '',
        width: '120px',
      },
    ],
    [],
  );

  const anomalyColumns: ColumnDef<AnomalousUser>[] = useMemo(
    () => [
      {
        key: 'user_login',
        header: 'User',
        sortable: true,
        filterable: true,
        render: (row) => <strong>{row.user_login}</strong>,
        sortValue: (row) => row.user_login,
        filterValue: (row) => row.user_login,
      },
      {
        key: 'activity_ratio',
        header: 'Activity Multiplier',
        sortable: true,
        render: (row) => <span className={styles.anomalyRatio}>{row.activity_ratio}x</span>,
        sortValue: (row) => row.activity_ratio,
        width: '140px',
      },
      {
        key: 'recent_event_count',
        header: 'Recent Events',
        sortable: true,
        render: (row) => row.recent_event_count.toLocaleString(),
        sortValue: (row) => row.recent_event_count,
        width: '120px',
      },
      {
        key: 'baseline_daily_avg',
        header: 'Baseline (daily avg)',
        sortable: true,
        render: (row) => row.baseline_daily_avg.toLocaleString(),
        sortValue: (row) => row.baseline_daily_avg,
        width: '140px',
      },
      {
        key: 'deviation_reasons',
        header: 'Deviation Signals',
        render: (row) => (
          <div className={styles.deviationList}>
            {row.deviation_reasons.map((reason, i) => (
              <span key={i} className={styles.deviationTag}>
                {reason}
              </span>
            ))}
          </div>
        ),
      },
      {
        key: 'recent_ips',
        header: 'Recent IPs',
        sortable: true,
        render: (row) => <span title={`Baseline: ${row.baseline_ips} IPs`}>{row.recent_ips}</span>,
        sortValue: (row) => row.recent_ips,
        width: '100px',
      },
    ],
    [],
  );

  const permissionColumns: ColumnDef<PermissionDriftUser>[] = useMemo(
    () => [
      {
        key: 'user_login',
        header: 'User',
        sortable: true,
        filterable: true,
        render: (row) => <strong>{row.user_login}</strong>,
        sortValue: (row) => row.user_login,
        filterValue: (row) => row.user_login,
      },
      {
        key: 'admin_pct',
        header: 'Admin %',
        sortable: true,
        render: (row) => `${row.admin_pct}%`,
        sortValue: (row) => row.admin_pct,
        width: '100px',
      },
      {
        key: 'admin_events',
        header: 'Admin Actions',
        sortable: true,
        render: (row) => row.admin_events.toLocaleString(),
        sortValue: (row) => row.admin_events,
        width: '120px',
      },
      {
        key: 'dev_events',
        header: 'Dev Actions',
        sortable: true,
        render: (row) => row.dev_events.toLocaleString(),
        sortValue: (row) => row.dev_events,
        width: '120px',
      },
      {
        key: 'status',
        header: 'Status',
        sortable: true,
        render: (row) => {
          const variant =
            row.status === 'review_recommended'
              ? 'attention'
              : row.status === 'low_activity'
                ? 'muted'
                : 'success';
          const label =
            row.status === 'review_recommended'
              ? 'Review'
              : row.status === 'low_activity'
                ? 'Low Activity'
                : 'Normal';
          return <Label variant={variant}>{label}</Label>;
        },
        sortValue: (row) => row.status,
        width: '120px',
      },
      {
        key: 'reason',
        header: 'Assessment',
        render: (row) => <span className={styles.assessmentText}>{row.reason}</span>,
      },
    ],
    [],
  );

  const totalPages = riskyUsersData ? Math.ceil(riskyUsersData.total / PAGE_SIZE) : 0;

  const handleTimeRangeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setLookbackDays(Number(e.target.value));
    setPage(1);
  };

  const handleRiskFilterChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setRiskFilter(e.target.value);
    setPage(1);
  };

  return (
    <div className={styles.page}>
      <PageHeader
        title="User Behavior"
        description="Security-focused behavioral analysis — risk scoring, anomaly detection, and permission hygiene"
      />

      {/* Context banner */}
      <div className={styles.contextBanner} role="note">
        <span className={styles.contextIcon} aria-hidden="true">
          🛡️
        </span>
        <div className={styles.contextText}>
          <strong>What this page shows:</strong> Security signals derived from audit log events —
          unusual patterns, risky actions, and permission misalignment. This is different from
          Developer Activity which tracks productivity metrics.
        </div>
      </div>

      {/* Filters */}
      <div className={styles.filterRow}>
        <label htmlFor="time-range-filter">Time range:</label>
        <select
          id="time-range-filter"
          className={styles.filterSelect}
          value={lookbackDays}
          onChange={handleTimeRangeChange}
        >
          {TIME_RANGES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </div>

      {/* Key metrics */}
      {summaryLoading ? (
        <div className={styles.metricsRow}>
          <SkeletonCard lines={2} />
          <SkeletonCard lines={2} />
          <SkeletonCard lines={2} />
          <SkeletonCard lines={2} />
          <SkeletonCard lines={2} />
        </div>
      ) : summaryError ? (
        <div role="alert" className={styles.errorBanner}>
          Failed to load risk summary. Ensure audit log events have been ingested.
        </div>
      ) : (
        <div className={styles.metricsRow}>
          <div className={styles.metricCard}>
            <div className={styles.metricValue} data-testid="users-with-signals">
              {summary?.total_users_with_signals ?? 0}
            </div>
            <div className={styles.metricLabel}>Users with Risk Signals</div>
            <div className={styles.metricHelp}>Users who performed security-relevant actions</div>
          </div>
          <div className={styles.metricCard} data-severity="high">
            <div className={styles.metricValue} data-testid="high-risk-count">
              {summary?.high_risk_count ?? 0}
            </div>
            <div className={styles.metricLabel}>High Risk</div>
            <div className={styles.metricHelp}>Score ≥ 15 — investigate promptly</div>
          </div>
          <div className={styles.metricCard} data-severity="medium">
            <div className={styles.metricValue} data-testid="medium-risk-count">
              {summary?.medium_risk_count ?? 0}
            </div>
            <div className={styles.metricLabel}>Medium Risk</div>
            <div className={styles.metricHelp}>Score 7–14 — worth monitoring</div>
          </div>
          <div className={styles.metricCard} data-severity="low">
            <div className={styles.metricValue} data-testid="low-risk-count">
              {summary?.low_risk_count ?? 0}
            </div>
            <div className={styles.metricLabel}>Low Risk</div>
            <div className={styles.metricHelp}>Score 3–6 — normal activity</div>
          </div>
          <div className={styles.metricCard}>
            <div className={styles.metricValue} data-testid="anomaly-count">
              {summary?.anomaly_count ?? 0}
            </div>
            <div className={styles.metricLabel}>Anomalies Detected</div>
            <div className={styles.metricHelp}>Users deviating 2x+ from baseline</div>
          </div>
        </div>
      )}

      {/* Risk categories breakdown */}
      {summary && summary.top_categories.length > 0 && (
        <div className={styles.categoriesCard}>
          <div className={styles.cardTitle}>Top Risk Categories</div>
          <div className={styles.categoryGrid}>
            {summary.top_categories.map((cat) => (
              <div key={cat.category} className={styles.categoryItem}>
                <div className={styles.categoryLabel}>{cat.label}</div>
                <div className={styles.categoryCount}>{cat.event_count} events</div>
                <div className={styles.categoryDesc}>{cat.description}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className={styles.tabBar} role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'risky-users'}
          className={`${styles.tab} ${activeTab === 'risky-users' ? styles.tabActive : ''}`}
          onClick={() => {
            setActiveTab('risky-users');
            setPage(1);
          }}
        >
          Risky Users
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'anomalies'}
          className={`${styles.tab} ${activeTab === 'anomalies' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('anomalies')}
        >
          Anomaly Detection
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'permissions'}
          className={`${styles.tab} ${activeTab === 'permissions' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('permissions')}
        >
          Permission Drift
        </button>
      </div>

      {/* Tab content */}
      <div className={styles.tabContent} role="tabpanel">
        {activeTab === 'risky-users' && (
          <>
            <div className={styles.tabDescription}>
              Users ranked by risk score based on security-sensitive actions. Higher scores indicate
              more frequent or severe risky behaviors (permission escalation, protection removals,
              credential creation spikes).
            </div>
            <div className={styles.filterRow}>
              <label htmlFor="risk-level-filter">Risk level:</label>
              <select
                id="risk-level-filter"
                className={styles.filterSelect}
                value={riskFilter}
                onChange={handleRiskFilterChange}
              >
                {RISK_FILTERS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </div>

            {riskyUsersLoading ? (
              <SkeletonCard lines={8} />
            ) : riskyUsersError ? (
              <div role="alert" className={styles.errorBanner}>
                Failed to load risky users data.
              </div>
            ) : (
              <>
                <DataTable
                  columns={riskyUserColumns}
                  data={riskyUsersData?.users ?? []}
                  rowKey={(row) => row.user_login}
                  emptyMessage="No users with risk signals detected in this time range. This is a good sign — or it may mean audit log data hasn't been ingested yet."
                />

                {totalPages > 1 && (
                  <div className={styles.pagination}>
                    <button
                      type="button"
                      className={styles.paginationBtn}
                      disabled={page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                    >
                      Previous
                    </button>
                    <span>
                      Page {page} of {totalPages}
                    </span>
                    <button
                      type="button"
                      className={styles.paginationBtn}
                      disabled={page >= totalPages}
                      onClick={() => setPage((p) => p + 1)}
                    >
                      Next
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {activeTab === 'anomalies' && (
          <>
            <div className={styles.tabDescription}>
              Users whose recent activity significantly deviates from their personal baseline. A 2x
              multiplier means the user has double their normal activity volume — investigate
              whether this is legitimate (e.g., project crunch) or suspicious.
            </div>

            {anomaliesLoading ? (
              <SkeletonCard lines={8} />
            ) : anomaliesError ? (
              <div role="alert" className={styles.errorBanner}>
                Failed to load anomaly detection data.
              </div>
            ) : (
              <DataTable
                columns={anomalyColumns}
                data={anomaliesData?.anomalies ?? []}
                rowKey={(row) => row.user_login}
                emptyMessage="No anomalous behavior detected. Users are operating within their normal baseline patterns. Requires 90+ days of data for meaningful baselines."
              />
            )}
          </>
        )}

        {activeTab === 'permissions' && (
          <>
            <div className={styles.tabDescription}>
              Users with administrative access whose actual activity doesn&apos;t justify their
              permission level. &ldquo;Review Recommended&rdquo; indicates users who primarily
              perform admin actions with little development work — consider whether they need their
              current access level.
            </div>

            {permissionLoading ? (
              <SkeletonCard lines={8} />
            ) : permissionError ? (
              <div role="alert" className={styles.errorBanner}>
                Failed to load permission drift data.
              </div>
            ) : (
              <DataTable
                columns={permissionColumns}
                data={permissionData?.users ?? []}
                rowKey={(row) => row.user_login}
                emptyMessage="No permission drift detected. All users with admin access appear to be using their permissions appropriately."
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
