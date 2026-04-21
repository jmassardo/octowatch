import { useState, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { Drawer } from '../../components/primitives/Drawer';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Label } from '../../components/primitives/Label';
import { Pagination } from '../../components/primitives/Pagination';
import {
  getUnifiedSecurity,
  getSecretScanningAlerts,
  getSecretScanning,
  getCodeScanningAlerts,
  getCodeScanning,
  getDependabotAlerts,
  getVulnerabilities,
  type SecretScanningAlertItem,
  type CodeScanningAlertItem,
  type DependabotAlertItem,
} from '../../api/healthSignals';
import { listDetections } from '../../api/detections';
import type { DetectionResponse } from '../../types/detections';
import { formatRelativeShort } from '../../utils/dates';
import styles from './AdvancedSecurity.module.css';

const PAGE_SIZE = 50;

type TabKey = 'overview' | 'secrets' | 'code' | 'dependabot' | 'activity';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'secrets', label: 'Secret Scanning' },
  { key: 'code', label: 'Code Scanning' },
  { key: 'dependabot', label: 'Dependabot' },
  { key: 'activity', label: 'Activity Log' },
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

/* ── Trend SVG polyline chart ── */
function TrendChart({
  data,
}: {
  data: { day: string; secret_scanning: number; code_scanning: number; dependabot: number }[];
}) {
  if (data.length === 0) return null;

  const width = 800;
  const height = 120;
  const pad = { top: 8, right: 8, bottom: 8, left: 8 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;

  const maxVal = Math.max(
    1,
    ...data.map((d) => Math.max(d.secret_scanning, d.code_scanning, d.dependabot)),
  );

  function toPoints(accessor: (d: (typeof data)[0]) => number): string {
    return data
      .map((d, i) => {
        const x = pad.left + (i / Math.max(1, data.length - 1)) * chartW;
        const y = pad.top + chartH - (accessor(d) / maxVal) * chartH;
        return `${x},${y}`;
      })
      .join(' ');
  }

  return (
    <div className={styles.trendSection}>
      <div className={styles.trendTitle}>30-Day Alert Trend</div>
      <svg
        className={styles.trendChart}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
      >
        <polyline
          points={toPoints((d) => d.secret_scanning)}
          fill="none"
          stroke="#f59e0b"
          strokeWidth="2"
        />
        <polyline
          points={toPoints((d) => d.code_scanning)}
          fill="none"
          stroke="#8b5cf6"
          strokeWidth="2"
        />
        <polyline
          points={toPoints((d) => d.dependabot)}
          fill="none"
          stroke="#ef4444"
          strokeWidth="2"
        />
      </svg>
      <div className={styles.trendLegend}>
        <span>
          <span className={styles.legendDot} style={{ background: '#f59e0b' }} />
          Secret Scanning
        </span>
        <span>
          <span className={styles.legendDot} style={{ background: '#8b5cf6' }} />
          Code Scanning
        </span>
        <span>
          <span className={styles.legendDot} style={{ background: '#ef4444' }} />
          Dependabot
        </span>
      </div>
    </div>
  );
}

/* ── Overview Tab ── */
function OverviewTab() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['unified-security'],
    queryFn: getUnifiedSecurity,
    staleTime: 60_000,
  });

  if (isLoading)
    return (
      <div className={styles.center}>
        <Spinner />
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

  return (
    <>
      <div className={styles.cardGrid}>
        <MetricCard
          value={String(data.secret_scanning.open)}
          label="Secret Scanning"
          helpText="Open secret scanning alerts across all repos"
        />
        <MetricCard
          value={String(data.code_scanning.open)}
          label="Code Scanning"
          helpText="Open code scanning alerts across all repos"
        />
        <MetricCard
          value={String(data.dependabot.open)}
          label="Dependabot"
          helpText="Open Dependabot vulnerability alerts"
        />
        <MetricCard
          value={String(data.detections.active)}
          label="Threat Detections"
          helpText="Active GHAS-related threat detections"
          accent
        />
      </div>

      <TrendChart data={data.trend_30d} />

      <div className={styles.severitySection}>
        <div className={styles.severityTitle}>Aggregated Severity Breakdown</div>
        <div className={styles.severityGrid}>
          <div className={styles.severityItem}>
            <Label variant="danger">Critical</Label>
            <span className={styles.severityCount}>{totalCritical}</span>
          </div>
          <div className={styles.severityItem}>
            <Label variant="severe">High</Label>
            <span className={styles.severityCount}>{totalHigh}</span>
          </div>
          <div className={styles.severityItem}>
            <Label variant="attention">Medium</Label>
            <span className={styles.severityCount}>{totalMedium}</span>
          </div>
          <div className={styles.severityItem}>
            <Label variant="muted">Low</Label>
            <span className={styles.severityCount}>{totalLow}</span>
          </div>
        </div>
      </div>
    </>
  );
}

