import { useState, useCallback, useEffect, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getMauReport,
  getSeatUtilizationReport,
  getActionsVolumeReport,
  getCopilotSeatsReport,
  getRepoCreationRateReport,
  getPatCountsReport,
  getWebhookCountsReport,
  getCodespaceHoursReport,
  exportReport,
  getReportCatalog,
  listCustomReports,
  listSharedReports,
  deleteCustomReport,
  shareCustomReport,
} from '../../api/reports';
import { useOrg } from '../../hooks/useOrg';
import { useToast } from '../../hooks/useToast';
import { PageHeader } from '../../components/common/PageHeader';
import { SkeletonCard } from '../../components/common/SkeletonCard';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Drawer } from '../../components/primitives/Drawer';
import { Modal } from '../../components/primitives/Modal';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { ReportConfigPanel } from './ReportConfigPanel';
import { ReportBuilder } from './ReportBuilder';
import type {
  ReportParams,
  ReportTab,
  ReportCatalogEntry,
  CustomReport,
  ReportTemplate,
} from '../../types/reports';
import { formatDateOnly } from '../../utils/dates';
import { useEnumQueryParam, useQueryParam } from '../../hooks/useQueryParam';
import styles from './Reports.module.css';

/**
 * Unified row type for the reports table. Combines templates, catalog entries,
 * and custom/shared reports into a single renderable format.
 */
interface ReportTableRow {
  /** Unique identifier for the row */
  id: string;
  /** Display name of the report */
  name: string;
  /** Description or category */
  description: string;
  /** Report type for data lookup */
  type: string;
  /** Last run / generated date */
  lastRun: string | null;
  /** Schedule indicator */
  schedule: string;
  /** Current status */
  status: string;
  /** Source kind for determining drawer behavior */
  source: 'template' | 'catalog' | 'custom' | 'shared';
  /** Original template (if source is 'template') */
  templateRef?: ReportTemplate;
  /** Original catalog entry (if source is 'catalog') */
  catalogRef?: ReportCatalogEntry;
  /** Original custom report (if source is 'custom' or 'shared') */
  customRef?: CustomReport;
}

const REPORT_TEMPLATES: ReportTemplate[] = [
  {
    id: 'security-posture',
    type: 'soc2',
    title: 'Security Posture Report',
    description:
      'Comprehensive security posture overview including code scanning alerts, secret scanning, and dependency vulnerabilities.',
    category: 'Security',
    data_source: 'Audit Events (Compliance)',
    tags: ['security', 'compliance'],
  },
  {
    id: 'compliance',
    type: 'iso27001',
    title: 'Compliance Report',
    description:
      'ISO 27001 Annex A controls evidence report covering access control, operations security, and incident management.',
    category: 'Compliance',
    data_source: 'Audit Events (Compliance)',
    tags: ['compliance', 'iso27001'],
  },
  {
    id: 'detection-summary',
    type: 'nist-csf',
    title: 'Detection Summary Report',
    description:
      'Summary of security detections across NIST CSF functions: Identify, Protect, Detect, Respond, Recover.',
    category: 'Security',
    data_source: 'Audit Events (Compliance)',
    tags: ['security', 'detections'],
  },
  {
    id: 'user-activity',
    type: 'mau',
    title: 'User Activity Report',
    description: 'Monthly active users and actor activity trends derived from audit log events.',
    category: 'Usage',
    data_source: 'Audit Events',
    tags: ['usage', 'activity'],
  },
  {
    id: 'copilot-usage',
    type: 'copilot-seats',
    title: 'Copilot Usage Report',
    description:
      'Copilot seat assignments, revocations, and net change trends for license optimization.',
    category: 'Usage',
    data_source: 'Audit Events (Copilot)',
    tags: ['copilot', 'licensing'],
  },
  {
    id: 'workflow-health',
    type: 'actions-volume',
    title: 'Workflow Health Report',
    description:
      'GitHub Actions workflow run volume, success rates, and CI/CD pipeline health metrics.',
    category: 'DevOps',
    data_source: 'Audit Events',
    tags: ['ci-cd', 'actions'],
  },
  {
    id: 'access-review',
    type: 'pat-counts',
    title: 'Access Review Report',
    description:
      'Personal access token lifecycle events, creation and revocation patterns for access governance.',
    category: 'Security',
    data_source: 'Audit Events',
    tags: ['security', 'tokens'],
  },
  {
    id: 'org-comparison',
    type: 'seat-utilization',
    title: 'Org Comparison Report',
    description:
      'Cross-organization comparison of seat utilization, active users, and platform adoption metrics.',
    category: 'Usage',
    data_source: 'Audit Events',
    tags: ['licensing', 'platform'],
  },
];

