import { useState, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTabParam } from '../../hooks/useTabParam';
import {
  getRiskSummary,
  getRiskyUsers,
  getAnomalies,
  getPermissionDrift,
} from '../../api/userBehavior';
import type { RiskyUser, AnomalousUser, PermissionDriftUser } from '../../api/userBehavior';
import { getClassificationSummary, getClassifiedUsers } from '../../api/userClassification';
import type { ClassifiedUser } from '../../api/userClassification';
import { PageHeader } from '../../components/common/PageHeader';
import { SkeletonCard } from '../../components/common/SkeletonCard';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { Drawer } from '../../components/primitives/Drawer';
import { Label } from '../../components/primitives/Label';
import styles from './UserBehavior.module.css';

const RISK_LEVEL_VARIANTS: Record<string, 'danger' | 'attention' | 'success' | 'muted'> = {
  high: 'danger',
  medium: 'attention',
  low: 'success',
  none: 'muted',
};

const PERSONA_VARIANTS: Record<string, 'danger' | 'attention' | 'success' | 'muted'> = {
  bot: 'muted',
  viewer: 'muted',
  developer: 'success',
  code_reviewer: 'success',
  product_manager: 'attention',
  admin: 'attention',
  collaborator: 'success',
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

type TabId = 'risky-users' | 'anomalies' | 'permissions' | 'personas';
const TAB_KEYS: readonly TabId[] = ['risky-users', 'anomalies', 'permissions', 'personas'];

type SelectedRow =
  | { type: 'risky'; data: RiskyUser }
  | { type: 'anomaly'; data: AnomalousUser }
  | { type: 'permission'; data: PermissionDriftUser }
  | { type: 'persona'; data: ClassifiedUser };

const PAGE_SIZE = 50;

export function UserBehaviorPage() {
  const [lookbackDays, setLookbackDays] = useState(30);
  const [riskFilter, setRiskFilter] = useState<string>('');
  const [activeTab, setActiveTab] = useTabParam('/user-behavior', TAB_KEYS, 'risky-users');
  const [page, setPage] = useState(1);
  const [selectedRow, setSelectedRow] = useState<SelectedRow | null>(null);
  const [activeChip, setActiveChip] = useState<string | null>(null);
  const [personaFilter, setPersonaFilter] = useState<string>('');
  const [personaPage, setPersonaPage] = useState(1);

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

  const {
    data: personaSummary,
    isLoading: personaSummaryLoading,
    error: personaSummaryError,
  } = useQuery({
    queryKey: ['user-behavior', 'persona-summary'],
    queryFn: () => getClassificationSummary(),
    staleTime: 120_000,
    enabled: activeTab === 'personas',
  });

  const {
    data: personaUsersData,
    isLoading: personaUsersLoading,
    error: personaUsersError,
  } = useQuery({
    queryKey: ['user-behavior', 'persona-users', personaFilter, personaPage],
    queryFn: () =>
      getClassifiedUsers({
        persona: personaFilter || undefined,
        page: personaPage,
        page_size: PAGE_SIZE,
      }),
    staleTime: 60_000,
    enabled: activeTab === 'personas',
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
        filterable: true,
        render: (row) => (
          <Label variant={RISK_LEVEL_VARIANTS[row.risk_level] ?? 'muted'}>{row.risk_level}</Label>
        ),
        sortValue: (row) => row.risk_level,
        filterValue: (row) => row.risk_level,
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
        filterable: true,
        render: (row) => row.orgs.join(', '),
        filterValue: (row) => row.orgs.join(', '),
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
        filterable: true,
        render: (row) => <span className={styles.anomalyRatio}>{row.activity_ratio}x</span>,
        sortValue: (row) => row.activity_ratio,
        filterValue: (row) => `${row.activity_ratio}x`,
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
        filterable: true,
        render: (row) => <span title={`Baseline: ${row.baseline_ips} IPs`}>{row.recent_ips}</span>,
        sortValue: (row) => row.recent_ips,
        filterValue: (row) => String(row.recent_ips),
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
        filterable: true,
        render: (row) => `${row.admin_pct}%`,
        sortValue: (row) => row.admin_pct,
        filterValue: (row) => `${row.admin_pct}%`,
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
        filterable: true,
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
        filterValue: (row) =>
          row.status === 'review_recommended'
            ? 'Review'
            : row.status === 'low_activity'
              ? 'Low Activity'
              : 'Normal',
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

  const personaColumns: ColumnDef<ClassifiedUser>[] = useMemo(
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
        key: 'persona',
        header: 'Persona',
        sortable: true,
        filterable: true,
        render: (row) => (
          <Label variant={PERSONA_VARIANTS[row.persona] ?? 'muted'}>
            {row.persona.replace(/_/g, ' ')}
          </Label>
        ),
        sortValue: (row) => row.persona,
        filterValue: (row) => row.persona.replace(/_/g, ' '),
        width: '150px',
      },
      {
        key: 'confidence_score',
        header: 'Confidence',
        sortable: true,
        render: (row) => `${Math.round(row.confidence_score * 100)}%`,
        sortValue: (row) => row.confidence_score,
        width: '100px',
      },
      {
        key: 'event_count',
        header: 'Events',
        sortable: true,
        render: (row) => row.event_count.toLocaleString(),
        sortValue: (row) => row.event_count,
        width: '100px',
      },
      {
        key: 'surfaces',
        header: 'Surfaces',
        render: (row) => (
          <div className={styles.signalList}>
            {row.surfaces.map((s) => (
              <span key={s} className={styles.signalTag}>
                {s}
              </span>
            ))}
          </div>
        ),
      },
      {
        key: 'org',
        header: 'Org',
        sortable: true,
        filterable: true,
        render: (row) => row.org,
        sortValue: (row) => row.org,
        filterValue: (row) => row.org,
        width: '120px',
      },
      {
        key: 'classified_at',
        header: 'Classified',
        sortable: true,
        render: (row) =>
          row.classified_at ? new Date(row.classified_at).toLocaleDateString() : '—',
        sortValue: (row) => row.classified_at ?? '',
        width: '110px',
      },
    ],
    [],
  );

  const totalPages = riskyUsersData ? Math.ceil(riskyUsersData.total / PAGE_SIZE) : 0;
  const totalPersonaPages = personaUsersData ? Math.ceil(personaUsersData.total / PAGE_SIZE) : 0;

  const handleTimeRangeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setLookbackDays(Number(e.target.value));
    setPage(1);
  };

  const handleRiskFilterChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setRiskFilter(e.target.value);
    setPage(1);
    setActiveChip(null);
  };

  /** Click a metric chip to filter by risk level */
  const handleChipClick = useCallback(
    (level: string) => {
      if (activeChip === level) {
        // Deselect
        setActiveChip(null);
        setRiskFilter('');
      } else {
        setActiveChip(level);
        setRiskFilter(level);
        setActiveTab('risky-users');
        setPage(1);
      }
    },
    [activeChip],
  );

  /** Click a category card to filter (navigate to risky users with that category in view) */
  const handleCategoryClick = useCallback(
    (category: string) => {
      if (activeChip === `cat:${category}`) {
        setActiveChip(null);
        setRiskFilter('');
      } else {
        setActiveChip(`cat:${category}`);
        setActiveTab('risky-users');
        setRiskFilter('');
        setPage(1);
      }
    },
    [activeChip],
  );

  /** Clear all chip-based filters */
  const handleClearChipFilter = useCallback(() => {
    setActiveChip(null);
    setRiskFilter('');
    setPage(1);
  }, []);

  /** Compute the displayed risky users: apply category filter client-side if active */
  const displayedRiskyUsers = useMemo(() => {
    const users = riskyUsersData?.users ?? [];
    if (!activeChip?.startsWith('cat:')) return users;
    const category = activeChip.slice(4);
    return users.filter((u) => u.category_breakdown.some((cb) => cb.category === category));
  }, [riskyUsersData?.users, activeChip]);

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

      {/* Key metrics — clickable chips */}
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
          <button
            type="button"
            className={`${styles.metricCard} ${styles.metricCardClickable} ${activeChip === 'high' ? styles.metricCardSelected : ''}`}
            data-severity="high"
            onClick={() => handleChipClick('high')}
            aria-pressed={activeChip === 'high'}
          >
            <div className={styles.metricValue} data-testid="high-risk-count">
              {summary?.high_risk_count ?? 0}
            </div>
            <div className={styles.metricLabel}>High Risk</div>
            <div className={styles.metricHelp}>Score ≥ 15 — investigate promptly</div>
          </button>
          <button
            type="button"
            className={`${styles.metricCard} ${styles.metricCardClickable} ${activeChip === 'medium' ? styles.metricCardSelected : ''}`}
            data-severity="medium"
            onClick={() => handleChipClick('medium')}
            aria-pressed={activeChip === 'medium'}
          >
            <div className={styles.metricValue} data-testid="medium-risk-count">
              {summary?.medium_risk_count ?? 0}
            </div>
            <div className={styles.metricLabel}>Medium Risk</div>
            <div className={styles.metricHelp}>Score 7–14 — worth monitoring</div>
          </button>
          <button
            type="button"
            className={`${styles.metricCard} ${styles.metricCardClickable} ${activeChip === 'low' ? styles.metricCardSelected : ''}`}
            data-severity="low"
            onClick={() => handleChipClick('low')}
            aria-pressed={activeChip === 'low'}
          >
            <div className={styles.metricValue} data-testid="low-risk-count">
              {summary?.low_risk_count ?? 0}
            </div>
            <div className={styles.metricLabel}>Low Risk</div>
            <div className={styles.metricHelp}>Score 3–6 — normal activity</div>
          </button>
          <div className={styles.metricCard}>
            <div className={styles.metricValue} data-testid="anomaly-count">
              {summary?.anomaly_count ?? 0}
            </div>
            <div className={styles.metricLabel}>Anomalies Detected</div>
            <div className={styles.metricHelp}>Users deviating 2x+ from baseline</div>
          </div>
        </div>
      )}

      {/* Active chip filter indicator */}
      {activeChip && (
        <div className={styles.activeFilterBanner} data-testid="active-chip-filter">
          <span className={styles.activeFilterText}>
            Filtered by:{' '}
            <strong>
              {activeChip.startsWith('cat:')
                ? activeChip.slice(4).replace(/_/g, ' ')
                : `${activeChip} risk`}
            </strong>
          </span>
          <button
            type="button"
            className={styles.clearFilterBtn}
            onClick={handleClearChipFilter}
            aria-label="Clear filter"
          >
            ✕ Clear
          </button>
        </div>
      )}

      {/* Risk categories breakdown — clickable */}
      {summary && summary.top_categories.length > 0 && (
        <div className={styles.categoriesCard}>
          <div className={styles.cardTitle}>Top Risk Categories</div>
          <div className={styles.categoryGrid}>
            {summary.top_categories.map((cat) => (
              <button
                key={cat.category}
                type="button"
                className={`${styles.categoryItem} ${styles.categoryItemClickable} ${activeChip === `cat:${cat.category}` ? styles.categoryItemSelected : ''}`}
                onClick={() => handleCategoryClick(cat.category)}
                aria-pressed={activeChip === `cat:${cat.category}`}
              >
                <div className={styles.categoryLabel}>{cat.label}</div>
                <div className={styles.categoryCount}>{cat.event_count} events</div>
                <div className={styles.categoryDesc}>{cat.description}</div>
              </button>
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
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'personas'}
          className={`${styles.tab} ${activeTab === 'personas' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('personas')}
        >
          Personas
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
                  data={displayedRiskyUsers}
                  rowKey={(row) => row.user_login}
                  onRowClick={(row) => setSelectedRow({ type: 'risky', data: row })}
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
                onRowClick={(row) => setSelectedRow({ type: 'anomaly', data: row })}
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
                onRowClick={(row) => setSelectedRow({ type: 'permission', data: row })}
                emptyMessage="No permission drift detected. All users with admin access appear to be using their permissions appropriately."
              />
            )}
          </>
        )}

        {activeTab === 'personas' && (
          <>
            <div className={styles.tabDescription}>
              Users classified by their GitHub usage patterns. Persona assignment is based on audit
              log activity over the configured analysis window (default: 90 days).
            </div>

            {/* Persona summary cards */}
            {personaSummaryLoading ? (
              <SkeletonCard lines={3} />
            ) : personaSummaryError ? (
              <div role="alert" className={styles.errorBanner}>
                Failed to load persona summary. Ensure the classification engine has run at least
                once.
              </div>
            ) : (
              personaSummary && (
                <div className={styles.metricsRow}>
                  <div className={styles.metricCard}>
                    <div className={styles.metricValue}>{personaSummary.total_users}</div>
                    <div className={styles.metricLabel}>Total Classified</div>
                  </div>
                  <div className={styles.metricCard} data-severity="high">
                    <div className={styles.metricValue}>
                      {personaSummary.dormant_count} ({personaSummary.dormant_pct}%)
                    </div>
                    <div className={styles.metricLabel}>Truly Dormant</div>
                    <div className={styles.metricHelp}>Zero activity in analysis window</div>
                  </div>
                  <div className={styles.metricCard} data-severity="low">
                    <div className={styles.metricValue}>
                      {personaSummary.power_user_count} ({personaSummary.power_user_pct}%)
                    </div>
                    <div className={styles.metricLabel}>Power Users</div>
                    <div className={styles.metricHelp}>Active across 3+ surfaces</div>
                  </div>
                  {personaSummary.personas.slice(0, 4).map((p) => (
                    <button
                      key={p.persona}
                      type="button"
                      className={`${styles.metricCard} ${styles.metricCardClickable} ${personaFilter === p.persona ? styles.metricCardSelected : ''}`}
                      onClick={() => {
                        setPersonaFilter(personaFilter === p.persona ? '' : p.persona);
                        setPersonaPage(1);
                      }}
                      aria-pressed={personaFilter === p.persona}
                    >
                      <div className={styles.metricValue}>{p.user_count}</div>
                      <div className={styles.metricLabel}>{p.persona.replace(/_/g, ' ')}</div>
                      <div className={styles.metricHelp}>
                        Avg confidence: {Math.round(p.avg_confidence * 100)}%
                      </div>
                    </button>
                  ))}
                </div>
              )
            )}

            {/* Persona filter */}
            {personaSummary && (
              <div className={styles.filterRow}>
                <label htmlFor="persona-filter">Persona:</label>
                <select
                  id="persona-filter"
                  className={styles.filterSelect}
                  value={personaFilter}
                  onChange={(e) => {
                    setPersonaFilter(e.target.value);
                    setPersonaPage(1);
                  }}
                >
                  <option value="">All Personas</option>
                  {personaSummary.personas.map((p) => (
                    <option key={p.persona} value={p.persona}>
                      {p.persona.replace(/_/g, ' ')} ({p.user_count})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* User table */}
            {personaUsersLoading ? (
              <SkeletonCard lines={8} />
            ) : personaUsersError ? (
              <div role="alert" className={styles.errorBanner}>
                Failed to load classified users.
              </div>
            ) : (
              <>
                <DataTable
                  columns={personaColumns}
                  data={personaUsersData?.users ?? []}
                  rowKey={(row) => `${row.user_login}-${row.org}`}
                  onRowClick={(row) => setSelectedRow({ type: 'persona', data: row })}
                  emptyMessage="No users classified yet. The classification engine runs nightly — or trigger a manual run from the admin settings."
                />

                {totalPersonaPages > 1 && (
                  <div className={styles.pagination}>
                    <button
                      type="button"
                      className={styles.paginationBtn}
                      disabled={personaPage <= 1}
                      onClick={() => setPersonaPage((p) => Math.max(1, p - 1))}
                    >
                      Previous
                    </button>
                    <span>
                      Page {personaPage} of {totalPersonaPages}
                    </span>
                    <button
                      type="button"
                      className={styles.paginationBtn}
                      disabled={personaPage >= totalPersonaPages}
                      onClick={() => setPersonaPage((p) => p + 1)}
                    >
                      Next
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>

      {/* Detail Drawer */}
      <Drawer
        open={!!selectedRow}
        onClose={() => setSelectedRow(null)}
        title={selectedRow ? `${selectedRow.data.user_login} — Details` : ''}
      >
        {selectedRow && <DrawerContent selected={selectedRow} />}
      </Drawer>
    </div>
  );
}

// ─── Drawer Content ─────────────────────────────────────────────────────────

function DrawerContent({ selected }: { selected: SelectedRow }) {
  const userLogin = selected.data.user_login;
  const githubUrl = `https://github.com/${userLogin}`;

  return (
    <div className={styles.drawerBody}>
      {/* User header */}
      <div className={styles.drawerUserHeader}>
        <img
          src={`https://github.com/${userLogin}.png?size=64`}
          alt={`${userLogin} avatar`}
          className={styles.drawerAvatar}
          width={48}
          height={48}
        />
        <div>
          <div className={styles.drawerUserName}>@{userLogin}</div>
          <a
            href={githubUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.drawerGhLink}
          >
            View on GitHub ↗
          </a>
        </div>
      </div>

      {selected.type === 'risky' && <RiskyUserDetails user={selected.data} />}
      {selected.type === 'anomaly' && <AnomalyDetails user={selected.data} />}
      {selected.type === 'permission' && <PermissionDriftDetails user={selected.data} />}
      {selected.type === 'persona' && <PersonaDetails user={selected.data} />}
    </div>
  );
}

function RiskyUserDetails({ user }: { user: RiskyUser }) {
  return (
    <>
      {/* Risk score breakdown */}
      <section className={styles.drawerSection}>
        <h3 className={styles.drawerSectionTitle}>Risk Assessment</h3>
        <div className={styles.drawerMetricRow}>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Score</span>
            <span className={styles.drawerMetricValue} data-level={user.risk_level}>
              {user.risk_score}
            </span>
          </div>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Level</span>
            <Label variant={RISK_LEVEL_VARIANTS[user.risk_level] ?? 'muted'}>
              {user.risk_level}
            </Label>
          </div>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Last Signal</span>
            <span>
              {user.last_risky_action_at
                ? new Date(user.last_risky_action_at).toLocaleDateString()
                : '—'}
            </span>
          </div>
        </div>
      </section>

      {/* Signal timeline */}
      <section className={styles.drawerSection}>
        <h3 className={styles.drawerSectionTitle}>Signal Timeline</h3>
        <div className={styles.drawerTimeline}>
          {user.signals.map((signal) => (
            <div key={signal.action} className={styles.drawerTimelineItem}>
              <div className={styles.drawerTimelineHeader}>
                <span className={styles.drawerTimelineLabel}>{signal.label}</span>
                <span className={styles.drawerTimelineCount}>×{signal.count}</span>
              </div>
              <div className={styles.drawerTimelineMeta}>
                Weight: {signal.weight} · Category: {signal.category.replace(/_/g, ' ')}
                {signal.last_seen && (
                  <> · Last: {new Date(signal.last_seen).toLocaleDateString()}</>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Org memberships */}
      <section className={styles.drawerSection}>
        <h3 className={styles.drawerSectionTitle}>Org Memberships</h3>
        <div className={styles.drawerTagList}>
          {user.orgs.map((org) => (
            <span key={org} className={styles.drawerTag}>
              {org}
            </span>
          ))}
        </div>
      </section>

      {/* Recommended actions */}
      <section className={styles.drawerSection}>
        <h3 className={styles.drawerSectionTitle}>Recommended Actions</h3>
        <ul className={styles.drawerActionList}>
          {user.risk_level === 'high' && (
            <>
              <li>Review recent audit log entries for this user</li>
              <li>Verify branch protection changes are intentional</li>
              <li>Consider rotating any newly-created credentials</li>
            </>
          )}
          {user.risk_level === 'medium' && (
            <>
              <li>Monitor user activity over the next few days</li>
              <li>Verify permission changes were authorized</li>
            </>
          )}
          {user.risk_level === 'low' && (
            <li>No immediate action required — continue baseline monitoring</li>
          )}
        </ul>
      </section>
    </>
  );
}

function AnomalyDetails({ user }: { user: AnomalousUser }) {
  return (
    <>
      {/* Activity chart (baseline vs actual) */}
      <section className={styles.drawerSection}>
        <h3 className={styles.drawerSectionTitle}>Activity Comparison</h3>
        <div className={styles.drawerBarChart}>
          <div className={styles.drawerBarRow}>
            <span className={styles.drawerBarLabel}>Baseline (daily avg)</span>
            <div className={styles.drawerBarTrack}>
              <div
                className={styles.drawerBarFill}
                data-variant="baseline"
                style={{
                  width: `${Math.min(100, (user.baseline_daily_avg / user.recent_event_count) * 100)}%`,
                }}
              />
            </div>
            <span className={styles.drawerBarValue}>{user.baseline_daily_avg}</span>
          </div>
          <div className={styles.drawerBarRow}>
            <span className={styles.drawerBarLabel}>Recent events</span>
            <div className={styles.drawerBarTrack}>
              <div
                className={styles.drawerBarFill}
                data-variant="actual"
                style={{ width: '100%' }}
              />
            </div>
            <span className={styles.drawerBarValue}>
              {user.recent_event_count.toLocaleString()}
            </span>
          </div>
        </div>
        <div className={styles.drawerHighlight}>
          Activity is <strong>{user.activity_ratio}x</strong> above baseline
        </div>
      </section>

      {/* Deviation details */}
      <section className={styles.drawerSection}>
        <h3 className={styles.drawerSectionTitle}>Deviation Signals</h3>
        <ul className={styles.drawerActionList}>
          {user.deviation_reasons.map((reason, i) => (
            <li key={i}>{reason}</li>
          ))}
        </ul>
      </section>

      {/* IP history */}
      <section className={styles.drawerSection}>
        <h3 className={styles.drawerSectionTitle}>IP Address History</h3>
        <div className={styles.drawerMetricRow}>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Recent IPs</span>
            <span className={styles.drawerMetricValue}>{user.recent_ips}</span>
          </div>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Baseline IPs</span>
            <span className={styles.drawerMetricValue}>{user.baseline_ips}</span>
          </div>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Action Types (recent)</span>
            <span className={styles.drawerMetricValue}>{user.recent_action_types}</span>
          </div>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Action Types (baseline)</span>
            <span className={styles.drawerMetricValue}>{user.baseline_action_types}</span>
          </div>
        </div>
      </section>
    </>
  );
}

function PermissionDriftDetails({ user }: { user: PermissionDriftUser }) {
  const statusLabel =
    user.status === 'review_recommended'
      ? 'Review Recommended'
      : user.status === 'low_activity'
        ? 'Low Activity'
        : 'Normal';
  const statusVariant =
    user.status === 'review_recommended'
      ? 'attention'
      : user.status === 'low_activity'
        ? 'muted'
        : 'success';

  return (
    <>
      {/* Status assessment */}
      <section className={styles.drawerSection}>
        <h3 className={styles.drawerSectionTitle}>Status Assessment</h3>
        <div className={styles.drawerMetricRow}>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Status</span>
            <Label variant={statusVariant as 'attention' | 'muted' | 'success'}>
              {statusLabel}
            </Label>
          </div>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Admin %</span>
            <span className={styles.drawerMetricValue}>{user.admin_pct}%</span>
          </div>
        </div>
        <p className={styles.drawerAssessment}>{user.reason}</p>
      </section>

      {/* Admin action timeline */}
      <section className={styles.drawerSection}>
        <h3 className={styles.drawerSectionTitle}>Activity Breakdown</h3>
        <div className={styles.drawerBarChart}>
          <div className={styles.drawerBarRow}>
            <span className={styles.drawerBarLabel}>Admin actions</span>
            <div className={styles.drawerBarTrack}>
              <div
                className={styles.drawerBarFill}
                data-variant="actual"
                style={{
                  width: `${user.total_events > 0 ? (user.admin_events / user.total_events) * 100 : 0}%`,
                }}
              />
            </div>
            <span className={styles.drawerBarValue}>{user.admin_events}</span>
          </div>
          <div className={styles.drawerBarRow}>
            <span className={styles.drawerBarLabel}>Dev actions</span>
            <div className={styles.drawerBarTrack}>
              <div
                className={styles.drawerBarFill}
                data-variant="baseline"
                style={{
                  width: `${user.total_events > 0 ? (user.dev_events / user.total_events) * 100 : 0}%`,
                }}
              />
            </div>
            <span className={styles.drawerBarValue}>{user.dev_events}</span>
          </div>
        </div>
      </section>

      {/* Permission change history */}
      <section className={styles.drawerSection}>
        <h3 className={styles.drawerSectionTitle}>Summary</h3>
        <div className={styles.drawerMetricRow}>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Total Events</span>
            <span className={styles.drawerMetricValue}>{user.total_events}</span>
          </div>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Last Active</span>
            <span>{user.last_active ? new Date(user.last_active).toLocaleDateString() : '—'}</span>
          </div>
        </div>
      </section>
    </>
  );
}

function PersonaDetails({ user }: { user: ClassifiedUser }) {
  return (
    <>
      {/* Classification info */}
      <section className={styles.drawerSection}>
        <h3 className={styles.drawerSectionTitle}>Classification</h3>
        <div className={styles.drawerMetricRow}>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Persona</span>
            <Label variant={PERSONA_VARIANTS[user.persona] ?? 'muted'}>
              {user.persona.replace(/_/g, ' ')}
            </Label>
          </div>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Confidence</span>
            <span className={styles.drawerMetricValue}>
              {Math.round(user.confidence_score * 100)}%
            </span>
          </div>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Analysis Window</span>
            <span>{user.analysis_window_days} days</span>
          </div>
        </div>
      </section>

      {/* Activity summary */}
      <section className={styles.drawerSection}>
        <h3 className={styles.drawerSectionTitle}>Activity</h3>
        <div className={styles.drawerMetricRow}>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Total Events</span>
            <span className={styles.drawerMetricValue}>{user.event_count.toLocaleString()}</span>
          </div>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Org</span>
            <span>{user.org}</span>
          </div>
          <div className={styles.drawerMetric}>
            <span className={styles.drawerMetricLabel}>Classified</span>
            <span>
              {user.classified_at ? new Date(user.classified_at).toLocaleDateString() : '—'}
            </span>
          </div>
        </div>
      </section>

      {/* Surfaces */}
      <section className={styles.drawerSection}>
        <h3 className={styles.drawerSectionTitle}>Active Surfaces</h3>
        <div className={styles.drawerTagList}>
          {user.surfaces.length > 0 ? (
            user.surfaces.map((surface) => (
              <span key={surface} className={styles.drawerTag}>
                {surface}
              </span>
            ))
          ) : (
            <span className={styles.drawerMuted}>No active surfaces detected</span>
          )}
        </div>
      </section>
    </>
  );
}
