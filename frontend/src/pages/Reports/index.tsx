import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getMauReport,
  getSeatUtilizationReport,
  getActionsVolumeReport,
  getCopilotSeatsReport,
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
import type { ReportParams } from '../../types/reports';
import styles from './Reports.module.css';

export function ReportsPage() {
  const { selectedOrg } = useOrg();
  const [windowDays, setWindowDays] = useState<30 | 60 | 90>(30);
  const [bucketModal, setBucketModal] = useState<string | null>(null);
  const params: ReportParams = { window_days: windowDays, granularity: 'daily' };

  const { data: mauData, isLoading: mauLoading, isError: mauError } = useQuery({
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

  const { data: catalogData, isLoading: catalogLoading } = useQuery({
    queryKey: ['reports', 'catalog'],
    queryFn: getReportCatalog,
  });

  const summaries = [
    { key: 'mau', label: 'Total MAU buckets', value: mauData?.data.length ?? '—', data: mauData?.data },
    { key: 'actions', label: 'Actions buckets', value: actionsData?.data.length ?? '—', data: actionsData?.data },
    { key: 'seat', label: 'Seat util buckets', value: seatData?.data.length ?? '—', data: seatData?.data },
    { key: 'copilot', label: 'Copilot seat buckets', value: copilotData?.data.length ?? '—', data: copilotData?.data },
  ];

  const activeBucket = summaries.find((s) => s.key === bucketModal);

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

      {mauError && <ErrorBanner message="Failed to load report data" />}

      <Card style={{ marginBottom: 20 }}>
        <CardHeader>Data summary — last {windowDays} days</CardHeader>
        <div className={styles.summaryGrid}>
          {summaries.map((s) => {
            const isClickable = typeof s.value === 'number' && s.value > 0;
            return (
              <div key={s.label} className={styles.summaryItem}>
                <div className={styles.summaryValue}>
                  {mauLoading || actionsLoading ? (
                    <Spinner />
                  ) : isClickable ? (
                    <span
                      className={styles.clickableValue}
                      role="button"
                      tabIndex={0}
                      onClick={() => setBucketModal(s.key)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setBucketModal(s.key); }}
                    >
                      {s.value}
                    </span>
                  ) : (
                    s.value
                  )}
                </div>
                <div className={styles.summaryLabel}>{s.label}</div>
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
            No reports generated yet. Use the data summary cards above to explore your data, or check back after reports have been generated.
          </div>
        ) : (
          (catalogData ?? []).map((r) => (
            <div key={r.id} className={styles.reportItem}>
              <div>
                <div
                  className={`${styles.reportTitle} ${styles.reportTitleClickable}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => exportReport(r.type, 'pdf')}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') exportReport(r.type, 'pdf'); }}
                >
                  {r.title}
                </div>
                <div className={styles.reportDate}>Generated {new Date(r.generated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} · {r.status}</div>
                <div className={styles.reportTags}>
                  {r.tags.map((tag) => (
                    <Label key={tag} variant="muted">{tag}</Label>
                  ))}
                  <Label variant="muted">{selectedOrg || 'All orgs'}</Label>
                </div>
              </div>
              <div className={styles.reportActions}>
                <Button size="sm" onClick={() => exportReport(r.type, 'pdf')}>PDF</Button>
                <Button size="sm" onClick={() => exportReport(r.type, 'csv')}>CSV</Button>
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
        {activeBucket?.data && activeBucket.data.length > 0 ? (
          <table className={styles.bucketTable}>
            <thead>
              <tr>
                {Object.keys(activeBucket.data[0]).map((col) => (
                  <th key={col}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {activeBucket.data.map((row: Record<string, unknown>, i: number) => (
                <tr key={i}>
                  {Object.values(row).map((val, j) => (
                    <td key={j}>{String(val)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>No data available.</p>
        )}
      </Modal>
    </div>
  );
}
