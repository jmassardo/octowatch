import { useState, useMemo, useRef, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { Drawer } from '../../components/primitives/Drawer';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SkeletonCard } from '../../components/common/SkeletonCard';
import { SkeletonChart } from '../../components/common/SkeletonChart';
import { Label } from '../../components/primitives/Label';
import { Pagination } from '../../components/primitives/Pagination';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { BarChart } from '../../components/charts/BarChart';
import {
  listSecretAlerts,
  getSecretAlertSummary,
  getSecretAlertTrends,
  getSecretAlertAuditTrail,
  getPushProtectionStats,
  type SecretAlertItem,
  type AuditEvent,
} from '../../api/secretScanning';
import { formatRelativeShort } from '../../utils/dates';
import styles from './AdvancedSecurity.module.css';

const PAGE_SIZE = 50;

/* ── Helpers ── */

function stateVariant(state: string) {
  if (state === 'open') return 'attention' as const;
  if (state === 'resolved') return 'success' as const;
  return 'muted' as const;
}

function validityVariant(validity: string | null) {
  if (validity === 'active') return 'danger' as const;
  if (validity === 'inactive') return 'success' as const;
  return 'muted' as const;
}

function formatMttr(hours: number): string {
  if (hours < 1) return '<1h';
  if (hours < 24) return `${Math.round(hours)}h`;
  const days = Math.round(hours / 24);
  return `${days}d`;
}

/* ── Audit Trail Drawer Section ── */

function AuditTrailSection({ alertId }: { alertId: number }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['secret-alert-audit-trail', alertId],
    queryFn: () => getSecretAlertAuditTrail(alertId),
    staleTime: 60_000,
  });

  if (isLoading) return <Spinner />;
  if (isError) return <div className={styles.drawerValue}>Failed to load audit trail</div>;
  if (!data || data.events.length === 0) {
    return <div className={styles.drawerValue}>No related audit events found</div>;
  }

  return (
    <div>
      {data.events.map((evt: AuditEvent) => (
        <div key={evt.id} className={styles.drawerField}>
          <div className={styles.drawerLabel}>
            {evt.action} — {evt.actor}
          </div>
          <div className={styles.drawerValue}>{formatRelativeShort(evt.created_at)}</div>
        </div>
      ))}
    </div>
  );
}

/* ── Main Component ── */

