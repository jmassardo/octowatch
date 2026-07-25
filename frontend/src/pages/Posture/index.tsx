import { useState, useMemo, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { getPosture } from '../../api/posture';
import type { PostureResponse, PostureCheckResult, OrgPosture } from '../../api/posture';
import { getDetection } from '../../api/detections';
import { DetectionDetailPane } from '../Threats/DetectionDetailPane';
import { Drawer } from '../../components/primitives/Drawer';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Pagination } from '../../components/primitives/Pagination';
import { EmptyState } from '../../components/common/EmptyState';
import { PageHeader } from '../../components/common/PageHeader';
import { RadialGauge } from '../../components/charts/RadialGauge';
import { useChartColors } from '../../hooks/useChartColors';
import { useOrg } from '../../hooks/useOrg';
import { formatDateOnly } from '../../utils/dates';
import styles from './Posture.module.css';

/* ── Helpers ───────────────────────────────────────────────────────── */

function scoreColor(score: number) {
  if (score >= 80) return 'var(--success)';
  if (score >= 50) return 'var(--attention)';
  return 'var(--danger)';
}

function sevVariant(sev: string) {
  if (sev === 'critical') return 'danger' as const;
  if (sev === 'high') return 'severe' as const;
  if (sev === 'medium') return 'attention' as const;
  if (sev === 'info') return 'muted' as const;
  return 'success' as const;
}

function boolDisplay(
  val: boolean | null | undefined,
  trueLabel = 'Enabled',
  falseLabel = 'Disabled',
) {
  if (val === null || val === undefined) return 'Unknown';
  return val ? trueLabel : falseLabel;
}

/* ── Breadcrumb ────────────────────────────────────────────────────── */

function Breadcrumb({ items }: { items: PostureResponse['breadcrumb'] }) {
  return (
    <div className={styles.breadcrumb}>
      {items.map((item, i) => (
        <span key={i}>
          {i > 0 && <span className={styles.breadcrumbSep}> / </span>}
          {item.href ? <Link to={item.href}>{item.label}</Link> : <strong>{item.label}</strong>}
        </span>
      ))}
    </div>
  );
}

/* ── Check row ─────────────────────────────────────────────────────── */

function CheckRow({
  check,
  onSelect,
}: {
  check: PostureCheckResult;
  onSelect: (detectionId: number) => void;
}) {
  const passing = check.status === 'pass';
  return (
    <div
      className={styles.checkRow}
      role={check.detection_id ? 'button' : undefined}
      tabIndex={check.detection_id ? 0 : undefined}
      onClick={() => check.detection_id && onSelect(check.detection_id)}
      onKeyDown={(e) => {
        if (check.detection_id && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onSelect(check.detection_id);
        }
      }}
    >
      <span
        className={`${styles.checkIcon} ${passing ? styles.checkPass : styles.checkFail}`}
        title={passing ? 'Check is passing' : 'Check is failing'}
      >
        {passing ? '✓' : '✕'}
      </span>
      <div className={styles.checkInfo}>
        <span className={styles.checkTitle}>{check.title}</span>
        {!passing && check.description && (
          <span className={styles.checkDesc}>{check.description}</span>
        )}
      </div>
      <div className={styles.checkMeta}>
        <Label variant={sevVariant(check.severity)}>{check.severity}</Label>
        {passing ? (
          <Label variant="success">Passing</Label>
        ) : (
          <Label variant={sevVariant(check.severity)}>{check.status}</Label>
        )}
      </div>
    </div>
  );
}

/* ── Filter bar ────────────────────────────────────────────────────── */

function Filters({
  severity,
  setSeverity,
  statusFilter,
  setStatusFilter,
  showVisibility,
  visibility,
  setVisibility,
}: {
  severity: string;
  setSeverity: (v: string) => void;
  statusFilter: string;
  setStatusFilter: (v: string) => void;
  showVisibility?: boolean;
  visibility?: string;
  setVisibility?: (v: string) => void;
}) {
  return (
    <div className={styles.filters}>
      <select
        value={severity}
        onChange={(e) => setSeverity(e.target.value)}
        title="Filter checks by severity level"
      >
        <option value="">All severities</option>
        <option value="critical">Critical</option>
        <option value="high">High</option>
        <option value="medium">Medium</option>
        <option value="low">Low</option>
        <option value="info">Info</option>
      </select>
      <select
        value={statusFilter}
        onChange={(e) => setStatusFilter(e.target.value)}
        title="Filter by check pass/fail status"
      >
        <option value="">All statuses</option>
        <option value="fail">Failing</option>
        <option value="pass">Passing</option>
      </select>
      {showVisibility && setVisibility && (
        <select
          value={visibility}
          onChange={(e) => setVisibility(e.target.value)}
          title="Filter repositories by visibility type"
        >
          <option value="">All visibility</option>
          <option value="public">Public</option>
          <option value="private">Private</option>
          <option value="internal">Internal</option>
        </select>
      )}
    </div>
  );
}

