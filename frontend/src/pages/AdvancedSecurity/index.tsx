import { useState, useMemo, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { Drawer } from '../../components/primitives/Drawer';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { PageHeader } from '../../components/common/PageHeader';
import { SkeletonCard } from '../../components/common/SkeletonCard';
import { SkeletonTable } from '../../components/common/SkeletonTable';
import { Label } from '../../components/primitives/Label';
import { Pagination } from '../../components/primitives/Pagination';
import {
  getUnifiedSecurity,
  getCodeScanningAlerts,
  getCodeScanning,
  getDependabotAlerts,
  getVulnerabilities,
  type CodeScanningAlertItem,
  type DependabotAlertItem,
} from '../../api/healthSignals';
import { listDetections } from '../../api/detections';
import type { DetectionResponse } from '../../types/detections';
import { formatRelativeShort } from '../../utils/dates';
import {
  useEnumQueryParam,
  useQueryParam,
  useQueryParamInt,
  useSetQueryParams,
} from '../../hooks/useQueryParam';
import styles from './AdvancedSecurity.module.css';

const PAGE_SIZE = 50;

import { StrategicPane } from './StrategicPane';
import { SecretsPane } from './SecretsPane';

type TabKey = 'overview' | 'secrets' | 'code' | 'dependabot' | 'activity' | 'strategic';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'secrets', label: 'Secret Scanning' },
  { key: 'code', label: 'Code Scanning' },
  { key: 'dependabot', label: 'Dependabot' },
  { key: 'activity', label: 'Activity Log' },
  { key: 'strategic', label: 'Strategic' },
];

function sevVariant(sev: string) {
  if (sev === 'critical') return 'danger' as const;
  if (sev === 'high') return 'severe' as const;
  if (sev === 'medium') return 'attention' as const;
  return 'muted' as const;
}

function stateVariant(state: string) {
  if (state === 'open') return 'attention' as const;
  if (state === 'fixed' || state === 'resolved') return 'success' as const;
  if (state === 'dismissed') return 'muted' as const;
  return 'muted' as const;
}