export function ReportsPage() {
  const { selectedOrg } = useOrg();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useEnumQueryParam(
    'tab',
    ['templates', 'my-reports', 'shared', 'recent'] as const,
    'templates',
  );
  const [windowDaysStr, setWindowDaysStr] = useQueryParam('days', '30');
  const windowDays = ([30, 60, 90] as const).includes(Number(windowDaysStr) as 30 | 60 | 90)
    ? (Number(windowDaysStr) as 30 | 60 | 90)
    : 30;
  const setWindowDays = useCallback(
    (v: 30 | 60 | 90) => setWindowDaysStr(String(v), { replace: true }),
    [setWindowDaysStr],
  );

  // Deep-linking: selected report ID from URL query param
  const [selectedReportId, setSelectedReportId] = useQueryParam('report', '');

  const [showBuilder, setShowBuilder] = useState(false);
  const [shareModalReport, setShareModalReport] = useState<CustomReport | null>(null);
  const [shareLogins, setShareLogins] = useState('');
  const params: ReportParams = { window_days: windowDays, granularity: 'daily' };

  const {
    data: mauData,
    isLoading: mauLoading,
    isError: mauError,
  } = useQuery({
    queryKey: ['reports', 'mau', windowDays],
    queryFn: () => getMauReport(params),
  });

  const { data: actionsData, isLoading: actionsLoading } = useQuery({
    queryKey: ['reports', 'actions-volume', windowDays],
    queryFn: () => getActionsVolumeReport(params),
  });

  const { data: seatData } = useQuery({
    queryKey: ['reports', 'seat-utilization', windowDays],
    queryFn: () => getSeatUtilizationReport(params),
  });

  const { data: copilotData } = useQuery({
    queryKey: ['reports', 'copilot-seats', windowDays],
    queryFn: () => getCopilotSeatsReport(params),
  });

  const {
    data: repoCreationData,
    isLoading: repoCreationLoading,
    isError: repoCreationError,
  } = useQuery({
    queryKey: ['reports', 'repo-creation-rate', windowDays],
    queryFn: () => getRepoCreationRateReport(params),
  });

  const {
    data: patCountsData,
    isLoading: patCountsLoading,
    isError: patCountsError,
  } = useQuery({
    queryKey: ['reports', 'pat-counts', windowDays],
    queryFn: () => getPatCountsReport(params),
  });

  const {
    data: webhookCountsData,
    isLoading: webhookCountsLoading,
    isError: webhookCountsError,
  } = useQuery({
    queryKey: ['reports', 'webhook-counts', windowDays],
    queryFn: () => getWebhookCountsReport(params),
  });

  const {
    data: codespaceHoursData,
    isLoading: codespaceHoursLoading,
    isError: codespaceHoursError,
  } = useQuery({
    queryKey: ['reports', 'codespace-hours', windowDays],
    queryFn: () => getCodespaceHoursReport(params),
  });

  const { data: catalogData, isLoading: catalogLoading } = useQuery({
    queryKey: ['reports', 'catalog'],
    queryFn: getReportCatalog,
  });

  const { data: customReports, isLoading: customReportsLoading } = useQuery({
    queryKey: ['custom-reports'],
    queryFn: listCustomReports,
  });

  const { data: sharedReports, isLoading: sharedReportsLoading } = useQuery({
    queryKey: ['shared-reports'],
    queryFn: listSharedReports,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCustomReport,
    onSuccess: () => {
      showToast('Report deleted', 'success');
      void queryClient.invalidateQueries({ queryKey: ['custom-reports'] });
    },
    onError: () => {
      showToast('Failed to delete report', 'error');
    },
  });

  const shareMutation = useMutation({
    mutationFn: ({ reportId, logins }: { reportId: number; logins: string[] }) =>
      shareCustomReport(reportId, { logins }),
    onSuccess: () => {
      showToast('Report shared successfully', 'success');
      setShareModalReport(null);
      setShareLogins('');
      void queryClient.invalidateQueries({ queryKey: ['custom-reports'] });
    },
    onError: () => {
      showToast('Failed to share report', 'error');
    },
  });

  const handleShare = useCallback(() => {
    if (!shareModalReport || !shareLogins.trim()) return;
    const logins = shareLogins
      .split(',')
      .map((l) => l.trim())
      .filter((l) => l.length > 0);
    if (logins.length === 0) return;
    shareMutation.mutate({ reportId: shareModalReport.id, logins });
  }, [shareModalReport, shareLogins, shareMutation]);

  // Report data map for template/catalog reports
  const reportDataMap: Record<
    string,
    { title: string; dataSource: string; data: readonly Record<string, unknown>[] | undefined }
  > = useMemo(
    () => ({
      mau: {
        title: 'Monthly Active Users',
        dataSource: mauData?.data_source ?? 'Audit Events',
        data: mauData?.data,
      },
      'actions-volume': {
        title: 'Actions Volume',
        dataSource: actionsData?.data_source ?? 'Audit Events',
        data: actionsData?.data,
      },
      'seat-utilization': {
        title: 'Platform Seat Utilization',
        dataSource: seatData?.data_source ?? 'Audit Events',
        data: seatData?.data,
      },
      'copilot-seats': {
        title: 'Copilot Seats',
        dataSource: copilotData?.data_source ?? 'Audit Events (Copilot)',
        data: copilotData?.data,
      },
      'repo-creation-rate': {
        title: 'Repo Creation Rate',
        dataSource: repoCreationData?.data_source ?? 'Audit Events',
        data: repoCreationData?.data,
      },
      'pat-counts': {
        title: 'Personal Access Token Counts',
        dataSource: patCountsData?.data_source ?? 'Audit Events',
        data: patCountsData?.data,
      },
      'webhook-counts': {
        title: 'Webhook Counts',
        dataSource: webhookCountsData?.data_source ?? 'Audit Events',
        data: webhookCountsData?.data,
      },
      'codespace-hours': {
        title: 'Codespace Hours',
        dataSource: codespaceHoursData?.data_source ?? 'Audit Events',
        data: codespaceHoursData?.data,
      },
    }),
    [
      mauData,
      actionsData,
      seatData,
      copilotData,
      repoCreationData,
      patCountsData,
      webhookCountsData,
      codespaceHoursData,
    ],
  );

  // Build unified table rows for each tab
  const templateRows: ReportTableRow[] = useMemo(() => {
    const rows: ReportTableRow[] = REPORT_TEMPLATES.map((tmpl) => ({
      id: `tmpl-${tmpl.id}`,
      name: tmpl.title,
      description: tmpl.description,
      type: tmpl.type,
      lastRun: null,
      schedule: '—',
      status: 'available',
      source: 'template' as const,
      templateRef: tmpl,
    }));

    for (const r of catalogData ?? []) {
      rows.push({
        id: `cat-${r.id}`,
        name: r.title,
        description: r.description ?? '',
        type: r.type,
        lastRun: r.generated_at,
        schedule: '—',
        status: r.status,
        source: 'catalog' as const,
        catalogRef: r,
      });
    }

    return rows;
  }, [catalogData]);

  const customRows: ReportTableRow[] = useMemo(
    () =>
      (customReports ?? []).map((r) => ({
        id: `custom-${r.id}`,
        name: r.name,
        description: r.description ?? '',
        type: r.data_sources.join(', '),
        lastRun: r.last_run_at,
        schedule: '—',
        status: r.is_shared ? 'shared' : 'active',
        source: 'custom' as const,
        customRef: r,
      })),
    [customReports],
  );

  const sharedRows: ReportTableRow[] = useMemo(
    () =>
      (sharedReports ?? []).map((r) => ({
        id: `shared-${r.id}`,
        name: r.name,
        description: r.description ?? '',
        type: r.data_sources.join(', '),
        lastRun: r.last_run_at,
        schedule: '—',
        status: `shared by ${r.owner_login}`,
        source: 'shared' as const,
        customRef: r,
      })),
    [sharedReports],
  );

  const recentRows: ReportTableRow[] = useMemo(() => {
    const combined = [...(customReports ?? []), ...(sharedReports ?? [])]
      .filter((r) => r.last_run_at)
      .sort((a, b) => {
        const aDate = a.last_run_at ? new Date(a.last_run_at).getTime() : 0;
        const bDate = b.last_run_at ? new Date(b.last_run_at).getTime() : 0;
        return bDate - aDate;
      })
      .slice(0, 20);

    return combined.map((r) => ({
      id: `recent-${r.id}`,
      name: r.name,
      description: r.description ?? '',
      type: r.data_sources.join(', '),
      lastRun: r.last_run_at,
      schedule: '—',
      status: r.owner_login ? `by ${r.owner_login}` : 'active',
      source: (r.is_shared ? 'shared' : 'custom') as 'shared' | 'custom',
      customRef: r,
    }));
  }, [customReports, sharedReports]);

  // Determine which rows to display for the active tab
  const activeRows: ReportTableRow[] = useMemo(() => {
    switch (activeTab) {
      case 'templates':
        return templateRows;
      case 'my-reports':
        return customRows;
      case 'shared':
        return sharedRows;
      case 'recent':
        return recentRows;
      default:
        return [];
    }
  }, [activeTab, templateRows, customRows, sharedRows, recentRows]);

  // Table column definitions for the unified reports table
  const tableColumns: ColumnDef<ReportTableRow>[] = useMemo(
    () => [
      {
        key: 'name',
        header: 'Report Name',
        sortable: true,
        filterable: true,
        sortValue: (row: ReportTableRow) => row.name.toLowerCase(),
        filterValue: (row: ReportTableRow) => row.name,
        render: (row: ReportTableRow) => (
          <span className={styles.reportTitleClickable}>{row.name}</span>
        ),
      },
      {
        key: 'description',
        header: 'Description',
        sortable: false,
        filterable: true,
        filterValue: (row: ReportTableRow) => row.description,
        render: (row: ReportTableRow) => (
          <span className={styles.reportDescription} title={row.description}>
            {row.description.length > 80 ? `${row.description.substring(0, 80)}…` : row.description}
          </span>
        ),
      },
      {
        key: 'type',
        header: 'Type',
        sortable: true,
        filterable: true,
        sortValue: (row: ReportTableRow) => row.type.toLowerCase(),
        filterValue: (row: ReportTableRow) => row.type,
        render: (row: ReportTableRow) => <Label variant="muted">{row.type}</Label>,
      },
      {
        key: 'lastRun',
        header: 'Last Run',
        sortable: true,
        sortValue: (row: ReportTableRow) => (row.lastRun ? new Date(row.lastRun).getTime() : 0),
        render: (row: ReportTableRow) => (row.lastRun ? formatDateOnly(row.lastRun) : '—'),
      },
      {
        key: 'schedule',
        header: 'Schedule',
        sortable: false,
        render: (row: ReportTableRow) => row.schedule,
      },
      {
        key: 'status',
        header: 'Status',
        sortable: true,
        filterable: true,
        sortValue: (row: ReportTableRow) => row.status.toLowerCase(),
        filterValue: (row: ReportTableRow) => row.status,
        render: (row: ReportTableRow) => (
          <Label variant={row.status === 'available' ? 'accent' : 'muted'}>{row.status}</Label>
        ),
      },
    ],
    [],
  );

  // Find the selected row from the URL query param
  const selectedReport: ReportTableRow | null = useMemo(() => {
    if (!selectedReportId) return null;
    const allRows = [...templateRows, ...customRows, ...sharedRows, ...recentRows];
    return allRows.find((r) => r.id === selectedReportId) ?? null;
  }, [selectedReportId, templateRows, customRows, sharedRows, recentRows]);

  // Handle row click — open the detail tray and update URL
  const handleRowClick = useCallback(
    (row: ReportTableRow) => {
      setSelectedReportId(row.id);
    },
    [setSelectedReportId],
  );

  // Handle drawer close
  const handleDrawerClose = useCallback(() => {
    setSelectedReportId('', { replace: true });
  }, [setSelectedReportId]);

  // Deep-link effect: if a report is selected via URL but not in the current tab, switch tabs
  useEffect(() => {
    if (!selectedReportId || selectedReport) return;
    if (templateRows.some((r) => r.id === selectedReportId)) {
      setActiveTab('templates');
    } else if (customRows.some((r) => r.id === selectedReportId)) {
      setActiveTab('my-reports');
    } else if (sharedRows.some((r) => r.id === selectedReportId)) {
      setActiveTab('shared');
    } else if (recentRows.some((r) => r.id === selectedReportId)) {
      setActiveTab('recent');
    }
  }, [
    selectedReportId,
    selectedReport,
    templateRows,
    customRows,
    sharedRows,
    recentRows,
    setActiveTab,
  ]);

  // Determine drawer content based on selected report
  const drawerTitle = selectedReport?.name ?? 'Report Details';
  const drawerReportData = selectedReport ? reportDataMap[selectedReport.type] : undefined;

  const summaries = [
    {
      key: 'mau',
      label: 'Total MAU buckets',
      helpText:
        'Monthly active user time-series buckets derived from audit log events. Each bucket represents a time period with aggregated unique user counts.',
      dataSource: mauData?.data_source ?? 'Audit Events',
      value: mauData?.data.length ?? '—',
    },
    {
      key: 'actions',
      label: 'Actions buckets',
      helpText:
        'GitHub Actions workflow run volume buckets. Tracks CI/CD pipeline execution frequency over the selected time window.',
      dataSource: actionsData?.data_source ?? 'Audit Events',
      value: actionsData?.data.length ?? '—',
    },
    {
      key: 'seat',
      label: 'Platform seat util buckets',
      helpText:
        'Platform seat utilization over time. Tracks how many GHEC license seats are actively used versus provisioned.',
      dataSource: seatData?.data_source ?? 'Audit Events',
      value: seatData?.data.length ?? '—',
    },
    {
      key: 'copilot',
      label: 'Copilot seat buckets',
      helpText:
        'Copilot seat assignment changes over time. Tracks seat grants, removals, and net seat count for license optimization.',
      dataSource: copilotData?.data_source ?? 'Audit Events (Copilot)',
      value: copilotData?.data.length ?? '—',
    },
    {
      key: 'repo-creation',
      label: 'Repo creation buckets',
      helpText:
        'Repository creation rate over time. Derived from repo.create audit events. Useful for tracking org growth.',
      dataSource: repoCreationData?.data_source ?? 'Audit Events',
      value: repoCreationData?.data.length ?? '—',
    },
    {
      key: 'pat-counts',
      label: 'PAT event buckets',
      helpText:
        'Personal Access Token lifecycle events over time. Tracks token creation, usage, and revocation patterns.',
      dataSource: patCountsData?.data_source ?? 'Audit Events',
      value: patCountsData?.data.length ?? '—',
    },
    {
      key: 'webhook-counts',
      label: 'Webhook event buckets',
      helpText:
        'Webhook lifecycle events over time. Tracks webhook creation, modification, and deletion activity.',
      dataSource: webhookCountsData?.data_source ?? 'Audit Events',
      value: webhookCountsData?.data.length ?? '—',
    },
    {
      key: 'codespace-hours',
      label: 'Codespace hours buckets',
      helpText:
        'Codespace compute hours consumed over time. Tracks codespace lifecycle events for cost management.',
      dataSource: codespaceHoursData?.data_source ?? 'Audit Events',
      value: codespaceHoursData?.data.length ?? '—',
    },
  ];

  /** Map summary keys to template report types for deep-linking from summary cards */
  const summaryKeyToType: Record<string, string> = {
    mau: 'mau',
    actions: 'actions-volume',
    seat: 'seat-utilization',
    copilot: 'copilot-seats',
    'repo-creation': 'repo-creation-rate',
    'pat-counts': 'pat-counts',
    'webhook-counts': 'webhook-counts',
    'codespace-hours': 'codespace-hours',
  };

  const handleSummaryClick = useCallback(
    (key: string) => {
      const reportType = summaryKeyToType[key];
      if (!reportType) return;
      const matchRow = templateRows.find((r) => r.type === reportType);
      if (matchRow) {
        setSelectedReportId(matchRow.id);
      }
    },
    [templateRows, setSelectedReportId],
  );

  const tabs: { key: ReportTab; label: string }[] = [
    { key: 'templates', label: 'Templates' },
    { key: 'my-reports', label: 'My Reports' },
    { key: 'shared', label: 'Shared with Me' },
    { key: 'recent', label: 'Recent' },
  ];

  const isLoading =
    activeTab === 'templates'
      ? catalogLoading
      : activeTab === 'my-reports'
        ? customReportsLoading
        : activeTab === 'shared'
          ? sharedReportsLoading
          : customReportsLoading || sharedReportsLoading;

  const emptyMessage =
    activeTab === 'templates'
      ? 'No reports available yet. Reports are generated automatically after sync completes. Check back after your first successful organization sync.'
      : activeTab === 'my-reports'
        ? 'No custom reports yet. Click "+ New Custom Report" to create one.'
        : activeTab === 'shared'
          ? 'No reports have been shared with you yet.'
          : 'No recently run reports.';

  function buildDynamicColumns(
    data: readonly Record<string, unknown>[],
  ): ColumnDef<Record<string, unknown>>[] {
    if (data.length === 0) return [];
    return Object.keys(data[0]).map((col) => ({
      key: col,
      header: col,
      sortable: true,
      filterable: true,
      sortValue: (row: Record<string, unknown>) => {
        const val = row[col];
        if (val == null) return '';
        if (typeof val === 'number') return val;
        return String(val).toLowerCase();
      },
      filterValue: (row: Record<string, unknown>) => String(row[col] ?? ''),
      render: (row: Record<string, unknown>) => String(row[col] ?? ''),
    }));
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <PageHeader
            title="Reports"
            description="Organization activity and usage analytics"
            showHelp
          />
        </div>
        <div className={styles.headerActions}>
          <Button onClick={() => setShowBuilder(true)}>+ New Custom Report</Button>
          <div className={styles.windowSelector}>
            <span className={styles.windowLabel}>Window:</span>
            {([30, 60, 90] as const).map((w) => (
              <Button
                key={w}
                size="sm"
                className={windowDays === w ? styles.windowBtnActive : undefined}
                onClick={() => setWindowDays(w)}
              >
                {w}d
              </Button>
            ))}
          </div>
        </div>
      </div>

      {(mauError ||
        repoCreationError ||
        patCountsError ||
        webhookCountsError ||
        codespaceHoursError) && <ErrorBanner message="Failed to load report data" />}

      <Card style={{ marginBottom: 20 }}>
        <CardHeader>Data summary — last {windowDays} days</CardHeader>
        <div className={styles.summaryGrid}>
          {summaries.map((s) => {
            const isClickable = typeof s.value === 'number' && s.value > 0;
            return (
              <div key={s.label} className={styles.summaryItem}>
                <div className={styles.summaryValue}>
                  {mauLoading ||
                  actionsLoading ||
                  repoCreationLoading ||
                  patCountsLoading ||
                  webhookCountsLoading ||
                  codespaceHoursLoading ? (
                    <Spinner />
                  ) : isClickable ? (
                    <span
                      className={styles.clickableValue}
                      role="button"
                      tabIndex={0}
                      onClick={() => handleSummaryClick(s.key)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') handleSummaryClick(s.key);
                      }}
                    >
                      {s.value}
                    </span>
                  ) : (
                    s.value
                  )}
                </div>
                <div className={styles.summaryLabel}>{s.label}</div>
                {s.helpText && (
                  <span
                    title={s.helpText}
                    style={{
                      cursor: 'help',
                      fontSize: 12,
                      color: 'var(--fg-muted)',
                      marginLeft: 4,
                    }}
                  >
                    ⓘ
                  </span>
                )}
                <div className={styles.dataSourceLabel}>Source: {s.dataSource}</div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Tab navigation */}
      <div className={styles.tabBar} role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            className={`${styles.tab} ${activeTab === tab.key ? styles.tabActive : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
            {tab.key === 'my-reports' && customReports && customReports.length > 0 && (
              <span className={styles.tabCount}>{customReports.length}</span>
            )}
            {tab.key === 'shared' && sharedReports && sharedReports.length > 0 && (
              <span className={styles.tabCount}>{sharedReports.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* Reports table */}
      {isLoading ? (
        <div className={styles.reportList}>
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : activeRows.length === 0 ? (
        <div className={styles.emptyReports}>{emptyMessage}</div>
      ) : (
        <DataTable<ReportTableRow>
          columns={tableColumns}
          data={activeRows}
          rowKey={(row) => row.id}
          onRowClick={handleRowClick}
          emptyMessage={emptyMessage}
        />
      )}

      {/* Detail slide-out tray */}
      <Drawer open={selectedReport !== null} onClose={handleDrawerClose} title={drawerTitle}>
        {selectedReport && (
          <div className={styles.drawerContent} data-testid="report-detail-tray">
            {/* Report metadata */}
            <div className={styles.drawerMeta}>
              <div className={styles.drawerMetaRow}>
                <span className={styles.configLabel}>Type</span>
                <Label variant="accent">{selectedReport.type}</Label>
              </div>
              <div className={styles.drawerMetaRow}>
                <span className={styles.configLabel}>Status</span>
                <Label variant="muted">{selectedReport.status}</Label>
              </div>
              {selectedReport.lastRun && (
                <div className={styles.drawerMetaRow}>
                  <span className={styles.configLabel}>Last Run</span>
                  <span>{formatDateOnly(selectedReport.lastRun)}</span>
                </div>
              )}
              {selectedOrg && (
                <div className={styles.drawerMetaRow}>
                  <span className={styles.configLabel}>Organization</span>
                  <span>{selectedOrg}</span>
                </div>
              )}
              {selectedReport.description && (
                <p className={styles.drawerDescription}>{selectedReport.description}</p>
              )}
            </div>

            {/* Actions: Export, Schedule, Configure */}
            <div className={styles.drawerActions}>
              <Button
                size="sm"
                onClick={() => {
                  const rType =
                    selectedReport.catalogRef?.type ??
                    selectedReport.templateRef?.type ??
                    selectedReport.customRef?.data_sources[0] ??
                    'events';
                  exportReport(rType, 'csv');
                  showToast('Report exported as CSV', 'success');
                }}
              >
                Export CSV
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  const rType =
                    selectedReport.catalogRef?.type ??
                    selectedReport.templateRef?.type ??
                    selectedReport.customRef?.data_sources[0] ??
                    'events';
                  exportReport(rType, 'pdf');
                  showToast('Report exported as PDF', 'success');
                }}
              >
                Export PDF
              </Button>
              {selectedReport.source === 'custom' && selectedReport.customRef && (
                <>
                  <Button
                    size="sm"
                    onClick={() => {
                      if (selectedReport.customRef) {
                        setShareModalReport(selectedReport.customRef);
                      }
                    }}
                  >
                    Share
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => {
                      if (
                        selectedReport.customRef &&
                        window.confirm(`Delete report "${selectedReport.name}"?`)
                      ) {
                        deleteMutation.mutate(selectedReport.customRef.id);
                        handleDrawerClose();
                      }
                    }}
                  >
                    Delete
                  </Button>
                </>
              )}
            </div>

            {/* Configuration panel for templates/catalog */}
            {(selectedReport.source === 'template' || selectedReport.source === 'catalog') && (
              <div className={styles.drawerSection}>
                <ReportConfigPanel
                  template={
                    selectedReport.catalogRef ??
                    (selectedReport.templateRef
                      ? {
                          id: selectedReport.templateRef.id,
                          type: selectedReport.templateRef.type,
                          title: selectedReport.templateRef.title,
                          description: selectedReport.templateRef.description,
                          data_source: selectedReport.templateRef.data_source,
                          generated_at: null,
                          status: 'available',
                          tags: [...selectedReport.templateRef.tags],
                        }
                      : undefined)
                  }
                  customReport={undefined}
                  onClose={handleDrawerClose}
                />
              </div>
            )}

            {/* Configuration panel for custom/shared reports */}
            {(selectedReport.source === 'custom' || selectedReport.source === 'shared') &&
              selectedReport.customRef && (
                <div className={styles.drawerSection}>
                  <ReportConfigPanel
                    template={undefined}
                    customReport={selectedReport.customRef}
                    onClose={handleDrawerClose}
                  />
                </div>
              )}

            {/* Report data results for templates/catalog (if available) */}
            {drawerReportData?.data && drawerReportData.data.length > 0 && (
              <div className={styles.drawerSection}>
                <h4 className={styles.drawerSectionTitle}>{drawerReportData.title}</h4>
                <div className={styles.modalDataSource}>Source: {drawerReportData.dataSource}</div>
                <div className={styles.reportTableContainer}>
                  <DataTable<Record<string, unknown>>
                    columns={buildDynamicColumns(drawerReportData.data)}
                    data={drawerReportData.data.map((row, i) => ({ ...row, __idx: i }))}
                    rowKey={(row) => row.__idx as number}
                    emptyMessage="No data available for this report type"
                  />
                </div>
              </div>
            )}

            {/* No data state for templates/catalog */}
            {(selectedReport.source === 'template' || selectedReport.source === 'catalog') &&
              (!drawerReportData?.data || drawerReportData.data.length === 0) && (
                <p className={styles.emptyReports}>No data available for this report type.</p>
              )}
          </div>
        )}
      </Drawer>

      {/* Report builder modal */}
      <Modal
        open={showBuilder}
        onClose={() => setShowBuilder(false)}
        title="Custom Report Builder"
        width={720}
      >
        <ReportBuilder
          onClose={() => setShowBuilder(false)}
          onCreated={() => {
            setShowBuilder(false);
            setActiveTab('my-reports');
          }}
        />
      </Modal>

      {/* Share modal */}
      <Modal
        open={shareModalReport !== null}
        onClose={() => {
          setShareModalReport(null);
          setShareLogins('');
        }}
        title={`Share "${shareModalReport?.name ?? ''}"`}
      >
        <div className={styles.shareModal}>
          <label className={styles.configLabel}>Enter GitHub usernames (comma-separated)</label>
          <input
            type="text"
            className={styles.textInput}
            placeholder="user1, user2, user3"
            value={shareLogins}
            onChange={(e) => setShareLogins(e.target.value)}
            aria-label="Usernames to share with"
          />
          {shareModalReport && shareModalReport.shared_with.length > 0 && (
            <div className={styles.currentShares}>
              <span className={styles.configLabel}>Currently shared with:</span>
              <div className={styles.reportTags}>
                {shareModalReport.shared_with.map((login) => (
                  <Label key={login} variant="muted">
                    {login}
                  </Label>
                ))}
              </div>
            </div>
          )}
          <div className={styles.configActions}>
            <Button onClick={handleShare} disabled={!shareLogins.trim() || shareMutation.isPending}>
              {shareMutation.isPending ? (
                <>
                  <Spinner /> Sharing…
                </>
              ) : (
                'Share'
              )}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