function filterChecks(checks: PostureCheckResult[], severity: string, statusFilter: string) {
  let filtered = checks;
  if (severity) filtered = filtered.filter((c) => c.severity === severity);
  if (statusFilter === 'pass') filtered = filtered.filter((c) => c.status === 'pass');
  if (statusFilter === 'fail') filtered = filtered.filter((c) => c.status !== 'pass');
  return filtered;
}

/* ── Aggregate Metrics Helpers ──────────────────────────────────────── */

interface AggregateMetrics {
  totalOpen: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  secretScanningCoverage: number;
  codeScanningCoverage: number;
  dependabotCoverage: number;
}

function computeMetrics(orgs: OrgPosture[]): AggregateMetrics {
  const allChecks = orgs.flatMap((o) => o.checks);
  const failing = allChecks.filter((c) => c.status !== 'pass');

  const totalOpen = failing.length;
  const critical = failing.filter((c) => c.severity === 'critical').length;
  const high = failing.filter((c) => c.severity === 'high').length;
  const medium = failing.filter((c) => c.severity === 'medium').length;
  const low = failing.filter((c) => c.severity === 'low').length;

  // Coverage: check for feature-specific checks across all orgs
  const totalRepos = orgs.reduce((sum, o) => sum + (o.repo_summary?.total ?? 0), 0);

  function computeCoverage(keyword: string): number {
    if (totalRepos === 0) return 0;
    const relevantChecks = allChecks.filter(
      (c) =>
        c.title.toLowerCase().includes(keyword) ||
        c.category.toLowerCase().includes(keyword) ||
        c.rule_name.toLowerCase().includes(keyword),
    );
    if (relevantChecks.length === 0) return 0;
    const passing = relevantChecks.filter((c) => c.status === 'pass').length;
    return Math.round((passing / relevantChecks.length) * 100);
  }

  return {
    totalOpen,
    critical,
    high,
    medium,
    low,
    secretScanningCoverage: computeCoverage('secret scanning'),
    codeScanningCoverage: computeCoverage('code scanning'),
    dependabotCoverage: computeCoverage('dependabot'),
  };
}

/* ── Metrics Summary Bar ───────────────────────────────────────────── */

function MetricsSummary({
  metrics,
  onSeverityClick,
}: {
  metrics: AggregateMetrics;
  onSeverityClick?: (severity: string) => void;
}) {
  const clickable = onSeverityClick ? styles.metricClickable : '';
  return (
    <div className={styles.metricsSummary} data-testid="metrics-summary">
      <div
        className={`${styles.metricCard} ${clickable}`}
        onClick={() => onSeverityClick?.('')}
        role={onSeverityClick ? 'button' : undefined}
      >
        <div className={styles.metricValue}>{metrics.totalOpen}</div>
        <div className={styles.metricLabel}>Open Alerts</div>
      </div>
      <div
        className={`${styles.metricCard} ${clickable}`}
        onClick={() => onSeverityClick?.('critical')}
        role={onSeverityClick ? 'button' : undefined}
      >
        <div className={`${styles.metricValue} ${styles.metricCritical}`}>{metrics.critical}</div>
        <div className={styles.metricLabel}>Critical</div>
      </div>
      <div
        className={`${styles.metricCard} ${clickable}`}
        onClick={() => onSeverityClick?.('high')}
        role={onSeverityClick ? 'button' : undefined}
      >
        <div className={`${styles.metricValue} ${styles.metricHigh}`}>{metrics.high}</div>
        <div className={styles.metricLabel}>High</div>
      </div>
      <div
        className={`${styles.metricCard} ${clickable}`}
        onClick={() => onSeverityClick?.('medium')}
        role={onSeverityClick ? 'button' : undefined}
      >
        <div className={styles.metricValue}>{metrics.medium}</div>
        <div className={styles.metricLabel}>Medium</div>
      </div>
      <div
        className={`${styles.metricCard} ${clickable}`}
        onClick={() => onSeverityClick?.('low')}
        role={onSeverityClick ? 'button' : undefined}
      >
        <div className={styles.metricValue}>{metrics.low}</div>
        <div className={styles.metricLabel}>Low</div>
      </div>
      <div className={styles.metricCard}>
        <div className={styles.metricValue}>{metrics.secretScanningCoverage}%</div>
        <div className={styles.metricLabel}>Secret Scanning</div>
      </div>
      <div className={styles.metricCard}>
        <div className={styles.metricValue}>{metrics.codeScanningCoverage}%</div>
        <div className={styles.metricLabel}>Code Scanning</div>
      </div>
      <div className={styles.metricCard}>
        <div className={styles.metricValue}>{metrics.dependabotCoverage}%</div>
        <div className={styles.metricLabel}>Dependabot</div>
      </div>
    </div>
  );
}