/* ── Mini Sparkline (60×20 inline SVG) ── */
function MiniSparkline({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return null;
  const w = 60;
  const h = 20;
  const maxVal = Math.max(1, ...data);
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - (v / maxVal) * h;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg
      className={styles.miniSparkline}
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      aria-hidden="true"
    >
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

/* ── Compute week-over-week delta ── */
function computeWoWDelta(values: number[]): { delta: string; deltaDir: 'up' | 'down' | 'neutral' } {
  if (values.length < 14) return { delta: '', deltaDir: 'neutral' };
  const recent7 = values.slice(-7).reduce((a, b) => a + b, 0);
  const prev7 = values.slice(-14, -7).reduce((a, b) => a + b, 0);
  const diff = recent7 - prev7;
  if (diff === 0) return { delta: '0', deltaDir: 'neutral' };
  const sign = diff > 0 ? '+' : '';
  // For security alerts: up = bad (more alerts), down = good (fewer alerts)
  const dir: 'up' | 'down' = diff > 0 ? 'up' : 'down';
  return { delta: `${sign}${diff}`, deltaDir: dir };
}

/* ── Period selector type ── */
type TrendPeriod = '7d' | '14d' | '30d';

/* ── Trend SVG polyline chart ── */
function TrendChart({
  data,
}: {
  data: { day: string; secret_scanning: number; code_scanning: number; dependabot: number }[];
}) {
  const [period, setPeriod] = useState<TrendPeriod>('30d');

  if (data.length === 0) return null;

  const periodDays = period === '7d' ? 7 : period === '14d' ? 14 : 30;
  const slicedData = data.slice(-periodDays);

  const width = 800;
  const height = 120;
  const pad = { top: 8, right: 8, bottom: 8, left: 8 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;

  const maxVal = Math.max(
    1,
    ...slicedData.map((d) => Math.max(d.secret_scanning, d.code_scanning, d.dependabot)),
  );

  function toPoints(accessor: (d: (typeof slicedData)[0]) => number): string {
    return slicedData
      .map((d, i) => {
        const x = pad.left + (i / Math.max(1, slicedData.length - 1)) * chartW;
        const y = pad.top + chartH - (accessor(d) / maxVal) * chartH;
        return `${x},${y}`;
      })
      .join(' ');
  }

  return (
    <div className={styles.trendSection}>
      <div className={styles.trendHeader}>
        <div className={styles.trendTitle}>Alert Trend</div>
        <div className={styles.periodToggle} role="group" aria-label="Trend period">
          {(['7d', '14d', '30d'] as const).map((p) => (
            <button
              key={p}
              className={`${styles.periodBtn} ${period === p ? styles.periodBtnActive : ''}`}
              onClick={() => setPeriod(p)}
              aria-pressed={period === p}
            >
              {p}
            </button>
          ))}
        </div>
      </div>
      <svg
        className={styles.trendChart}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
      >
        <polyline
          points={toPoints((d) => d.secret_scanning)}
          fill="none"
          stroke="var(--attention)"
          strokeWidth="2"
        />
        <polyline
          points={toPoints((d) => d.code_scanning)}
          fill="none"
          stroke="var(--done)"
          strokeWidth="2"
        />
        <polyline
          points={toPoints((d) => d.dependabot)}
          fill="none"
          stroke="var(--danger)"
          strokeWidth="2"
        />
      </svg>
      <div className={styles.trendLegend}>
        <span>
          <span className={styles.legendDot} style={{ background: 'var(--attention)' }} />
          Secret Scanning
        </span>
        <span>
          <span className={styles.legendDot} style={{ background: 'var(--done)' }} />
          Code Scanning
        </span>
        <span>
          <span className={styles.legendDot} style={{ background: 'var(--danger)' }} />
          Dependabot
        </span>
      </div>
    </div>
  );
}

/* ── Overview Tab ── */
function OverviewTab({ onSwitchTab }: { onSwitchTab: (tab: TabKey) => void }) {
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['unified-security'],
    queryFn: getUnifiedSecurity,
    staleTime: 60_000,
  });

  if (isLoading)
    return (
      <div className={styles.center}>
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonTable />
      </div>
    );
  if (isError || !data)
    return (
      <ErrorBanner message="Failed to load security overview" onRetry={() => void refetch()} />
    );

  const totalCritical =
    data.code_scanning.critical + data.dependabot.critical + data.detections.critical;
  const totalHigh = data.code_scanning.high + data.dependabot.high + data.detections.high;
  const totalMedium = data.code_scanning.medium + data.dependabot.medium + data.detections.medium;
  const totalLow = data.code_scanning.low + data.dependabot.low + data.detections.low;

  // Compute week-over-week deltas from trend_30d
  const secretTrend = data.trend_30d.map((d) => d.secret_scanning);
  const codeTrend = data.trend_30d.map((d) => d.code_scanning);
  const dependabotTrend = data.trend_30d.map((d) => d.dependabot);

  const secretDelta = computeWoWDelta(secretTrend);
  const codeDelta = computeWoWDelta(codeTrend);
  const dependabotDelta = computeWoWDelta(dependabotTrend);

  // Last 7 data points for sparklines
  const secretSparkData = secretTrend.slice(-7);
  const codeSparkData = codeTrend.slice(-7);
  const dependabotSparkData = dependabotTrend.slice(-7);

  return (
    <>
      <div className={styles.cardGrid}>
        <div className={styles.cardWithSparkline}>
          <MetricCard
            value={String(data.secret_scanning.open)}
            label="Secret Scanning"
            helpText="Open secret scanning alerts across all repos"
            onClick={() => onSwitchTab('secrets')}
            delta={secretDelta.delta || undefined}
            deltaDir={secretDelta.deltaDir}
          />
          <MiniSparkline data={secretSparkData} color="var(--attention)" />
        </div>
        <div className={styles.cardWithSparkline}>
          <MetricCard
            value={String(data.code_scanning.open)}
            label="Code Scanning"
            helpText="Open code scanning alerts across all repos"
            onClick={() => onSwitchTab('code')}
            delta={codeDelta.delta || undefined}
            deltaDir={codeDelta.deltaDir}
          />
          <MiniSparkline data={codeSparkData} color="var(--done)" />
        </div>
        <div className={styles.cardWithSparkline}>
          <MetricCard
            value={String(data.dependabot.open)}
            label="Dependabot"
            helpText="Open Dependabot vulnerability alerts"
            onClick={() => onSwitchTab('dependabot')}
            delta={dependabotDelta.delta || undefined}
            deltaDir={dependabotDelta.deltaDir}
          />
          <MiniSparkline data={dependabotSparkData} color="var(--danger)" />
        </div>
        <MetricCard
          value={String(data.detections.active)}
          label="Threat Detections"
          helpText="Active GHAS-related threat detections"
          accent
          onClick={() => navigate('/threats')}
        />
      </div>

      <TrendChart data={data.trend_30d} />

      <div className={styles.severitySection}>
        <div className={styles.severityTitle}>Aggregated Severity Breakdown</div>
        <div className={styles.severityGrid}>
          <div className={styles.severityItem}>
            <Label
              variant="danger"
              onClick={() => onSwitchTab('code')}
              title="View critical code scanning alerts"
            >
              Critical
            </Label>
            <span className={styles.severityCount}>{totalCritical}</span>
          </div>
          <div className={styles.severityItem}>
            <Label
              variant="severe"
              onClick={() => onSwitchTab('code')}
              title="View high code scanning alerts"
            >
              High
            </Label>
            <span className={styles.severityCount}>{totalHigh}</span>
          </div>
          <div className={styles.severityItem}>
            <Label
              variant="attention"
              onClick={() => onSwitchTab('code')}
              title="View medium code scanning alerts"
            >
              Medium
            </Label>
            <span className={styles.severityCount}>{totalMedium}</span>
          </div>
          <div className={styles.severityItem}>
            <Label
              variant="muted"
              onClick={() => onSwitchTab('code')}
              title="View low code scanning alerts"
            >
              Low
            </Label>
            <span className={styles.severityCount}>{totalLow}</span>
          </div>
        </div>
      </div>
    </>
  );
}

/* ── Code Scanning Tab ── */
function CodeScanningTab() {
  const [page, setPage] = useQueryParamInt('page', 1);
  const [stateFilter] = useQueryParam('state', '');
  const [sevFilter] = useQueryParam('severity', '');
  const setParams = useSetQueryParams();
  const [selected, setSelected] = useState<CodeScanningAlertItem | null>(null);
  const tableRef = useRef<HTMLDivElement>(null);

  const scrollToTable = useCallback(() => {
    setTimeout(() => tableRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
  }, []);

  const offset = (page - 1) * PAGE_SIZE;

  const { data: summary, isLoading: loadingSummary } = useQuery({
    queryKey: ['code-scanning-summary'],
    queryFn: getCodeScanning,
    staleTime: 60_000,
  });

  const {
    data: alertsData,
    isLoading: loadingAlerts,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['code-scanning-alerts', page, stateFilter, sevFilter],
    queryFn: () =>
      getCodeScanningAlerts(PAGE_SIZE, offset, stateFilter || undefined, sevFilter || undefined),
    staleTime: 30_000,
  });

  const columns: ColumnDef<CodeScanningAlertItem>[] = useMemo(
    () => [
      {
        key: 'repo',
        header: 'Repo',
        sortable: true,
        filterable: true,
        helpText: 'Repository where the code scanning alert was found',
        render: (r) => r.repo_full_name,
        sortValue: (r) => r.repo_full_name,
        filterValue: (r) => r.repo_full_name,
      },
      {
        key: 'rule_id',
        header: 'Rule ID',
        sortable: true,
        filterable: true,
        helpText: 'The code scanning rule that triggered this alert',
        render: (r) => r.rule_id,
        sortValue: (r) => r.rule_id,
        filterValue: (r) => r.rule_id,
      },
      {
        key: 'severity',
        header: 'Severity',
        sortable: true,
        filterable: true,
        helpText: 'Alert severity level — click chip to filter',
        render: (r) =>
          r.security_severity ? (
            <Label
              variant={sevVariant(r.security_severity)}
              onClick={() => {
                setParams({ severity: r.security_severity!, page: null });
              }}
            >
              {r.security_severity}
            </Label>
          ) : (
            <Label variant="muted">{r.severity ?? '—'}</Label>
          ),
        sortValue: (r) => r.security_severity ?? r.severity ?? '',
        filterValue: (r) => r.security_severity ?? r.severity ?? '',
      },
      {
        key: 'tool',
        header: 'Tool',
        sortable: true,
        filterable: true,
        helpText: 'The analysis tool that produced this alert',
        render: (r) => r.tool_name ?? '—',
        sortValue: (r) => r.tool_name ?? '',
        filterValue: (r) => r.tool_name ?? '',
      },
      {
        key: 'file',
        header: 'File',
        sortable: true,
        filterable: true,
        helpText: 'Source file where the issue was detected',
        render: (r) => r.file_path ?? '—',
        sortValue: (r) => r.file_path ?? '',
        filterValue: (r) => r.file_path ?? '',
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
              setParams({ state: r.state, page: null });
            }}
          >
            {r.state}
          </Label>
        ),
        sortValue: (r) => r.state,
        filterValue: (r) => r.state,
      },
      {
        key: 'created',
        header: 'Created',
        sortable: true,
        filterable: true,
        helpText: 'When the alert was first detected',
        render: (r) => formatRelativeShort(r.created_at),
        sortValue: (r) => r.created_at,
        filterValue: (r) => r.created_at,
      },
    ],
    [setParams],
  );

  return (
    <>
      <div className={styles.cardGrid}>
        {loadingSummary ? (
          <Spinner />
        ) : summary ? (
          <>
            <MetricCard
              value={String(summary.open_count)}
              label="Open Alerts"
              helpText="Total open code scanning alerts"
              onClick={() => {
                setParams({ state: 'open', severity: null, page: null });
                scrollToTable();
              }}
            />
            <MetricCard
              value={String(summary.critical_count)}
              label="Critical"
              helpText="Critical severity open alerts"
              accent
              onClick={() => {
                setParams({ severity: 'critical', state: null, page: null });
                scrollToTable();
              }}
            />
            <MetricCard
              value={String(summary.high_count)}
              label="High"
              helpText="High severity open alerts"
              onClick={() => {
                setParams({ severity: 'high', state: null, page: null });
                scrollToTable();
              }}
            />
            <MetricCard
              value={String(Math.round(summary.avg_hours_to_close))}
              label="Avg Hours to Close"
              helpText="Average hours to close code scanning alerts"
            />
            <MetricCard
              value={String(summary.fixed_count)}
              label="Fixed"
              helpText="Total code scanning alerts that have been fixed"
              onClick={() => {
                setParams({ state: 'fixed', severity: null, page: null });
                scrollToTable();
              }}
            />
          </>
        ) : null}
      </div>

      <div className={styles.filters}>
        <select
          className={styles.filterSelect}
          value={stateFilter}
          onChange={(e) => {
            setParams({ state: e.target.value || null, page: null });
          }}
        >
          <option value="">All states</option>
          <option value="open">Open</option>
          <option value="fixed">Fixed</option>
          <option value="dismissed">Dismissed</option>
        </select>
        <select
          className={styles.filterSelect}
          value={sevFilter}
          onChange={(e) => {
            setParams({ severity: e.target.value || null, page: null });
          }}
        >
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      {loadingAlerts && (
        <div className={styles.center}>
          <Spinner />
        </div>
      )}
      {isError && (
        <ErrorBanner message="Failed to load code scanning alerts" onRetry={() => void refetch()} />
      )}
      {alertsData && (
        <div className={styles.tableSection} ref={tableRef}>
          <DataTable
            columns={columns}
            data={alertsData.alerts}
            rowKey={(r) => r.id}
            onRowClick={(r) => setSelected(r)}
            emptyMessage="No code scanning alerts found"
          />
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={alertsData.total}
            onPageChange={setPage}
          />
        </div>
      )}

      <Drawer open={!!selected} onClose={() => setSelected(null)} title="Code Scanning Alert">
        {selected && (
          <>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Repository</div>
              <div className={styles.drawerValue}>{selected.repo_full_name}</div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Rule</div>
              <div className={styles.drawerValue}>{selected.rule_id}</div>
            </div>
            {selected.rule_description && (
              <div className={styles.drawerField}>
                <div className={styles.drawerLabel}>Description</div>
                <div className={styles.drawerValue}>{selected.rule_description}</div>
              </div>
            )}
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Severity</div>
              <div className={styles.drawerValue}>
                <Label variant={sevVariant(selected.security_severity ?? selected.severity ?? '')}>
                  {selected.security_severity ?? selected.severity ?? '—'}
                </Label>
              </div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Tool</div>
              <div className={styles.drawerValue}>{selected.tool_name ?? '—'}</div>
            </div>
            {selected.file_path && (
              <div className={styles.drawerField}>
                <div className={styles.drawerLabel}>File</div>
                <div className={`${styles.drawerValue} ${styles.drawerMono}`}>
                  {selected.file_path}
                  {selected.start_line ? `:${selected.start_line}` : ''}
                </div>
              </div>
            )}
            {selected.cwe_ids && selected.cwe_ids.length > 0 && (
              <div className={styles.drawerField}>
                <div className={styles.drawerLabel}>CWE</div>
                <div className={styles.drawerValue}>{selected.cwe_ids.join(', ')}</div>
              </div>
            )}
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>State</div>
              <div className={styles.drawerValue}>
                <Label variant={stateVariant(selected.state)}>{selected.state}</Label>
              </div>
            </div>
            {selected.dismissed_by && (
              <div className={styles.drawerField}>
                <div className={styles.drawerLabel}>Dismissed By</div>
                <div className={styles.drawerValue}>
                  {selected.dismissed_by} — {selected.dismissed_reason ?? 'no reason'}
                </div>
              </div>
            )}
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Created</div>
              <div className={styles.drawerValue}>{formatRelativeShort(selected.created_at)}</div>
            </div>
            {selected.fixed_at && (
              <div className={styles.drawerField}>
                <div className={styles.drawerLabel}>Fixed</div>
                <div className={styles.drawerValue}>{formatRelativeShort(selected.fixed_at)}</div>
              </div>
            )}
          </>
        )}
      </Drawer>
    </>
  );
}

