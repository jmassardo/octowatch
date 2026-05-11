import { useState, useCallback } from 'react';
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
import styles from './Reports.module.css';

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
  const [activeTab, setActiveTab] = useState<ReportTab>('templates');
  const [windowDays, setWindowDays] = useState<30 | 60 | 90>(30);
  const [filterBucket, setFilterBucket] = useState<string | null>(null);
  const [viewReport, setViewReport] = useState<string | null>(null);
  const [selectedRow, setSelectedRow] = useState<Record<string, unknown> | null>(null);
  const [configTemplate, setConfigTemplate] = useState<ReportCatalogEntry | null>(null);
  const [configCustomReport, setConfigCustomReport] = useState<CustomReport | null>(null);
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

  // Custom reports queries
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

  // Recent reports: combine custom and merge, sort by last_run_at
  const recentReports = [...(customReports ?? []), ...(sharedReports ?? [])]
    .filter((r) => r.last_run_at)
    .sort((a, b) => {
      const aDate = a.last_run_at ? new Date(a.last_run_at).getTime() : 0;
      const bDate = b.last_run_at ? new Date(b.last_run_at).getTime() : 0;
      return bDate - aDate;
    })
    .slice(0, 20);

  const summaries = [
    {
      key: 'mau',
      label: 'Total MAU buckets',
      helpText:
        'Monthly active user time-series buckets derived from audit log events. Each bucket represents a time period with aggregated unique user counts.',
      dataSource: mauData?.data_source ?? 'Audit Events',
      value: mauData?.data.length ?? '—',
      data: mauData?.data,
    },
    {
      key: 'actions',
      label: 'Actions buckets',
      helpText:
        'GitHub Actions workflow run volume buckets. Tracks CI/CD pipeline execution frequency over the selected time window.',
      dataSource: actionsData?.data_source ?? 'Audit Events',
      value: actionsData?.data.length ?? '—',
      data: actionsData?.data,
    },
    {
      key: 'seat',
      label: 'Platform seat util buckets',
      helpText:
        'Platform seat utilization over time. Tracks how many GHEC license seats are actively used versus provisioned.',
      dataSource: seatData?.data_source ?? 'Audit Events',
      value: seatData?.data.length ?? '—',
      data: seatData?.data,
    },
    {
      key: 'copilot',
      label: 'Copilot seat buckets',
      helpText:
        'Copilot seat assignment changes over time. Tracks seat grants, removals, and net seat count for license optimization.',
      dataSource: copilotData?.data_source ?? 'Audit Events (Copilot)',
      value: copilotData?.data.length ?? '—',
      data: copilotData?.data,
    },
    {
      key: 'repo-creation',
      label: 'Repo creation buckets',
      helpText:
        'Repository creation rate over time. Derived from repo.create audit events. Useful for tracking org growth.',
      dataSource: repoCreationData?.data_source ?? 'Audit Events',
      value: repoCreationData?.data.length ?? '—',
      data: repoCreationData?.data,
    },
    {
      key: 'pat-counts',
      label: 'PAT event buckets',
      helpText:
        'Personal Access Token lifecycle events over time. Tracks token creation, usage, and revocation patterns.',
      dataSource: patCountsData?.data_source ?? 'Audit Events',
      value: patCountsData?.data.length ?? '—',
      data: patCountsData?.data,
    },
    {
      key: 'webhook-counts',
      label: 'Webhook event buckets',
      helpText:
        'Webhook lifecycle events over time. Tracks webhook creation, modification, and deletion activity.',
      dataSource: webhookCountsData?.data_source ?? 'Audit Events',
      value: webhookCountsData?.data.length ?? '—',
      data: webhookCountsData?.data,
    },
    {
      key: 'codespace-hours',
      label: 'Codespace hours buckets',
      helpText:
        'Codespace compute hours consumed over time. Tracks codespace lifecycle events for cost management.',
      dataSource: codespaceHoursData?.data_source ?? 'Audit Events',
      value: codespaceHoursData?.data.length ?? '—',
      data: codespaceHoursData?.data,
    },
  ];

  const activeBucket = summaries.find((s) => s.key === filterBucket);

  const reportDataMap: Record<
    string,
    { title: string; dataSource: string; data: readonly Record<string, unknown>[] | undefined }
  > = {
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
  };

  const activeReport = viewReport ? reportDataMap[viewReport] : undefined;

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

  const tabs: { key: ReportTab; label: string }[] = [
    { key: 'templates', label: 'Templates' },
    { key: 'my-reports', label: 'My Reports' },
    { key: 'shared', label: 'Shared with Me' },
    { key: 'recent', label: 'Recent' },
  ];

  const renderCustomReportCard = (report: CustomReport, showOwner: boolean = false) => (
    <div key={report.id} className={styles.reportItem}>
      <div>
        <div
          className={`${styles.reportTitle} ${styles.reportTitleClickable}`}
          role="button"
          tabIndex={0}
          onClick={() => setConfigCustomReport(report)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') setConfigCustomReport(report);
          }}
        >
          {report.name}
        </div>
        {report.description && <div className={styles.reportDescription}>{report.description}</div>}
        <div className={styles.reportDate}>
          {report.last_run_at ? `Last run ${formatDateOnly(report.last_run_at)} · ` : ''}
          Created {formatDateOnly(report.created_at)}
        </div>
        <div className={styles.reportTags}>
          {report.data_sources.map((ds) => (
            <Label key={ds} variant="muted">
              {ds}
            </Label>
          ))}
          <Label variant="accent">{report.visualization}</Label>
          {showOwner && <Label variant="muted">Shared by {report.owner_login}</Label>}
          {report.is_shared && !showOwner && <Label variant="muted">Shared</Label>}
        </div>
      </div>
      <div className={styles.reportActions}>
        {!showOwner && (
          <>
            <Button size="sm" onClick={() => setShareModalReport(report)}>
              Share
            </Button>
            <Button
              size="sm"
              onClick={() => {
                if (window.confirm(`Delete report "${report.name}"?`)) {
                  deleteMutation.mutate(report.id);
                }
              }}
            >
              Delete
            </Button>
          </>
        )}
        <Button
          size="sm"
          onClick={() => {
            exportReport(report.data_sources[0] ?? 'events', 'csv');
            showToast('Report exported', 'success');
          }}
        >
          CSV
        </Button>
      </div>
    </div>
  );

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
                      className={`${styles.clickableValue}${filterBucket === s.key ? ` ${styles.clickableValueActive}` : ''}`}
                      role="button"
                      tabIndex={0}
                      onClick={() => setFilterBucket(filterBucket === s.key ? null : s.key)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ')
                          setFilterBucket(filterBucket === s.key ? null : s.key);
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

      {filterBucket && activeBucket && (
        <Card style={{ marginBottom: 20 }}>
          <CardHeader>
            <div className={styles.filterHeader}>
              <span>{activeBucket.label}</span>
              <Button size="sm" onClick={() => setFilterBucket(null)}>
                Clear filter
              </Button>
            </div>
          </CardHeader>
          <div className={styles.modalDataSource}>Source: {activeBucket.dataSource}</div>
          {activeBucket.data && activeBucket.data.length > 0 ? (
            <DataTable<Record<string, unknown>>
              columns={buildDynamicColumns(activeBucket.data)}
              data={activeBucket.data.map((row, i) => ({ ...row, __idx: i }))}
              rowKey={(row) => row.__idx as number}
              emptyMessage="No data available"
              onRowClick={(row) => setSelectedRow(row)}
            />
          ) : (
            <p style={{ padding: 16 }}>No data available.</p>
          )}
        </Card>
      )}

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

      {/* Templates tab */}
      {activeTab === 'templates' && (
        <div className={styles.reportList}>
          {catalogLoading ? (
            <>
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </>
          ) : (
            <>
              {/* Pre-built report templates */}
              <div className={styles.templateGrid}>
                {REPORT_TEMPLATES.map((tmpl) => (
                  <div
                    key={tmpl.id}
                    className={styles.templateCard}
                    role="button"
                    tabIndex={0}
                    onClick={() => {
                      const catalogEntry: ReportCatalogEntry = {
                        id: tmpl.id,
                        type: tmpl.type,
                        title: tmpl.title,
                        description: tmpl.description,
                        data_source: tmpl.data_source,
                        generated_at: null,
                        status: 'available',
                        tags: [...tmpl.tags],
                      };
                      setConfigTemplate(catalogEntry);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        const catalogEntry: ReportCatalogEntry = {
                          id: tmpl.id,
                          type: tmpl.type,
                          title: tmpl.title,
                          description: tmpl.description,
                          data_source: tmpl.data_source,
                          generated_at: null,
                          status: 'available',
                          tags: [...tmpl.tags],
                        };
                        setConfigTemplate(catalogEntry);
                      }
                    }}
                  >
                    <div className={styles.templateCategory}>
                      <Label variant="accent">{tmpl.category}</Label>
                    </div>
                    <div className={styles.templateTitle}>{tmpl.title}</div>
                    <div className={styles.templateDescription}>{tmpl.description}</div>
                    <div className={styles.reportTags}>
                      {tmpl.tags.map((tag) => (
                        <Label key={tag} variant="muted">
                          {tag}
                        </Label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              {/* Original catalog items */}
              {(catalogData ?? []).length === 0 ? (
                <div className={styles.emptyReports}>
                  No reports available yet. Reports are generated automatically after sync
                  completes. Check back after your first successful organization sync.
                </div>
              ) : (
                (catalogData ?? []).map((r) => (
                  <div key={r.id} className={styles.reportItem}>
                    <div>
                      <div
                        className={`${styles.reportTitle} ${styles.reportTitleClickable}`}
                        role="button"
                        tabIndex={0}
                        onClick={() => setViewReport(r.type)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') setViewReport(r.type);
                        }}
                      >
                        {r.title}
                      </div>
                      {r.description && (
                        <div className={styles.reportDescription}>{r.description}</div>
                      )}
                      <div className={styles.reportDate}>
                        {r.generated_at ? `Generated ${formatDateOnly(r.generated_at)} · ` : ''}
                        {r.status}
                      </div>
                      <div className={styles.reportTags}>
                        {(r.tags ?? []).map((tag) => (
                          <Label key={tag} variant="muted">
                            {tag}
                          </Label>
                        ))}
                        {r.data_source && <Label variant="accent">{r.data_source}</Label>}
                        <Label variant="muted">{selectedOrg || 'All orgs'}</Label>
                      </div>
                    </div>
                    <div className={styles.reportActions}>
                      <Button
                        size="sm"
                        onClick={() => {
                          exportReport(r.type, 'pdf');
                          showToast('Report exported successfully', 'success');
                        }}
                      >
                        PDF
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => {
                          exportReport(r.type, 'csv');
                          showToast('Report exported successfully', 'success');
                        }}
                      >
                        CSV
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </>
          )}
        </div>
      )}

      {/* My Reports tab */}
      {activeTab === 'my-reports' && (
        <div className={styles.reportList}>
          {customReportsLoading ? (
            <>
              <SkeletonCard />
              <SkeletonCard />
            </>
          ) : (customReports ?? []).length === 0 ? (
            <div className={styles.emptyReports}>
              No custom reports yet. Click &quot;+ New Custom Report&quot; to create one.
            </div>
          ) : (
            (customReports ?? []).map((r) => renderCustomReportCard(r))
          )}
        </div>
      )}

      {/* Shared with Me tab */}
      {activeTab === 'shared' && (
        <div className={styles.reportList}>
          {sharedReportsLoading ? (
            <>
              <SkeletonCard />
              <SkeletonCard />
            </>
          ) : (sharedReports ?? []).length === 0 ? (
            <div className={styles.emptyReports}>No reports have been shared with you yet.</div>
          ) : (
            (sharedReports ?? []).map((r) => renderCustomReportCard(r, true))
          )}
        </div>
      )}

      {/* Recent tab */}
      {activeTab === 'recent' && (
        <div className={styles.reportList}>
          {customReportsLoading || sharedReportsLoading ? (
            <>
              <SkeletonCard />
              <SkeletonCard />
            </>
          ) : recentReports.length === 0 ? (
            <div className={styles.emptyReports}>No recently run reports.</div>
          ) : (
            recentReports.map((r) => renderCustomReportCard(r, r.owner_login !== ''))
          )}
        </div>
      )}

      {/* Report config drawer */}
      <Drawer
        open={configTemplate !== null || configCustomReport !== null}
        onClose={() => {
          setConfigTemplate(null);
          setConfigCustomReport(null);
        }}
        title={configCustomReport?.name ?? configTemplate?.title ?? 'Configure Report'}
      >
        {(configTemplate || configCustomReport) && (
          <ReportConfigPanel
            template={configTemplate ?? undefined}
            customReport={configCustomReport ?? undefined}
            onClose={() => {
              setConfigTemplate(null);
              setConfigCustomReport(null);
            }}
          />
        )}
      </Drawer>

      {/* Report data drawer */}
      <Drawer
        open={viewReport !== null}
        onClose={() => setViewReport(null)}
        title={activeReport?.title ?? 'Report Data'}
      >
        <div className={styles.reportTableContainer}>
          {activeReport && (
            <div className={styles.modalDataSource}>Source: {activeReport.dataSource}</div>
          )}
          {activeReport?.data && activeReport.data.length > 0 ? (
            <DataTable<Record<string, unknown>>
              columns={buildDynamicColumns(activeReport.data)}
              data={activeReport.data.map((row, i) => ({ ...row, __idx: i }))}
              rowKey={(row) => row.__idx as number}
              emptyMessage="No data available for this report type"
              onRowClick={(row) => setSelectedRow(row)}
            />
          ) : (
            <p>No data available for this report type.</p>
          )}
        </div>
      </Drawer>

      {/* Row details drawer */}
      <Drawer open={!!selectedRow} onClose={() => setSelectedRow(null)} title="Details">
        {selectedRow && (
          <dl style={{ padding: '16px' }}>
            {Object.entries(selectedRow).map(([key, value]) => (
              <div key={key} style={{ marginBottom: 8 }}>
                <dt style={{ fontSize: '0.8em', color: 'var(--fg-muted)', marginBottom: 2 }}>
                  {key}
                </dt>
                <dd style={{ margin: 0 }}>{String(value ?? '—')}</dd>
              </div>
            ))}
          </dl>
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
