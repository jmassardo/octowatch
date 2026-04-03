import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
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
} from '../../api/reports';
import { useOrg } from '../../hooks/useOrg';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Modal } from '../../components/primitives/Modal';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import type { ReportParams } from '../../types/reports';
import { formatDateOnly } from '../../utils/dates';
import styles from './Reports.module.css';

export function ReportsPage() {
  const { selectedOrg } = useOrg();
  const [windowDays, setWindowDays] = useState<30 | 60 | 90>(30);
  const [bucketModal, setBucketModal] = useState<string | null>(null);
  const [viewReport, setViewReport] = useState<string | null>(null);
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

  const summaries = [
    {
      key: 'mau',
      label: 'Total MAU buckets',
      dataSource: mauData?.data_source ?? 'Audit Events',
      value: mauData?.data.length ?? '—',
      data: mauData?.data,
    },
    {
      key: 'actions',
      label: 'Actions buckets',
      dataSource: actionsData?.data_source ?? 'Audit Events',
      value: actionsData?.data.length ?? '—',
      data: actionsData?.data,
    },
    {
      key: 'seat',
      label: 'Platform seat util buckets',
      dataSource: seatData?.data_source ?? 'Audit Events',
      value: seatData?.data.length ?? '—',
      data: seatData?.data,
    },
    {
      key: 'copilot',
      label: 'Copilot seat buckets',
      dataSource: copilotData?.data_source ?? 'Audit Events (Copilot)',
      value: copilotData?.data.length ?? '—',
      data: copilotData?.data,
    },
    {
      key: 'repo-creation',
      label: 'Repo creation buckets',
      dataSource: repoCreationData?.data_source ?? 'Audit Events',
      value: repoCreationData?.data.length ?? '—',
      data: repoCreationData?.data,
    },
    {
      key: 'pat-counts',
      label: 'PAT event buckets',
      dataSource: patCountsData?.data_source ?? 'Audit Events',
      value: patCountsData?.data.length ?? '—',
      data: patCountsData?.data,
    },
    {
      key: 'webhook-counts',
      label: 'Webhook event buckets',
      dataSource: webhookCountsData?.data_source ?? 'Audit Events',
      value: webhookCountsData?.data.length ?? '—',
      data: webhookCountsData?.data,
    },
    {
      key: 'codespace-hours',
      label: 'Codespace hours buckets',
      dataSource: codespaceHoursData?.data_source ?? 'Audit Events',
      value: codespaceHoursData?.data.length ?? '—',
      data: codespaceHoursData?.data,
    },
  ];

  const activeBucket = summaries.find((s) => s.key === bucketModal);

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

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.pageTitle}>Reports</div>
          <div className={styles.pageSub}>On-demand metric reports with CSV export</div>
        </div>
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
                      onClick={() => setBucketModal(s.key)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') setBucketModal(s.key);
                      }}
                    >
                      {s.value}
                    </span>
                  ) : (
                    s.value
                  )}
                </div>
                <div className={styles.summaryLabel}>{s.label}</div>
                <div className={styles.dataSourceLabel}>Source: {s.dataSource}</div>
              </div>
            );
          })}
        </div>
      </Card>

      <div className={styles.reportList}>
        {catalogLoading ? (
          <Spinner />
        ) : (catalogData ?? []).length === 0 ? (
          <div className={styles.emptyReports}>
            No reports generated yet. Use the data summary cards above to explore your data, or
            check back after reports have been generated.
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
                {r.description && <div className={styles.reportDescription}>{r.description}</div>}
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
                <Button size="sm" onClick={() => exportReport(r.type, 'pdf')}>
                  PDF
                </Button>
                <Button size="sm" onClick={() => exportReport(r.type, 'csv')}>
                  CSV
                </Button>
              </div>
            </div>
          ))
        )}
      </div>

      <Modal
        open={bucketModal !== null}
        onClose={() => setBucketModal(null)}
        title={activeBucket?.label ?? ''}
        width={600}
      >
        {activeBucket && (
          <div className={styles.modalDataSource}>Source: {activeBucket.dataSource}</div>
        )}
        {activeBucket?.data && activeBucket.data.length > 0 ? (
          <DataTable<Record<string, unknown>>
            columns={buildDynamicColumns(activeBucket.data)}
            data={activeBucket.data.map((row, i) => ({ ...row, __idx: i }))}
            rowKey={(row) => row.__idx as number}
            emptyMessage="No data available"
          />
        ) : (
          <p>No data available.</p>
        )}
      </Modal>

      <Modal
        open={viewReport !== null}
        onClose={() => setViewReport(null)}
        title={activeReport?.title ?? 'Report Data'}
        width={800}
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
            />
          ) : (
            <p>No data available for this report type.</p>
          )}
        </div>
      </Modal>
    </div>
  );
}