/* ── Severity Distribution Chart ───────────────────────────────────── */

function SeverityDistributionChart({ metrics }: { metrics: AggregateMetrics }) {
  const colors = useChartColors();

  const chartData = [
    { value: metrics.critical, name: 'Critical' },
    { value: metrics.high, name: 'High' },
    { value: metrics.medium, name: 'Medium' },
    { value: metrics.low, name: 'Low' },
  ].filter((d) => d.value > 0);

  if (chartData.length === 0) {
    return (
      <div className={styles.chartPlaceholder} data-testid="severity-chart">
        <span className={styles.chartPlaceholderText}>No failing checks</span>
      </div>
    );
  }

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { color: colors.chartText, fontFamily: 'inherit' },
    tooltip: {
      trigger: 'item',
      backgroundColor: colors.chartTooltipBg,
      borderColor: colors.chartTooltipBorder,
      textStyle: { color: colors.chartTooltipFg, fontSize: 12 },
      formatter: '{b}: {c} ({d}%)',
    },
    legend: {
      orient: 'vertical',
      right: 10,
      top: 'center',
      textStyle: { color: colors.chartText, fontSize: 11 },
    },
    series: [
      {
        type: 'pie',
        radius: ['50%', '75%'],
        center: ['35%', '50%'],
        avoidLabelOverlap: false,
        label: { show: false },
        data: chartData,
        itemStyle: { borderRadius: 4, borderWidth: 2, borderColor: 'transparent' },
        color: ['var(--danger)', 'var(--severe)', 'var(--attention)', 'var(--success)'],
      },
    ],
  };

  return (
    <div data-testid="severity-chart">
      <div className={styles.sectionTitle}>Severity Distribution</div>
      <ReactECharts option={option} style={{ height: 180 }} opts={{ renderer: 'svg' }} />
    </div>
  );
}

/* ── Coverage Gauges ───────────────────────────────────────────────── */

function CoverageGauges({ metrics }: { metrics: AggregateMetrics }) {
  return (
    <div data-testid="coverage-gauges">
      <div className={styles.sectionTitle}>Feature Coverage</div>
      <div className={styles.coverageList}>
        <CoverageBar label="Secret Scanning" value={metrics.secretScanningCoverage} />
        <CoverageBar label="Code Scanning" value={metrics.codeScanningCoverage} />
        <CoverageBar label="Dependabot" value={metrics.dependabotCoverage} />
      </div>
    </div>
  );
}

function CoverageBar({ label, value }: { label: string; value: number }) {
  const barColor =
    value >= 80 ? 'var(--success)' : value >= 50 ? 'var(--attention)' : 'var(--danger)';
  return (
    <div className={styles.coverageItem}>
      <div className={styles.coverageHeader}>
        <span className={styles.coverageLabel}>{label}</span>
        <span className={styles.coverageValue}>{value}%</span>
      </div>
      <div className={styles.coverageTrack}>
        <div className={styles.coverageFill} style={{ width: `${value}%`, background: barColor }} />
      </div>
    </div>
  );
}

/* ── Organization Multi-Select Filter ──────────────────────────────── */

/* ── Enterprise View ───────────────────────────────────────────────── */

