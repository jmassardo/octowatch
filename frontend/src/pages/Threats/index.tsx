import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listDetections, updateDetectionStatus, deleteDetection, assignDetection } from '../../api/detections';
import type { DetectionResponse } from '../../types/detections';
import { SeverityDot } from '../../components/primitives/SeverityDot';
import { Label } from '../../components/primitives/Label';
import { Button } from '../../components/primitives/Button';
import { CodeBlock } from '../../components/primitives/CodeBlock';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Threats.module.css';

function formatTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}

type TabFilter = 'open' | 'closed' | 'acknowledged' | 'all';

export function ThreatsPage() {
  const [tab, setTab] = useState<TabFilter>('open');
  const [selected, setSelected] = useState<DetectionResponse | null>(null);
  const [filtersVisible, setFiltersVisible] = useState(false);
  const [severityFilter, setSeverityFilter] = useState('');
  const qc = useQueryClient();
  const navigate = useNavigate();

  const statusMap: Record<TabFilter, string | undefined> = {
    open: 'investigating',
    closed: 'resolved',
    acknowledged: 'false_positive',
    all: undefined,
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['detections', tab, severityFilter],
    queryFn: () => listDetections({ status: statusMap[tab], severity: severityFilter || undefined }),
  });

  const acknowledgeMutation = useMutation({
    mutationFn: (id: number) => updateDetectionStatus(id, { status: 'false_positive' }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['detections'] }); },
  });

  const assignMutation = useMutation({
    mutationFn: ({ id, assignee }: { id: number; assignee: string }) =>
      assignDetection(id, { assigned_to: assignee }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['detections'] }); },
  });

  const suspendMutation = useMutation({
    mutationFn: (id: number) => deleteDetection(id),
    onSuccess: () => {
      setSelected(null);
      void qc.invalidateQueries({ queryKey: ['detections'] });
    },
  });

  const items = data?.items ?? [];

  const sevLabelVariant = (sev: string) => {
    if (sev === 'critical') return 'danger' as const;
    if (sev === 'high') return 'severe' as const;
    if (sev === 'medium') return 'attention' as const;
    return 'success' as const;
  };

  return (
    <div className={styles.splitLayout}>
      <div className={styles.splitMain}>
        <div className={styles.pageTitle}>Threat Detections</div>
        <div className={styles.pageSub}>Rule-based and ML-powered detections from audit log analysis</div>
        <div className={styles.topActions}>
          <Button size="sm" onClick={() => setFiltersVisible((v) => !v)}>Filter</Button>
          <Button size="sm" variant="primary" onClick={() => navigate('/rules')}>New rule</Button>
        </div>
        {filtersVisible && (
          <div className={styles.topActions} style={{ gap: 8 }}>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--canvas-subtle)', color: 'var(--fg)', fontSize: 13 }}
            >
              <option value="">All severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        )}

        <div className={styles.issueList}>
          <div className={styles.ilFilters}>
            {(['open', 'closed', 'acknowledged', 'all'] as TabFilter[]).map((t) => (
              <button
                key={t}
                className={[styles.ilTab, tab === t && styles.active].filter(Boolean).join(' ')}
                onClick={() => setTab(t)}
              >
                {t === 'open' && `Open (${data?.total ?? '…'})`}
                {t === 'closed' && 'Closed'}
                {t === 'acknowledged' && 'Acknowledged'}
                {t === 'all' && 'All'}
              </button>
            ))}
          </div>

          {isLoading && (
            <div className={styles.loadingRow}><Spinner /></div>
          )}
          {isError && (
            <div className={styles.loadingRow}>
              <ErrorBanner message="Failed to load detections" onRetry={refetch} />
            </div>
          )}

          {!isLoading && !isError && items.length === 0 && (
            <div className={styles.emptyRow}>No detections found</div>
          )}

          {items.map((d) => (
            <div
              key={d.id}
              className={[styles.ilRow, selected?.id === d.id && styles.selected].filter(Boolean).join(' ')}
              onClick={() => setSelected(d)}
            >
              <SeverityDot severity={d.severity} style={{ marginTop: 4 }} />
              <div className={styles.ilMeta}>
                <div className={styles.ilTitle}>{d.title}</div>
                <div className={styles.ilSub}>
                  <Label variant={sevLabelVariant(d.severity)}>{d.severity}</Label>
                  {d.rule_name && <Label variant="muted">{d.rule_name}</Label>}
                  {d.actor && <span>actor: <span className={styles.mention}>@{d.actor}</span></span>}
                  {d.org && <span>· {d.org}</span>}
                </div>
              </div>
              <div className={styles.ilTime}>{formatTime(d.triggered_at)}</div>
            </div>
          ))}
        </div>
      </div>

      <div className={[styles.splitPanel, selected && styles.open].filter(Boolean).join(' ')}>
        {selected && (
          <>
            <div className={styles.panelHeader}>
              <div style={{ fontWeight: 600 }}>{selected.title}</div>
              <button className={styles.panelClose} onClick={() => setSelected(null)}>&#215;</button>
            </div>

            <div className={styles.panelLabels}>
              <Label variant={sevLabelVariant(selected.severity)}>{selected.severity}</Label>
              {selected.rule_name && <Label variant="muted">{selected.rule_name}</Label>}
              {selected.confidence && <Label variant="done">{selected.confidence}</Label>}
            </div>

            <p className={styles.panelDesc}>{selected.description}</p>

            {Object.keys(selected.context_data).length > 0 && (
              <>
                <div className={styles.evidenceLabel}>Evidence</div>
                <CodeBlock className={styles.evidence}>
                  {JSON.stringify(selected.context_data, null, 2)}
                </CodeBlock>
              </>
            )}

            <div className={styles.panelActions}>
              <Button
                size="sm"
                variant="danger"
                onClick={() => suspendMutation.mutate(selected.id)}
                disabled={suspendMutation.isPending}
              >
                Suspend user
              </Button>
              <Button
                size="sm"
                onClick={() => acknowledgeMutation.mutate(selected.id)}
                disabled={acknowledgeMutation.isPending}
              >
                Acknowledge
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  const user = window.prompt('Assign to username:');
                  if (user?.trim()) {
                    assignMutation.mutate({ id: selected.id, assignee: user.trim() });
                  }
                }}
                disabled={assignMutation.isPending}
              >
                {assignMutation.isPending ? 'Assigning…' : 'Assign'}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