/* ── Dependabot Tab ── */
function DependabotTab() {
  const [page, setPage] = useQueryParamInt('page', 1);
  const [stateFilter] = useQueryParam('state', '');
  const [sevFilter] = useQueryParam('severity', '');
  const setParams = useSetQueryParams();
  const [selected, setSelected] = useState<DependabotAlertItem | null>(null);
  const tableRef = useRef<HTMLDivElement>(null);

  const scrollToTable = useCallback(() => {
    setTimeout(() => tableRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
  }, []);

  const offset = (page - 1) * PAGE_SIZE;

  const { data: summary, isLoading: loadingSummary } = useQuery({
    queryKey: ['vulnerabilities-summary'],
    queryFn: getVulnerabilities,
    staleTime: 60_000,
  });

  const {
    data: alertsData,
    isLoading: loadingAlerts,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['dependabot-alerts', page, stateFilter, sevFilter],
    queryFn: () =>
      getDependabotAlerts(PAGE_SIZE, offset, stateFilter || undefined, sevFilter || undefined),
    staleTime: 30_000,
  });

  const columns: ColumnDef<DependabotAlertItem>[] = useMemo(
    () => [
      {
        key: 'repo',
        header: 'Repo',
        sortable: true,
        filterable: true,
        helpText: 'Repository affected by the vulnerability',
        render: (r) => r.repo_full_name,
        sortValue: (r) => r.repo_full_name,
        filterValue: (r) => r.repo_full_name,
      },
      {
        key: 'package',
        header: 'Package',
        sortable: true,
        filterable: true,
        helpText: 'Vulnerable package name',
        render: (r) => r.package_name,
        sortValue: (r) => r.package_name,
        filterValue: (r) => r.package_name,
      },
      {
        key: 'ecosystem',
        header: 'Ecosystem',
        sortable: true,
        filterable: true,
        helpText: 'Package ecosystem (npm, pip, maven, etc.)',
        render: (r) => r.package_ecosystem ?? '—',
        sortValue: (r) => r.package_ecosystem ?? '',
        filterValue: (r) => r.package_ecosystem ?? '',
      },
      {
        key: 'severity',
        header: 'Severity',
        sortable: true,
        filterable: true,
        helpText: 'Vulnerability severity level — click chip to filter',
        render: (r) =>
          r.severity ? (
            <Label
              variant={sevVariant(r.severity)}
              onClick={() => {
                setParams({ severity: r.severity!, page: null });
              }}
            >
              {r.severity}
            </Label>
          ) : (
            '—'
          ),
        sortValue: (r) => r.severity ?? '',
        filterValue: (r) => r.severity ?? '',
      },
      {
        key: 'cvss',
        header: 'CVSS',
        sortable: true,
        filterable: true,
        helpText: 'CVSS score (Common Vulnerability Scoring System)',
        render: (r) => (r.cvss_score != null ? r.cvss_score.toFixed(1) : '—'),
        sortValue: (r) => r.cvss_score ?? 0,
        filterValue: (r) => (r.cvss_score != null ? String(r.cvss_score) : ''),
      },
      {
        key: 'cve',
        header: 'CVE',
        sortable: true,
        filterable: true,
        helpText: 'CVE identifier for the vulnerability',
        render: (r) => r.cve_id ?? '—',
        sortValue: (r) => r.cve_id ?? '',
        filterValue: (r) => r.cve_id ?? '',
      },
      {
        key: 'state',
        header: 'State',
        sortable: true,
        filterable: true,
        helpText: 'Current state of the Dependabot alert — click chip to filter',
        render: (r) => (
          <Label
            variant={stateVariant(r.state)}
            onClick={() => {
              setParams({ state: r.state, page: null });
            }}
          >
            {r.state}
          </Label>
        ),
        sortValue: (r) => r.state,
        filterValue: (r) => r.state,
      },
      {
        key: 'created',
        header: 'Created',
        sortable: true,
        filterable: true,
        helpText: 'When the alert was first detected',
        render: (r) => formatRelativeShort(r.created_at),
        sortValue: (r) => r.created_at,
        filterValue: (r) => r.created_at,
      },
    ],
    [setParams],
  );

  return (
    <>
      <div className={styles.cardGrid}>
        {loadingSummary ? (
          <Spinner />
        ) : summary ? (
          <>
            <MetricCard
              value={String(summary.total_open)}
              label="Total Open"
              helpText="Total open Dependabot alerts"
              onClick={() => {
                setParams({ state: 'open', severity: null, page: null });
                scrollToTable();
              }}
            />
            <MetricCard
              value={String(summary.critical_open)}
              label="Critical Open"
              helpText="Critical severity open vulnerability alerts"
              accent
              onClick={() => {
                setParams({ severity: 'critical', state: null, page: null });
                scrollToTable();
              }}
            />
            <MetricCard
              value={String(summary.high_open)}
              label="High Open"
              helpText="High severity open vulnerability alerts"
              onClick={() => {
                setParams({ severity: 'high', state: null, page: null });
                scrollToTable();
              }}
            />
            <MetricCard
              value={String(Math.round(summary.avg_open_days))}
              label="Avg Open Days"
              helpText="Average number of days Dependabot alerts remain open"
            />
            <MetricCard
              value={String(summary.critical_aging_gt_90d)}
              label="Critical >90d"
              helpText="Critical alerts that have been open for more than 90 days"
              accent
              onClick={() => {
                setParams({ severity: 'critical', state: 'open', page: null });
                scrollToTable();
              }}
            />
          </>
        ) : null}
      </div>

      <div className={styles.filters}>
        <select
          className={styles.filterSelect}
          value={stateFilter}
          onChange={(e) => {
            setParams({ state: e.target.value || null, page: null });
          }}
        >
          <option value="">All states</option>
          <option value="open">Open</option>
          <option value="fixed">Fixed</option>
          <option value="dismissed">Dismissed</option>
        </select>
        <select
          className={styles.filterSelect}
          value={sevFilter}
          onChange={(e) => {
            setParams({ severity: e.target.value || null, page: null });
          }}
        >
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      {loadingAlerts && (
        <div className={styles.center}>
          <Spinner />
        </div>
      )}
      {isError && (
        <ErrorBanner message="Failed to load Dependabot alerts" onRetry={() => void refetch()} />
      )}
      {alertsData && (
        <div className={styles.tableSection} ref={tableRef}>
          <DataTable
            columns={columns}
            data={alertsData.alerts}
            rowKey={(r) => r.id}
            onRowClick={(r) => setSelected(r)}
            emptyMessage="No Dependabot alerts found"
          />
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={alertsData.total}
            onPageChange={setPage}
          />
        </div>
      )}

      <Drawer open={!!selected} onClose={() => setSelected(null)} title="Dependabot Alert">
        {selected && (
          <>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Repository</div>
              <div className={styles.drawerValue}>{selected.repo_full_name}</div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Package</div>
              <div className={`${styles.drawerValue} ${styles.drawerMono}`}>
                {selected.package_name}
              </div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Ecosystem</div>
              <div className={styles.drawerValue}>{selected.package_ecosystem ?? '—'}</div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Severity</div>
              <div className={styles.drawerValue}>
                {selected.severity ? (
                  <Label variant={sevVariant(selected.severity)}>{selected.severity}</Label>
                ) : (
                  '—'
                )}
              </div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>CVSS Score</div>
              <div className={styles.drawerValue}>
                {selected.cvss_score != null ? selected.cvss_score.toFixed(1) : '—'}
              </div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>CVE</div>
              <div className={styles.drawerValue}>{selected.cve_id ?? '—'}</div>
            </div>
            {selected.cwe_ids && selected.cwe_ids.length > 0 && (
              <div className={styles.drawerField}>
                <div className={styles.drawerLabel}>CWE</div>
                <div className={styles.drawerValue}>{selected.cwe_ids.join(', ')}</div>
              </div>
            )}
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Vulnerable Versions</div>
              <div className={`${styles.drawerValue} ${styles.drawerMono}`}>
                {selected.vulnerable_version_range ?? '—'}
              </div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Patched Version</div>
              <div className={`${styles.drawerValue} ${styles.drawerMono}`}>
                {selected.patched_version ?? '—'}
              </div>
            </div>
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>State</div>
              <div className={styles.drawerValue}>
                <Label variant={stateVariant(selected.state)}>{selected.state}</Label>
              </div>
            </div>
            {selected.dismissed_by && (
              <div className={styles.drawerField}>
                <div className={styles.drawerLabel}>Dismissed By</div>
                <div className={styles.drawerValue}>
                  {selected.dismissed_by} — {selected.dismissed_reason ?? 'no reason'}
                </div>
              </div>
            )}
            <div className={styles.drawerField}>
              <div className={styles.drawerLabel}>Created</div>
              <div className={styles.drawerValue}>{formatRelativeShort(selected.created_at)}</div>
            </div>
            {selected.fixed_at && (
              <div className={styles.drawerField}>
                <div className={styles.drawerLabel}>Fixed</div>
                <div className={styles.drawerValue}>{formatRelativeShort(selected.fixed_at)}</div>
              </div>
            )}
          </>
        )}
      </Drawer>
    </>
  );
}