function EnterpriseView({
  data,
  search,
  setSearch,
  page,
  setPage,
  onSelectDetection,
}: {
  data: PostureResponse;
  search: string;
  setSearch: (v: string) => void;
  page: number;
  setPage: (p: number) => void;
  onSelectDetection: (detectionId: number) => void;
}) {
  const navigate = useNavigate();
  const { selectedOrg } = useOrg();
  const [severity, setSeverity] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [orgsExpanded, setOrgsExpanded] = useState(true);
  const [findingsPage, setFindingsPage] = useState(1);
  const FINDINGS_PAGE_SIZE = 20;
  const orgs = useMemo(() => data.orgs ?? [], [data.orgs]);

  const filteredOrgsForMetrics = useMemo(() => {
    if (!selectedOrg) return orgs;
    return orgs.filter((o) => o.org_login === selectedOrg);
  }, [orgs, selectedOrg]);

  const metrics = useMemo(() => computeMetrics(filteredOrgsForMetrics), [filteredOrgsForMetrics]);

  const orgLabel = selectedOrg || 'All Organizations';

  // Empty state — distinguish "no sync yet" vs "synced but no orgs found"
  if (orgs.length === 0) {
    const hasSynced = data.last_sync_at !== null;
    const emptyTitle = hasSynced ? 'No organizations found' : 'No posture data available yet';
    const emptyDescription = hasSynced
      ? 'An enterprise sync has completed but no organizations were returned. This may indicate a permissions issue or that your enterprise has no organizations configured.'
      : 'Security posture data will appear here after your first enterprise sync completes. Run a sync from Settings to populate organization and repository data.';

    return (
      <>
        <div className={styles.header}>
          <RadialGauge value={data.score} label="Overall Security Posture" size={120} />
          <div className={styles.headerInfo}>
            <div className={styles.headerTitle}>Enterprise Security Posture</div>
            <div className={styles.headerSub}>
              {hasSynced
                ? `0 orgs · Last synced ${formatDateOnly(data.last_sync_at)}`
                : 'No sync performed yet'}
            </div>
          </div>
        </div>
        <div className={styles.content}>
          <EmptyState
            icon={hasSynced ? '🔍' : '🛡️'}
            title={emptyTitle}
            description={emptyDescription}
          />
        </div>
      </>
    );
  }

  const filteredOrgs = orgs.filter((o) => {
    if (statusFilter === 'fail' && o.score >= 80) return false;
    if (statusFilter === 'pass' && o.score < 80) return false;
    if (selectedOrg && o.org_login !== selectedOrg) return false;
    return true;
  });

  return (
    <>
      <div className={styles.header}>
        <RadialGauge value={data.score} label="Overall Security Posture" size={120} />
        <div className={styles.headerInfo}>
          <div className={styles.headerTitle}>Enterprise Security Posture</div>
          <div className={styles.headerSub}>
            {orgLabel} · {data.total} org{data.total !== 1 ? 's' : ''} · Last synced{' '}
            {formatDateOnly(data.last_sync_at)}
          </div>
        </div>
      </div>
      <div className={styles.content}>
        {/* Metrics Summary Bar — clickable to filter */}
        <MetricsSummary metrics={metrics} onSeverityClick={setSeverity} />

        {/* Severity Distribution + Coverage Gauges */}
        <div className={styles.chartsRow}>
          <div className={styles.chartPanel}>
            <SeverityDistributionChart metrics={metrics} />
          </div>
          <div className={styles.chartPanel}>
            <CoverageGauges metrics={metrics} />
          </div>
        </div>

        {/* Filters */}
        <div className={styles.filters}>
          <input
            type="text"
            placeholder="Search organizations..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            title="Search organizations by name"
            style={{
              padding: '4px 8px',
              borderRadius: 6,
              border: '1px solid var(--border)',
              background: 'var(--canvas-subtle)',
              color: 'var(--fg)',
              fontSize: 13,
              width: 220,
            }}
          />
        </div>
        <Filters
          severity={severity}
          setSeverity={setSeverity}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
        />

        {/* Top findings across enterprise */}
        {(() => {
          const allChecks = filteredOrgs.flatMap((o) =>
            o.checks.filter((c) => c.status !== 'pass'),
          );
          const sorted = allChecks
            .filter((c) => !severity || c.severity === severity)
            .sort((a, b) => {
              const w: Record<string, number> = {
                critical: 0,
                high: 1,
                medium: 2,
                low: 3,
                info: 4,
              };
              return (w[a.severity] ?? 5) - (w[b.severity] ?? 5);
            });
          if (!sorted.length) return null;
          const findingsOffset = (findingsPage - 1) * FINDINGS_PAGE_SIZE;
          const paginatedFindings = sorted.slice(
            findingsOffset,
            findingsOffset + FINDINGS_PAGE_SIZE,
          );
          return (
            <div className={styles.section}>
              <div
                className={styles.sectionTitle}
                title="Highest-severity failing checks across all organizations"
              >
                Top Findings ({sorted.length})
              </div>
              <div className={styles.checkList}>
                {paginatedFindings.map((c, i) => (
                  <CheckRow
                    key={`${c.rule_id}-${findingsOffset + i}`}
                    check={c}
                    onSelect={onSelectDetection}
                  />
                ))}
              </div>
              {sorted.length > FINDINGS_PAGE_SIZE && (
                <Pagination
                  page={findingsPage}
                  pageSize={FINDINGS_PAGE_SIZE}
                  total={sorted.length}
                  hasNext={findingsOffset + FINDINGS_PAGE_SIZE < sorted.length}
                  onPageChange={setFindingsPage}
                />
              )}
            </div>
          );
        })()}

        {/* Collapsible Organizations Grid */}
        <div className={styles.section}>
          <button
            type="button"
            className={styles.sectionToggle}
            onClick={() => setOrgsExpanded((v) => !v)}
            aria-expanded={orgsExpanded}
          >
            {orgsExpanded ? '▾' : '▸'} Organizations ({filteredOrgs.length})
          </button>
          {orgsExpanded && (
            <>
              <div className={styles.orgGrid}>
                {filteredOrgs.map((org) => (
                  <div
                    key={org.org_login}
                    className={styles.orgCard}
                    onClick={() => navigate(`/posture/${org.org_login}`)}
                    title={`View posture details for ${org.org_login}`}
                  >
                    <div className={styles.orgCardHeader}>
                      <span className={styles.orgName}>{org.org_login}</span>
                      <span
                        className={styles.orgMiniScore}
                        style={{ color: scoreColor(org.score) }}
                        title={`Security score: ${Math.round(org.score)}/100`}
                      >
                        {Math.round(org.score)}
                      </span>
                    </div>
                    <div
                      className={styles.scoreBar}
                      title={`Score: ${Math.round(org.score)}% — green ≥ 80, yellow ≥ 50, red < 50`}
                    >
                      <div
                        className={styles.scoreBarFill}
                        style={{ width: `${org.score}%`, background: scoreColor(org.score) }}
                      />
                    </div>
                    <div className={styles.orgMeta}>
                      {org.two_factor_required == null && org.default_repo_permission == null && (
                        <span
                          style={{ color: 'var(--attention)', fontStyle: 'italic', fontSize: 11 }}
                        >
                          Config not synced
                        </span>
                      )}
                      {org.repo_summary && (
                        <>
                          <span>{org.repo_summary.total} repos</span>
                          {org.repo_summary.failing > 0 && (
                            <span style={{ color: 'var(--danger)' }}>
                              {org.repo_summary.failing} failing
                            </span>
                          )}
                          {org.repo_summary.warning > 0 && (
                            <span style={{ color: 'var(--attention)' }}>
                              {org.repo_summary.warning} warning
                            </span>
                          )}
                          <span style={{ color: 'var(--success)' }}>
                            {org.repo_summary.passing} passing
                          </span>
                        </>
                      )}
                    </div>
                    {severity && (
                      <div style={{ marginTop: 8, fontSize: 12, color: 'var(--fg-muted)' }}>
                        {
                          org.checks.filter((c) => c.severity === severity && c.status !== 'pass')
                            .length
                        }{' '}
                        {severity} finding(s)
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <Pagination
                page={page}
                pageSize={data.page_size}
                total={data.total}
                hasNext={data.has_next}
                onPageChange={setPage}
              />
            </>
          )}
        </div>
      </div>
    </>
  );
}

/* ── Org View ──────────────────────────────────────────────────────── */

function OrgView({
  data,
  search,
  setSearch,
  page,
  setPage,
  onNavigate,
  onSelectDetection,
}: {
  data: PostureResponse;
  search: string;
  setSearch: (v: string) => void;
  page: number;
  setPage: (p: number) => void;
  onNavigate: () => void;
  onSelectDetection: (detectionId: number) => void;
}) {
  const navigate = useNavigate();
  const org = data.org!;
  const [severity, setSeverity] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [visibility, setVisibility] = useState('');
  const [sortCol, setSortCol] = useState<'name' | 'score' | 'visibility'>('score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const toggleSort = (col: typeof sortCol) => {
    if (sortCol === col) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortCol(col);
      setSortDir(col === 'score' ? 'asc' : 'asc');
    }
  };

  const checks = filterChecks(org.checks, severity, statusFilter);
  let repos = org.repos ?? [];
  if (visibility) repos = repos.filter((r) => r.visibility === visibility);
  if (severity) repos = repos.filter((r) => r.checks.some((c) => c.severity === severity));
  if (statusFilter === 'pass')
    repos = repos.filter((r) => r.checks.every((c) => c.status === 'pass'));
  if (statusFilter === 'fail')
    repos = repos.filter((r) => r.checks.some((c) => c.status !== 'pass'));
  repos = [...repos].sort((a, b) => {
    const dir = sortDir === 'asc' ? 1 : -1;
    if (sortCol === 'score') return (a.score - b.score) * dir;
    if (sortCol === 'visibility')
      return (a.visibility ?? '').localeCompare(b.visibility ?? '') * dir;
    return a.repo_name.localeCompare(b.repo_name) * dir;
  });

  return (
    <>
      <div className={styles.header}>
        <RadialGauge value={org.score} label="Organization Score" size={100} />
        <div className={styles.headerInfo}>
          <div className={styles.headerTitle}>{org.org_login}</div>
          <div className={styles.headerSub}>
            {(org.repos ?? []).length} repos · Last synced {formatDateOnly(data.last_sync_at)}
          </div>
        </div>
      </div>
      <div className={styles.content}>
        {/* Org metadata */}
        <div className={styles.metaCard}>
          <div className={styles.metaGrid}>
            <div
              className={styles.metaItem}
              title="Whether two-factor authentication is required for all org members"
            >
              <div className={styles.metaLabel}>2FA Required</div>
              <div className={styles.metaValue}>
                {boolDisplay(org.two_factor_required, 'Required', 'Not Required')}
              </div>
            </div>
            <div
              className={styles.metaItem}
              title="The default permission level granted to members on new repositories"
            >
              <div className={styles.metaLabel}>Default Repo Permission</div>
              <div className={styles.metaValue}>{org.default_repo_permission ?? 'Unknown'}</div>
            </div>
            <div
              className={styles.metaItem}
              title="Whether org members can fork private repositories"
            >
              <div className={styles.metaLabel}>Private Fork</div>
              <div className={styles.metaValue}>
                {boolDisplay(org.members_can_fork_private_repos, 'Allowed', 'Blocked')}
              </div>
            </div>
            <div
              className={styles.metaItem}
              title="Whether org members can create public repositories"
            >
              <div className={styles.metaLabel}>Public Repo Creation</div>
              <div className={styles.metaValue}>
                {boolDisplay(org.members_can_create_public_repos, 'Allowed', 'Blocked')}
              </div>
            </div>
            <div
              className={styles.metaItem}
              title="Whether an IP allow-list restricts access to org resources"
            >
              <div className={styles.metaLabel}>IP Allow List</div>
              <div className={styles.metaValue}>{boolDisplay(org.ip_allow_list_enabled)}</div>
            </div>
          </div>
        </div>

        {/* Org-level checks */}
        <div className={styles.section}>
          <div
            className={styles.sectionTitle}
            title="Security policy checks evaluated at the organization level"
          >
            Organization Security Checks
          </div>
          <Filters
            severity={severity}
            setSeverity={setSeverity}
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
          />
          <div className={styles.checkList}>
            {checks.map((c, i) => (
              <CheckRow key={`${c.rule_id}-${i}`} check={c} onSelect={onSelectDetection} />
            ))}
            {checks.length === 0 && <div className={styles.empty}>No checks match filters</div>}
          </div>
        </div>

        {/* Repos table */}
        <div className={styles.section}>
          <div
            className={styles.sectionTitle}
            title="All repositories in this organization with their security posture"
          >
            Repositories
          </div>
          <div className={styles.filters}>
            <input
              type="text"
              placeholder="Search repositories..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                padding: '4px 8px',
                borderRadius: 6,
                border: '1px solid var(--border)',
                background: 'var(--canvas-subtle)',
                color: 'var(--fg)',
                fontSize: 13,
                width: 220,
              }}
            />
          </div>
          <Filters
            severity={severity}
            setSeverity={setSeverity}
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
            showVisibility
            visibility={visibility}
            setVisibility={setVisibility}
          />
          <table className={styles.repoTable}>
            <thead>
              <tr>
                <th scope="col" onClick={() => toggleSort('name')} title="Sort by repository name">
                  Repository {sortCol === 'name' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </th>
                <th
                  scope="col"
                  onClick={() => toggleSort('score')}
                  title="Weighted security score (0–100). Click to sort."
                >
                  Score {sortCol === 'score' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </th>
                <th
                  scope="col"
                  onClick={() => toggleSort('visibility')}
                  title="Repository visibility: public, private, or internal"
                >
                  Visibility {sortCol === 'visibility' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </th>
                <th scope="col" title="Number of passing and failing security checks">
                  Checks
                </th>
                <th scope="col" title="Number of detection rules that have triggered for this repo">
                  Detections
                </th>
              </tr>
            </thead>
            <tbody>
              {repos.map((r) => {
                const failing = r.checks.filter((c) => c.status !== 'pass').length;
                const passing = r.checks.filter((c) => c.status === 'pass').length;
                return (
                  <tr
                    key={r.repo_name}
                    onClick={() => {
                      onNavigate();
                      navigate(`/posture/${r.org}/${r.repo_name}`);
                    }}
                  >
                    <td>
                      <span className={styles.repoName}>{r.repo_name}</span>
                      {r.archived && (
                        <span style={{ marginLeft: 6 }}>
                          <Label variant="muted">archived</Label>
                        </span>
                      )}
                      {r.fork && (
                        <span style={{ marginLeft: 6 }}>
                          <Label variant="muted">fork</Label>
                        </span>
                      )}
                    </td>
                    <td>
                      <span style={{ color: scoreColor(r.score), fontWeight: 600 }}>
                        {Math.round(r.score)}
                      </span>
                    </td>
                    <td>
                      <Label variant={r.visibility === 'public' ? 'attention' : 'muted'}>
                        {r.visibility ?? '—'}
                      </Label>
                    </td>
                    <td>
                      <span style={{ color: 'var(--success)' }}>{passing}✓</span>
                      {failing > 0 && (
                        <span style={{ color: 'var(--danger)', marginLeft: 6 }}>{failing}✕</span>
                      )}
                    </td>
                    <td>{r.detection_count || '—'}</td>
                  </tr>
                );
              })}
              {repos.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.empty}>
                    No repositories found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <Pagination
            page={page}
            pageSize={data.page_size}
            total={data.total}
            hasNext={data.has_next}
            onPageChange={setPage}
          />
        </div>
      </div>
    </>
  );
}

/* ── Repo View ─────────────────────────────────────────────────────── */

function RepoView({
  data,
  onSelectDetection,
}: {
  data: PostureResponse;
  onSelectDetection: (detectionId: number) => void;
}) {
  const repo = data.repo!;
  const [severity, setSeverity] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const checks = filterChecks(repo.checks, severity, statusFilter);

  return (
    <>
      <div className={styles.header}>
        <RadialGauge value={repo.score} label="Repository Score" size={100} />
        <div className={styles.headerInfo}>
          <div className={styles.headerTitle}>{repo.repo_name}</div>
          <div className={styles.headerSub}>
            {repo.org} · Last synced {formatDateOnly(data.last_sync_at)}
          </div>
        </div>
      </div>
      <div className={styles.content}>
        {/* Repo metadata */}
        <div className={styles.metaCard}>
          <div className={styles.metaGrid}>
            <div
              className={styles.metaItem}
              title="Whether this repository is public, private, or internal"
            >
              <div className={styles.metaLabel}>Visibility</div>
              <div className={styles.metaValue}>{repo.visibility ?? 'Unknown'}</div>
            </div>
            <div
              className={styles.metaItem}
              title="The branch used as the default for pull requests and code browsing"
            >
              <div className={styles.metaLabel}>Default Branch</div>
              <div className={styles.metaValue}>{repo.default_branch ?? '—'}</div>
            </div>
            <div
              className={styles.metaItem}
              title="Primary programming language detected in this repository"
            >
              <div className={styles.metaLabel}>Language</div>
              <div className={styles.metaValue}>{repo.language ?? '—'}</div>
            </div>
            <div className={styles.metaItem} title="Date of the most recent push to any branch">
              <div className={styles.metaLabel}>Last Push</div>
              <div className={styles.metaValue}>{formatDateOnly(repo.pushed_at)}</div>
            </div>
            <div
              className={styles.metaItem}
              title="Whether this repository has been archived and is read-only"
            >
              <div className={styles.metaLabel}>Archived</div>
              <div className={styles.metaValue}>{repo.archived ? 'Yes' : 'No'}</div>
            </div>
            <div
              className={styles.metaItem}
              title="Whether this repository is a fork of another repository"
            >
              <div className={styles.metaLabel}>Fork</div>
              <div className={styles.metaValue}>{repo.fork ? 'Yes' : 'No'}</div>
            </div>
          </div>
        </div>

        {/* All checks */}
        <div className={styles.section}>
          <div
            className={styles.sectionTitle}
            title="Security configuration checks evaluated for this repository"
          >
            Security Checks
          </div>
          <Filters
            severity={severity}
            setSeverity={setSeverity}
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
          />
          <div className={styles.checkList}>
            {checks.map((c, i) => (
              <CheckRow key={`${c.rule_id}-${i}`} check={c} onSelect={onSelectDetection} />
            ))}
            {checks.length === 0 && <div className={styles.empty}>No checks match filters</div>}
          </div>
        </div>
      </div>
    </>
  );
}

/* ── Main Page ─────────────────────────────────────────────────────── */

export function PosturePage() {
  const { org, repo } = useParams<{ org?: string; repo?: string }>();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [selectedDetectionId, setSelectedDetectionId] = useState<number | null>(null);

  const PAGE_SIZE = 20;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['posture', org ?? '', repo ?? '', page, search],
    queryFn: () =>
      getPosture({ org, repo, search: search || undefined, page, page_size: PAGE_SIZE }),
  });

  // Fetch detection details when a finding is selected
  const { data: selectedDetection } = useQuery({
    queryKey: ['detection-detail', selectedDetectionId],
    queryFn: () => getDetection(selectedDetectionId!),
    enabled: selectedDetectionId !== null,
  });

  const handleSelectDetection = useCallback((detectionId: number) => {
    setSelectedDetectionId(detectionId);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setSelectedDetectionId(null);
  }, []);

  // Reset page when navigating to different level
  const resetPage = () => {
    setPage(1);
    setSearch('');
  };

  const pageHeader = (
    <PageHeader
      title="Security Posture"
      description="Review enterprise, organization, and repository security posture"
      showHelp
    />
  );

  if (isLoading)
    return (
      <div className={styles.page}>
        {pageHeader}
        <div className={styles.loading}>
          <Spinner />
        </div>
      </div>
    );
  if (isError || !data)
    return (
      <div className={styles.page}>
        {pageHeader}
        <div className={styles.content}>
          <ErrorBanner message="Failed to load posture data" onRetry={refetch} />
        </div>
      </div>
    );

  return (
    <div className={styles.page}>
      {pageHeader}
      <Breadcrumb items={data.breadcrumb} />
      {data.level === 'enterprise' && (
        <EnterpriseView
          data={data}
          search={search}
          setSearch={(v) => {
            setSearch(v);
            setPage(1);
          }}
          page={page}
          setPage={setPage}
          onSelectDetection={handleSelectDetection}
        />
      )}
      {data.level === 'org' && (
        <OrgView
          data={data}
          search={search}
          setSearch={(v) => {
            setSearch(v);
            setPage(1);
          }}
          page={page}
          setPage={setPage}
          onNavigate={resetPage}
          onSelectDetection={handleSelectDetection}
        />
      )}
      {data.level === 'repo' && <RepoView data={data} onSelectDetection={handleSelectDetection} />}

      <Drawer
        open={selectedDetection != null}
        onClose={handleCloseDetail}
        title="Detection Details"
      >
        {selectedDetection && (
          <DetectionDetailPane
            selected={selectedDetection}
            actorSuggestions={[]}
            onClose={handleCloseDetail}
            onDeleted={handleCloseDetail}
          />
        )}
      </Drawer>
    </div>
  );
}