export function SecretsPane() {
  const [page, setPage] = useState(1);
  const [stateFilter, setStateFilter] = useState('');
  const [secretTypeFilter, setSecretTypeFilter] = useState('');
  const [validityFilter, setValidityFilter] = useState('');
  const [bypassFilter, setBypassFilter] = useState('');
  const [selected, setSelected] = useState<SecretAlertItem | null>(null);
  const tableRef = useRef<HTMLDivElement>(null);

  const scrollToTable = useCallback(() => {
    setTimeout(() => tableRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
  }, []);

  const offset = (page - 1) * PAGE_SIZE;

  // Compute push_protection_bypassed filter value
  const bypassBool = bypassFilter === 'yes' ? true : bypassFilter === 'no' ? false : undefined;

  // ── Data queries ──

  const {
    data: summary,
    isLoading: loadingSummary,
    isError: summaryError,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['secret-scanning-summary-v2'],
    queryFn: getSecretAlertSummary,
    staleTime: 60_000,
  });

  const {
    data: alertsData,
    isLoading: loadingAlerts,
    isError: alertsError,
    refetch: refetchAlerts,
  } = useQuery({
    queryKey: [
      'secret-scanning-alerts-v2',
      page,
      stateFilter,
      secretTypeFilter,
      validityFilter,
      bypassFilter,
    ],
    queryFn: () =>
      listSecretAlerts(
        PAGE_SIZE,
        offset,
        stateFilter || undefined,
        secretTypeFilter || undefined,
        validityFilter || undefined,
        bypassBool,
      ),
    staleTime: 30_000,
  });

  const { data: trends, isLoading: loadingTrends } = useQuery({
    queryKey: ['secret-scanning-trends-v2'],
    queryFn: () => getSecretAlertTrends(30),
    staleTime: 120_000,
  });

  const { data: pushStats, isLoading: loadingPushStats } = useQuery({
    queryKey: ['secret-scanning-push-stats'],
    queryFn: getPushProtectionStats,
    staleTime: 120_000,
  });

  // ── Derived chart data ──

  const trendChartData = useMemo(() => {
    if (!trends?.points)
      return { dates: [] as string[], newSeries: [] as number[], resolvedSeries: [] as number[] };
    return {
      dates: trends.points.map((p) => p.date),
      newSeries: trends.points.map((p) => p.new_alerts),
      resolvedSeries: trends.points.map((p) => p.resolved_alerts),
    };
  }, [trends]);

  const typeDistribution = useMemo(() => {
    if (!summary?.open_by_type) return { labels: [] as string[], values: [] as number[] };
    return {
      labels: summary.open_by_type.map((t) => t.secret_type_label),
      values: summary.open_by_type.map((t) => t.count),
    };
  }, [summary]);

  // ── Table columns ──

  const columns: ColumnDef<SecretAlertItem>[] = useMemo(
    () => [
      {
        key: 'repo',
        header: 'Repo',
        sortable: true,
        filterable: true,
        helpText: 'Repository where the secret was detected',
        render: (r) => r.repo_full_name,
        sortValue: (r) => r.repo_full_name,
        filterValue: (r) => r.repo_full_name,
      },
      {
        key: 'secret_type',
        header: 'Secret Type',
        sortable: true,
        filterable: true,
        helpText: 'Type of secret detected (e.g. API key, token)',
        render: (r) => r.secret_type_display ?? r.secret_type,
        sortValue: (r) => r.secret_type,
        filterValue: (r) => r.secret_type_display ?? r.secret_type,
      },
      {
        key: 'state',
        header: 'State',
        sortable: true,
        filterable: true,
        helpText: 'Current state of the alert — click chip to filter',
        render: (r) => (
          <Label
            variant={stateVariant(r.state)}
            onClick={() => {
              setStateFilter(r.state);
              setPage(1);
            }}
          >
            {r.state}
          </Label>
        ),
        sortValue: (r) => r.state,
        filterValue: (r) => r.state,
      },
      {
        key: 'validity',
        header: 'Validity',
        sortable: true,
        filterable: true,
        helpText: 'Whether the secret is active, inactive, or unknown',
        render: (r) => (
          <Label variant={validityVariant(r.validity)}>{r.validity ?? 'unknown'}</Label>
        ),
        sortValue: (r) => r.validity ?? 'unknown',
        filterValue: (r) => r.validity ?? 'unknown',
      },
      {
        key: 'push_protection',
        header: 'Push Protection Bypassed',
        sortable: true,
        filterable: true,
        helpText: 'Whether push protection was bypassed for this secret',
        render: (r) =>
          r.push_protection_bypassed ? (
            <Label variant="danger">Yes</Label>
          ) : (
            <Label variant="muted">No</Label>
          ),
        sortValue: (r) => (r.push_protection_bypassed ? 1 : 0),
        filterValue: (r) => (r.push_protection_bypassed ? 'yes' : 'no'),
      },
      {
        key: 'created',
        header: 'Created',
        sortable: true,
        filterable: true,
        helpText: 'When the alert was first created',
        render: (r) => formatRelativeShort(r.created_at),
        sortValue: (r) => r.created_at,
        filterValue: (r) => r.created_at,
      },
      {
        key: 'resolution',
        header: 'Resolution',
        sortable: true,
        filterable: true,
        helpText: 'How the alert was resolved',
        render: (r) => r.resolution ?? '—',
        sortValue: (r) => r.resolution ?? '',
        filterValue: (r) => r.resolution ?? '',
      },
    ],
    [setStateFilter],
  );

  return (
    <>
      {/* ── Summary Strip ── */}
      <div className={styles.cardGrid}>
        {loadingSummary ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : summaryError ? (
          <ErrorBanner
            message="Failed to load secret scanning summary"
            onRetry={() => void refetchSummary()}
          />
        ) : summary ? (
          <>
            <MetricCard
              value={String(summary.open_alerts)}
              label="Open Alerts"
              helpText="Total unresolved secret scanning alerts"
              onClick={() => {
                setStateFilter('open');
                setPage(1);
                scrollToTable();
              }}
            />
            <MetricCard
              value={String(summary.resolved_30d)}
              label="Resolved (30d)"
              helpText="Alerts resolved in the last 30 days"
              onClick={() => {
                setStateFilter('resolved');
                setPage(1);
                scrollToTable();
              }}
            />
            <MetricCard
              value={String(summary.push_protection_bypasses)}
              label="Push Protection Bypasses"
              helpText="Alerts where push protection was explicitly bypassed"
              onClick={() => {
                setBypassFilter('yes');
                setPage(1);
                scrollToTable();
              }}
            />
            <MetricCard
              value={String(summary.active_secrets)}
              label="Active Secrets"
              helpText="Open alerts where the secret is still valid/active"
              accent
              onClick={() => {
                setValidityFilter('active');
                setStateFilter('open');
                setPage(1);
                scrollToTable();
              }}
            />
            <MetricCard
              value={formatMttr(summary.mttr_hours)}
              label="MTTR"
              helpText="Mean time to resolve secret scanning alerts"
            />
          </>
        ) : null}
      </div>

      {/* ── Charts Row ── */}
      <div className={styles.cardGrid}>
        {/* Alert Trend */}
        <div style={{ flex: 2, minWidth: 0 }}>
          {loadingTrends ? (
            <SkeletonChart />
          ) : trendChartData.dates.length > 0 ? (
            <LineAreaChart
              title="Alert Trend (30d)"
              xAxisData={trendChartData.dates}
              series={[
                { name: 'New', data: trendChartData.newSeries, color: '#f59e0b' },
                {
                  name: 'Resolved',
                  data: trendChartData.resolvedSeries,
                  color: '#3fb950',
                  dashed: true,
                },
              ]}
              height={180}
            />
          ) : null}
        </div>

        {/* Secret Type Distribution */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {loadingSummary ? (
            <SkeletonChart />
          ) : typeDistribution.labels.length > 0 ? (
            <BarChart
              title="Open by Secret Type"
              xAxisData={typeDistribution.labels}
              series={[
                {
                  name: 'Count',
                  data: typeDistribution.values,
                  color: '#f59e0b',
                },
              ]}
              height={180}
            />
          ) : null}
        </div>

        {/* Push Protection Effectiveness */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {loadingPushStats ? (
            <SkeletonChart />
          ) : pushStats ? (
            <BarChart
              title="Push Protection"
              xAxisData={['Blocked', 'Bypassed']}
              series={[
                {
                  name: 'Alerts',
                  data: [pushStats.blocked, pushStats.bypassed],
                  color: '#8b5cf6',
                },
              ]}
              height={180}
            />
          ) : null}
        </div>
      </div>

      {/* ── Filters ── */}
      <div className={styles.filters}>
        <select
          className={styles.filterSelect}
          value={stateFilter}
          onChange={(e) => {
            setStateFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All states</option>
          <option value="open">Open</option>
          <option value="resolved">Resolved</option>
        </select>
        <select
          className={styles.filterSelect}
          value={validityFilter}
          onChange={(e) => {
            setValidityFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All validity</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
          <option value="unknown">Unknown</option>
        </select>
        <select
          className={styles.filterSelect}
          value={bypassFilter}
          onChange={(e) => {
            setBypassFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All push protection</option>
          <option value="yes">Bypassed</option>
          <option value="no">Not bypassed</option>
        </select>
        <select
          className={styles.filterSelect}
          value={secretTypeFilter}
          onChange={(e) => {
            setSecretTypeFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All secret types</option>
          {summary?.open_by_type.map((t) => (
            <option key={t.secret_type_label} value={t.secret_type_label}>
              {t.secret_type_label}
            </option>
          ))}
        </select>
      </div>

      {/* ── Alert Table ── */}
      {loadingAlerts && (
        <div className={styles.center}>
          <Spinner />
        </div>
      )}
      {alertsError && (
        <ErrorBanner
          message="Failed to load secret scanning alerts"
          onRetry={() => void refetchAlerts()}
        />
      )}
      {alertsData && (
        <div className={styles.tableSection} ref={tableRef}>
          <DataTable
            columns={columns}
            data={alertsData.alerts}
            rowKey={(r) => r.id}
            onRowClick={(r) => setSelected(r)}
            emptyMessage="No secret scanning alerts found"
          />
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={alertsData.total}
            onPageChange={setPage}
          />
        </div>
      )}

      {/* ── Detail Drawer ── */}
      <Drawer open={!!selected} onClose={() => setSelected(null)} title="Secret Scanning Alert">
        {selected && (
          <>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Repository</div>
              <div className={styles.drawerValue}>{selected.repo_full_name}</div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Secret Type</div>
              <div className={styles.drawerValue}>
                {selected.secret_type_display ?? selected.secret_type}
              </div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>State</div>
              <div className={styles.drawerValue}>
                <Label variant={stateVariant(selected.state)}>{selected.state}</Label>
              </div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Validity</div>
              <div className={styles.drawerValue}>
                <Label variant={validityVariant(selected.validity)}>
                  {selected.validity ?? 'unknown'}
                </Label>
              </div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Resolution</div>
              <div className={styles.drawerValue}>{selected.resolution ?? '—'}</div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Push Protection Bypassed</div>
              <div className={styles.drawerValue}>
                {selected.push_protection_bypassed ? (
                  <Label variant="danger">
                    Yes — by {selected.push_protection_bypassed_by ?? 'unknown'}
                  </Label>
                ) : (
                  'No'
                )}
              </div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Locations</div>
              <div className={styles.drawerValue}>{selected.locations_count}</div>
            </div>
            {selected.file_path && (
              <div className={styles.drawerField}>
                <div className={styles.drawerLabel}>File</div>
                <div className={`${styles.drawerValue} ${styles.drawerMono}`}>
                  {selected.file_path}
                </div>
              </div>
            )}
            {selected.commit_sha && (
              <div className={styles.drawerField}>
                <div className={styles.drawerLabel}>Commit</div>
                <div className={`${styles.drawerValue} ${styles.drawerMono}`}>
                  {selected.commit_sha}
                </div>
              </div>
            )}
            {selected.resolved_by && (
              <div className={styles.drawerField}>
                <div className={styles.drawerLabel}>Resolved By</div>
                <div className={styles.drawerValue}>{selected.resolved_by}</div>
              </div>
            )}
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Created</div>
              <div className={styles.drawerValue}>{formatRelativeShort(selected.created_at)}</div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Resolved</div>
              <div className={styles.drawerValue}>
                {selected.resolved_at ? formatRelativeShort(selected.resolved_at) : '—'}
              </div>
            </div>

            {/* Audit Trail */}
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Audit Trail</div>
              <AuditTrailSection alertId={selected.id} />
            </div>
          </>
        )}
      </Drawer>
    </>
  );
}