/* ── Secret Scanning Tab ── */
function SecretScanningTab() {
  const [page, setPage] = useState(1);
  const [stateFilter, setStateFilter] = useState('');
  const [selected, setSelected] = useState<SecretScanningAlertItem | null>(null);

  const offset = (page - 1) * PAGE_SIZE;

  const { data: summary, isLoading: loadingSummary } = useQuery({
    queryKey: ['secret-scanning-summary'],
    queryFn: getSecretScanning,
    staleTime: 60_000,
  });

  const {
    data: alertsData,
    isLoading: loadingAlerts,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['secret-scanning-alerts', page, stateFilter],
    queryFn: () => getSecretScanningAlerts(PAGE_SIZE, offset, stateFilter || undefined),
    staleTime: 30_000,
  });

  const columns: ColumnDef<SecretScanningAlertItem>[] = useMemo(
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
        helpText: 'Current state of the alert (open, resolved, etc.)',
        render: (r) => <Label variant={stateVariant(r.state)}>{r.state}</Label>,
        sortValue: (r) => r.state,
        filterValue: (r) => r.state,
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
        key: 'resolved',
        header: 'Resolved',
        sortable: true,
        filterable: true,
        helpText: 'When the alert was resolved (if applicable)',
        render: (r) => (r.resolved_at ? formatRelativeShort(r.resolved_at) : '—'),
        sortValue: (r) => r.resolved_at ?? '',
        filterValue: (r) => r.resolved_at ?? '',
      },
    ],
    [],
  );

  return (
    <>
      <div className={styles.cardGrid}>
        {loadingSummary ? (
          <Spinner />
        ) : summary ? (
          <>
            <MetricCard
              value={String(summary.unresolved_total)}
              label="Open Alerts"
              helpText="Total unresolved secret scanning alerts"
            />
            <MetricCard
              value={String(summary.publicly_leaked)}
              label="Publicly Leaked"
              helpText="Secrets detected in publicly accessible locations"
              accent
            />
            <MetricCard
              value={String(summary.push_protection_bypassed_count)}
              label="Push Protection Bypassed"
              helpText="Alerts where push protection was explicitly bypassed"
            />
            <MetricCard
              value={String(Math.round(summary.mttr_hours))}
              label="MTTR (hours)"
              helpText="Mean time to resolve secret scanning alerts"
            />
            <MetricCard
              value={`${summary.resolution_rate_pct.toFixed(1)}%`}
              label="Resolution Rate"
              helpText="Percentage of total alerts that have been resolved"
            />
          </>
        ) : null}
      </div>

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
      </div>

      {loadingAlerts && (
        <div className={styles.center}>
          <Spinner />
        </div>
      )}
      {isError && (
        <ErrorBanner
          message="Failed to load secret scanning alerts"
          onRetry={() => void refetch()}
        />
      )}
      {alertsData && (
        <div className={styles.tableSection}>
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
          </>
        )}
      </Drawer>
    </>
  );
}

/* ── Code Scanning Tab ── */
function CodeScanningTab() {
  const [page, setPage] = useState(1);
  const [stateFilter, setStateFilter] = useState('');
  const [sevFilter, setSevFilter] = useState('');
  const [selected, setSelected] = useState<CodeScanningAlertItem | null>(null);

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
        helpText: 'Alert severity level',
        render: (r) =>
          r.security_severity ? (
            <Label variant={sevVariant(r.security_severity)}>{r.security_severity}</Label>
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
        helpText: 'Current state of the alert',
        render: (r) => <Label variant={stateVariant(r.state)}>{r.state}</Label>,
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
    [],
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
            />
            <MetricCard
              value={String(summary.critical_count)}
              label="Critical"
              helpText="Critical severity open alerts"
              accent
            />
            <MetricCard
              value={String(summary.high_count)}
              label="High"
              helpText="High severity open alerts"
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
            />
          </>
        ) : null}
      </div>

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
          <option value="fixed">Fixed</option>
          <option value="dismissed">Dismissed</option>
        </select>
        <select
          className={styles.filterSelect}
          value={sevFilter}
          onChange={(e) => {
            setSevFilter(e.target.value);
            setPage(1);
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
        <div className={styles.tableSection}>
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
  const [page, setPage] = useState(1);
  const [stateFilter, setStateFilter] = useState('');
  const [sevFilter, setSevFilter] = useState('');
  const [selected, setSelected] = useState<DependabotAlertItem | null>(null);

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
        helpText: 'Vulnerability severity level',
        render: (r) =>
          r.severity ? <Label variant={sevVariant(r.severity)}>{r.severity}</Label> : '—',
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
        helpText: 'Current state of the Dependabot alert',
        render: (r) => <Label variant={stateVariant(r.state)}>{r.state}</Label>,
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
    [],
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
            />
            <MetricCard
              value={String(summary.critical_open)}
              label="Critical Open"
              helpText="Critical severity open vulnerability alerts"
              accent
            />
            <MetricCard
              value={String(summary.high_open)}
              label="High Open"
              helpText="High severity open vulnerability alerts"
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
            />
          </>
        ) : null}
      </div>

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
          <option value="fixed">Fixed</option>
          <option value="dismissed">Dismissed</option>
        </select>
        <select
          className={styles.filterSelect}
          value={sevFilter}
          onChange={(e) => {
            setSevFilter(e.target.value);
            setPage(1);
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
        <div className={styles.tableSection}>
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
  const [page, setPage] = useState(1);

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
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get('tab') ?? 'overview';
  const activeTab: TabKey = TABS.some((t) => t.key === rawTab) ? (rawTab as TabKey) : 'overview';

  function setTab(tab: TabKey) {
    setSearchParams({ tab });
  }

  return (
    <div className={styles.splitLayout}>
      <div className={styles.splitMain}>
        <div className={styles.pageHeader}>
          <div className={styles.pageTitle}>Advanced Security</div>
          <div className={styles.pageSub}>
            GitHub Advanced Security alerts, trends, and GHAS-related threat detections
          </div>
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

        {activeTab === 'overview' && <OverviewTab />}
        {activeTab === 'secrets' && <SecretScanningTab />}
        {activeTab === 'code' && <CodeScanningTab />}
        {activeTab === 'dependabot' && <DependabotTab />}
        {activeTab === 'activity' && <ActivityLogTab />}
      </div>
    </div>
  );
}
