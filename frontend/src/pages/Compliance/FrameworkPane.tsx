import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { getFrameworkDetail } from '../../api/compliance';
import { exportReport } from '../../api/reports';
import type { ControlItem } from '../../types/compliance';
import styles from './Compliance.module.css';

function statusToLabelVariant(status: string) {
  switch (status) {
    case 'pass':
      return 'success' as const;
    case 'fail':
      return 'danger' as const;
    case 'partial':
      return 'attention' as const;
    default:
      return 'muted' as const;
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'pass':
      return 'Pass';
    case 'fail':
      return 'Fail';
    case 'partial':
      return 'Partial';
    default:
      return 'Not Assessed';
  }
}

function scoreColorClass(score: number): string {
  if (score >= 75) return styles.scoreHigh;
  if (score >= 50) return styles.scoreMedium;
  return styles.scoreLow;
}

function scoreBarColor(score: number): string {
  if (score >= 75) return 'var(--color-success-fg, #3fb950)';
  if (score >= 50) return 'var(--color-attention-fg, #d29922)';
  return 'var(--color-danger-fg, #f85149)';
}

interface FrameworkPaneProps {
  frameworkName: string;
  org?: string;
}

export function FrameworkPane({ frameworkName, org }: FrameworkPaneProps) {
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());

  const {
    data: detail,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['compliance', 'framework', frameworkName, org],
    queryFn: () => getFrameworkDetail(frameworkName, org),
    staleTime: 120_000,
  });

  function toggleCategory(category: string) {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  }

  function handleExport() {
    const reportMap: Record<string, string> = {
      soc2: 'soc2',
      iso27001: 'iso27001',
      nist_csf: 'nist-csf',
    };
    const reportType = reportMap[frameworkName];
    if (reportType) {
      exportReport(reportType, 'pdf');
    }
  }

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem' }}>
        <Spinner size={28} />
      </div>
    );
  }

  if (error || !detail) {
    return <ErrorBanner message="Failed to load framework data" onRetry={() => refetch()} />;
  }

  const controls = detail.controls;
  const passing = controls.filter((c) => c.status === 'pass').length;
  const total = controls.length;

  // Group controls by category (control_id prefix)
  const grouped = groupControls(controls);

  return (
    <div>
      <div className={styles.actionsBar}>
        <Button variant="primary" onClick={handleExport}>
          Generate Report
        </Button>
      </div>

      {/* Score header */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '1rem', marginBottom: '1rem' }}>
        <span className={`${styles.frameworkScore} ${scoreColorClass(detail.score)}`}>
          {detail.score}%
        </span>
        <span style={{ color: 'var(--fg-muted)', fontSize: '0.9rem' }}>
          {passing} / {total} controls passing
        </span>
        {detail.last_generated && (
          <span style={{ color: 'var(--fg-muted)', fontSize: '0.8rem' }}>
            Last generated: {new Date(detail.last_generated).toLocaleDateString()}
          </span>
        )}
      </div>

      <div className={styles.progressBar}>
        <div
          className={styles.progressFill}
          style={{
            width: `${detail.score}%`,
            backgroundColor: scoreBarColor(detail.score),
          }}
        />
      </div>

      {/* Control categories */}
      <div style={{ marginTop: '1.5rem' }}>
        {grouped.map(({ category, controls: catControls }) => {
          const catPassing = catControls.filter((c) => c.status === 'pass').length;
          const isExpanded = expandedCategories.has(category);

          return (
            <div key={category} className={styles.controlSection}>
              <div
                className={styles.controlHeader}
                onClick={() => toggleCategory(category)}
                role="button"
                tabIndex={0}
                aria-expanded={isExpanded}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggleCategory(category);
                  }
                }}
              >
                <span className={styles.controlTitle}>
                  <span aria-hidden="true">{isExpanded ? '▼' : '▶'}</span>
                  {category}
                </span>
                <span className={styles.controlPassRate}>
                  {catPassing} / {catControls.length} passing
                </span>
              </div>

              {isExpanded && (
                <div className={styles.controlList}>
                  {catControls.map((ctrl) => (
                    <div key={ctrl.control_id} className={styles.controlItem}>
                      <div className={styles.controlItemLeft}>
                        <span className={styles.controlItemId}>{ctrl.control_id}</span>
                        <span className={styles.controlItemTitle}>{ctrl.title}</span>
                        <span className={styles.controlItemDesc}>{ctrl.description}</span>
                        {ctrl.evidence_summary && (
                          <span className={styles.controlItemEvidence}>
                            Evidence: {ctrl.evidence_summary}
                          </span>
                        )}
                      </div>
                      <div className={styles.controlItemRight}>
                        <Label variant={statusToLabelVariant(ctrl.status)}>
                          {statusLabel(ctrl.status)}
                        </Label>
                        {ctrl.last_checked && (
                          <span
                            style={{ fontSize: '0.75rem', color: 'var(--fg-muted)' }}
                            title="Last checked"
                          >
                            {new Date(ctrl.last_checked).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface ControlGroup {
  category: string;
  controls: ControlItem[];
}

function groupControls(controls: readonly ControlItem[]): ControlGroup[] {
  const map = new Map<string, ControlItem[]>();
  for (const ctrl of controls) {
    // Use the control_id prefix as category (e.g., "CC6" from "CC6.1")
    const parts = ctrl.control_id.split(/[.-]/);
    const category = parts[0] || ctrl.category || 'General';
    const existing = map.get(category);
    if (existing) {
      existing.push({ ...ctrl });
    } else {
      map.set(category, [{ ...ctrl }]);
    }
  }
  return Array.from(map.entries()).map(([category, ctrls]) => ({
    category,
    controls: ctrls,
  }));
}
