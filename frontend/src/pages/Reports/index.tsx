import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import styles from './Reports.module.css';

const REPORTS = [
  {
    title: 'Monthly Security Posture — January 2024',
    date: 'Generated Jan 15, 2024 · 47 pages',
    tags: [
      { label: '14 critical findings', variant: 'danger' as const },
      { label: '8 medium', variant: 'attention' as const },
      { label: 'automated', variant: 'success' as const },
      { label: 'acme-corp + globex', variant: 'muted' as const },
    ],
    type: 'security-posture',
  },
  {
    title: 'Engineering Velocity Q4 2023 — Executive Summary',
    date: 'Generated Jan 1, 2024 · 12 pages',
    tags: [
      { label: 'velocity', variant: 'accent' as const },
      { label: '847 deploys', variant: 'success' as const },
      { label: '94.2% pipeline health', variant: 'success' as const },
    ],
    type: 'velocity',
  },
  {
    title: 'Access Review — Outside Collaborators and PAT Inventory',
    date: 'Generated Dec 28, 2023 · 23 pages',
    tags: [
      { label: '47 collaborators', variant: 'attention' as const },
      { label: '12 expiring tokens', variant: 'danger' as const },
      { label: 'quarterly', variant: 'muted' as const },
    ],
    type: 'access-review',
  },
  {
    title: 'DORA Metrics — December 2023',
    date: 'Generated Jan 2, 2024 · 8 pages',
    tags: [
      { label: 'Elite performer', variant: 'success' as const },
      { label: 'DORA', variant: 'accent' as const },
      { label: 'acme-corp', variant: 'muted' as const },
    ],
    type: 'dora',
  },
];

export function ReportsPage() {
  function handleExport(type: string, format: 'pdf' | 'csv') {
    window.open(`/api/v1/reports/export/${type}?format=${format}`, '_blank');
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.pageTitle}>Reports</div>
          <div className={styles.pageSub}>Scheduled and on-demand intelligence reports</div>
        </div>
        <Button variant="primary">Generate report</Button>
      </div>

      <div className={styles.reportList}>
        {REPORTS.map((r) => (
          <div key={r.type} className={styles.reportItem}>
            <div>
              <div className={styles.reportTitle}>{r.title}</div>
              <div className={styles.reportDate}>{r.date}</div>
              <div className={styles.reportTags}>
                {r.tags.map((t) => (
                  <Label key={t.label} variant={t.variant}>{t.label}</Label>
                ))}
              </div>
            </div>
            <div className={styles.reportActions}>
              <Button size="sm" onClick={() => handleExport(r.type, 'pdf')}>PDF</Button>
              <Button size="sm" onClick={() => handleExport(r.type, 'csv')}>CSV</Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
