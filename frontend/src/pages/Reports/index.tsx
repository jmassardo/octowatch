import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getMauReport,
  getSeatUtilizationReport,
  getActionsVolumeReport,
  getCopilotSeatsReport,
  exportReport,
} from '../../api/reports';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import type { ReportParams } from '../../types/reports';
import styles from './Reports.module.css';

const REPORT_CATALOG = [
  {
    type: 'security_posture',
    title: 'Monthly Security Posture — January 2024',
    dateInfo: 'Generated Jan 15, 2024 · 47 pages',
    tags: [
      { label: '14 critical findings', variant: 'danger' as const },
      { label: '8 medium', variant: 'attention' as const },
      { label: 'automated', variant: 'success' as const },
      { label: 'acme-corp', variant: 'muted' as const },
      { label: 'globex', variant: 'muted' as const },
    ],
  },
  {
    type: 'engineering_velocity',
    title: 'Engineering Velocity Q4 2023 — Executive Summary',
    dateInfo: 'Generated Jan 1, 2024 · 12 pages',
    tags: [
      { label: 'velocity', variant: 'accent' as const },
      { label: '847 deploys', variant: 'success' as const },
      { label: '94.2% pipeline health', variant: 'success' as const },
    ],
  },
  {
    type: 'access_review',
    title: 'Access Review — Outside Collaborators and PAT Inventory',
    dateInfo: 'Generated Dec 28, 2023 · 23 pages',
    tags: [
      { label: '47 collaborators', variant: 'attention' as const },
      { label: '12 expiring tokens', variant: 'danger' as const },
      { label: 'quarterly', variant: 'muted' as const },
    ],
  },
  {
    type: 'dora_metrics',
    title: 'DORA Metrics — December 2023',
    dateInfo: 'Generated Jan 2, 2024 · 8 pages',
    tags: [
      { label: 'Elite performer', variant: 'success' as const },
      { label: 'DORA', variant: 'accent' as const },
      { label: 'acme-corp', variant: 'muted' as const },
    ],
  },
];

export function ReportsPage() {
  const [windowDays, setWindowDays] = useState<30 | 60 | 90>(30);
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

  const summaries = [
    { label: 'Total MAU buckets', value: mauData?.data.length ?? '—' },
    { label: 'Actions buckets', value: actionsData?.data.length ?? '—' },
    { label: 'Seat util buckets', value: seatData?.data.length ?? '—' },
    { label: 'Copilot seat buckets', value: copilotData?.data.length ?? '—' },
  ];

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
          {summaries.map((s) => (
            <div key={s.label} className={styles.summaryItem}>
              <div className={styles.summaryValue}>
                {mauLoading || actionsLoading ? <Spinner /> : s.value}
              </div>
              <div className={styles.summaryLabel}>{s.label}</div>
            </div>
          ))}
        </div>
      </Card>

      <div className={styles.reportList}>
        {REPORT_CATALOG.map((r) => (
          <div key={r.type} className={styles.reportItem}>
            <div>
              <div className={styles.reportTitle}>{r.title}</div>
              <div className={styles.reportDate}>{r.dateInfo}</div>
              <div className={styles.reportTags}>
                {r.tags.map((t) => (
                  <Label key={t.label} variant={t.variant}>{t.label}</Label>
                ))}
              </div>
            </div>
            <div className={styles.reportActions}>
              <Button size="sm" onClick={() => exportReport(r.type, 'pdf')}>PDF</Button>
              <Button size="sm" onClick={() => exportReport(r.type, 'csv')}>CSV</Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