/* ── Activity Log Tab ── */
const GHAS_KEYWORDS = ['ghas', 'secret', 'codeql', 'push-protection', 'security-feature'];

function ActivityLogTab() {
  const navigate = useNavigate();
  const [page, setPage] = useQueryParamInt('page', 1);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['ghas-activity-detections', page],
    queryFn: () => listDetections({ page, page_size: PAGE_SIZE }),
    staleTime: 30_000,
  });

  const filteredItems = useMemo(() => {
    if (!data) return [];
    return data.items.filter((d) => {
      const name = (d.rule_name ?? d.title ?? '').toLowerCase();
      return GHAS_KEYWORDS.some((kw) => name.includes(kw));
    });
  }, [data]);

  const columns: ColumnDef<DetectionResponse>[] = useMemo(
    () => [
      {
        key: 'title',
        header: 'Title',
        sortable: true,
        filterable: true,
        helpText: 'Detection title describing the security event',
        render: (r) => r.title,
        sortValue: (r) => r.title,
        filterValue: (r) => r.title,
      },
      {
        key: 'severity',
        header: 'Severity',
        sortable: true,
        filterable: true,
        helpText: 'Detection severity level',
        render: (r) => <Label variant={sevVariant(r.severity)}>{r.severity}</Label>,
        sortValue: (r) => r.severity,
        filterValue: (r) => r.severity,
      },
      {
        key: 'actor',
        header: 'Actor',
        sortable: true,
        filterable: true,
        helpText: 'User who performed the action that triggered this detection',
        render: (r) => r.actor ?? '—',
        sortValue: (r) => r.actor ?? '',
        filterValue: (r) => r.actor ?? '',
      },
      {
        key: 'org',
        header: 'Org',
        sortable: true,
        filterable: true,
        helpText: 'Organization where the event occurred',
        render: (r) => r.org ?? '—',
        sortValue: (r) => r.org ?? '',
        filterValue: (r) => r.org ?? '',
      },
      {
        key: 'triggered_at',
        header: 'Triggered At',
        sortable: true,
        filterable: true,
        helpText: 'When this detection was triggered',
        render: (r) => formatRelativeShort(r.triggered_at),
        sortValue: (r) => r.triggered_at,
        filterValue: (r) => r.triggered_at,
      },
    ],
    [],
  );

  return (
    <>
      {isLoading && (
        <div className={styles.center}>
          <Spinner />
        </div>
      )}
      {isError && (
        <ErrorBanner
          message="Failed to load GHAS activity detections"
          onRetry={() => void refetch()}
        />
      )}
      {data && (
        <div className={styles.tableSection}>
          <DataTable
            columns={columns}
            data={filteredItems}
            rowKey={(r) => r.id}
            onRowClick={(r) => navigate(`/threats?id=${r.id}`)}
            emptyMessage="No GHAS-related detections found"
          />
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={filteredItems.length}
            onPageChange={setPage}
          />
        </div>
      )}
    </>
  );
}

/* ── Main Page ── */
export function AdvancedSecurityPage() {
  const TAB_KEYS = ['overview', 'secrets', 'code', 'dependabot', 'activity', 'strategic'] as const;
  const [activeTab, setTab] = useEnumQueryParam('tab', TAB_KEYS, 'overview');

  return (
    <div className={styles.splitLayout}>
      <div className={styles.splitMain}>
        <div className={styles.pageHeader}>
          <PageHeader
            title="Advanced Security"
            description="GitHub Advanced Security coverage and alert analytics"
          />
        </div>

        <div className={styles.tabs}>
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`${styles.tab} ${activeTab === t.key ? styles.tabActive : ''}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        {activeTab === 'overview' && <OverviewTab onSwitchTab={setTab} />}
        {activeTab === 'secrets' && <SecretsPane />}
        {activeTab === 'code' && <CodeScanningTab />}
        {activeTab === 'dependabot' && <DependabotTab />}
        {activeTab === 'activity' && <ActivityLogTab />}
        {activeTab === 'strategic' && <StrategicPane />}
      </div>
    </div>
  );
}
