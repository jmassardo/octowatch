import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listDetections,
  updateDetectionStatus,
  deleteDetection,
  assignDetection,
} from '../../api/detections';
import type { DetectionResponse } from '../../types/detections';
import { SeverityDot } from '../../components/primitives/SeverityDot';
import { Label } from '../../components/primitives/Label';
import { Button } from '../../components/primitives/Button';
import { CodeBlock } from '../../components/primitives/CodeBlock';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Pagination } from '../../components/primitives/Pagination';
import { formatRelativeShort } from '../../utils/dates';
import styles from './Threats.module.css';

/**
 * Safely convert any value to a display string.
 * Prevents `[object Object]` from appearing when the API returns an
 * object where a string was expected, or when a field typed as
 * `Record<string, unknown>` is accidentally rendered as JSX text.
 */
function safeText(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}

/**
 * Safely retrieve the length of an array-like value.
 * Returns 0 when the value is not actually an array, preventing
 * runtime errors if the API sends null/undefined for `event_ids`.
 */
function safeArrayLength(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

/**
 * Safely check whether an object has entries.
 * Returns false when the value is not a plain object, preventing
 * `Object.keys(null)` crashes if the API sends null for `context_data`.
 */
function hasEntries(value: unknown): value is Record<string, unknown> {
  return (
    value !== null &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    Object.keys(value).length > 0
  );
}

type TabFilter = 'open' | 'investigating' | 'closed' | 'acknowledged' | 'all';

export function ThreatsPage() {
  const [tab, setTab] = useState<TabFilter>('open');
  const [selected, setSelected] = useState<DetectionResponse | null>(null);
  const [filtersVisible, setFiltersVisible] = useState(false);
  const [severityFilter, setSeverityFilter] = useState('');
  const [page, setPage] = useState(1);
  const qc = useQueryClient();
  const navigate = useNavigate();

  const statusMap: Record<TabFilter, string | undefined> = {
    open: 'open',
    investigating: 'investigating',
    closed: 'resolved',
    acknowledged: 'false_positive',
    all: undefined,
  };

  const PAGE_SIZE = 25;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['detections', tab, severityFilter, page],
    queryFn: () =>
      listDetections({
        status: statusMap[tab],
        severity: severityFilter || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
  });

  // Fetch counts for each tab so badges stay current
  const { data: openData } = useQuery({
    queryKey: ['detections', 'count-open'],
    queryFn: () => listDetections({ status: 'open', page_size: 1 }),
  });
  const { data: investData } = useQuery({
    queryKey: ['detections', 'count-investigating'],
    queryFn: () => listDetections({ status: 'investigating', page_size: 1 }),
  });
  const { data: closedData } = useQuery({
    queryKey: ['detections', 'count-closed'],
    queryFn: () => listDetections({ status: 'resolved', page_size: 1 }),
  });
  const { data: ackData } = useQuery({
    queryKey: ['detections', 'count-ack'],
    queryFn: () => listDetections({ status: 'false_positive', page_size: 1 }),
  });
  const { data: allData } = useQuery({
    queryKey: ['detections', 'count-all'],
    queryFn: () => listDetections({ page_size: 1 }),
  });

  const tabCounts: Record<TabFilter, number | null> = {
    open: openData?.total ?? null,
    investigating: investData?.total ?? null,
    closed: closedData?.total ?? null,
    acknowledged: ackData?.total ?? null,
    all: allData?.total ?? null,
  };

  const acknowledgeMutation = useMutation({
    mutationFn: (id: number) => updateDetectionStatus(id, { status: 'false_positive' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['detections'] });
    },
  });

  const assignMutation = useMutation({
    mutationFn: ({ id, assignee }: { id: number; assignee: string }) =>
      assignDetection(id, { assigned_to: assignee }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['detections'] });
    },
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
        <div className={styles.pageSub}>
          Rule-based and ML-powered detections from audit log analysis
        </div>
        <div className={styles.topActions}>
          <Button size="sm" onClick={() => setFiltersVisible((v) => !v)}>
            Filter
          </Button>
          <Button size="sm" variant="primary" onClick={() => navigate('/rules')}>
            New rule
          </Button>
        </div>
        {filtersVisible && (
          <div className={styles.topActions} style={{ gap: 8 }}>
            <select
              value={severityFilter}
              onChange={(e) => {
                setSeverityFilter(e.target.value);
                setPage(1);
              }}
              style={{
                padding: '4px 8px',
                borderRadius: 6,
                border: '1px solid var(--border)',
                background: 'var(--canvas-subtle)',
                color: 'var(--fg)',
                fontSize: 13,
              }}
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
            {(['open', 'investigating', 'closed', 'acknowledged', 'all'] as TabFilter[]).map(
              (t) => {
                const count = tabCounts[t];
                const countStr = count != null ? ` (${count})` : '';
                const tabLabel =
                  t === 'open'
                    ? 'Open'
                    : t === 'investigating'
                      ? 'Investigating'
                      : t === 'closed'
                        ? 'Closed'
                        : t === 'acknowledged'
                          ? 'Acknowledged'
                          : 'All';
                return (
                  <button
                    key={t}
                    className={[styles.ilTab, tab === t && styles.active].filter(Boolean).join(' ')}
                    onClick={() => {
                      setTab(t);
                      setPage(1);
                    }}
                  >
                    {tabLabel}
                    {count != null && <span className={styles.tabBadge}>{count}</span>}
                    {count == null && countStr}
                  </button>
                );
              },
            )}
          </div>

          {isLoading && (
            <div className={styles.loadingRow}>
              <Spinner />
            </div>
          )}
          {isError && (
            <div className={styles.loadingRow}>
              <ErrorBanner message="Failed to load detections" onRetry={refetch} />
            </div>
          )}

          {!isLoading && !isError && items.length === 0 && (
            <div className={styles.emptyRow}>
              {tab === 'open'
                ? 'No open threats detected — all clear ✓'
                : tab === 'closed'
                  ? 'No closed detections. Resolved detections will appear here.'
                  : 'No detections found'}
            </div>
          )}

          {items.map((d) => (
            <div
              key={d.id}
              className={[styles.ilRow, selected?.id === d.id && styles.selected]
                .filter(Boolean)
                .join(' ')}
              onClick={() => setSelected(d)}
            >
              <SeverityDot severity={d.severity} style={{ marginTop: 4 }} />
              <div className={styles.ilMeta}>
                <div className={styles.ilTitle}>{safeText(d.title)}</div>
                <div className={styles.ilSub}>
                  <Label variant={sevLabelVariant(d.severity)}>{d.severity}</Label>
                  {d.rule_name && <Label variant="muted">{safeText(d.rule_name)}</Label>}
                  {d.actor && (
                    <span>
                      actor: <span className={styles.mention}>@{safeText(d.actor)}</span>
                    </span>
                  )}
                  {d.org && <span>· {safeText(d.org)}</span>}
                </div>
              </div>
              <div className={styles.ilTime}>{formatRelativeShort(d.triggered_at)}</div>
            </div>
          ))}

          {data && (
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={data.total}
              hasNext={data.has_next}
              onPageChange={setPage}
            />
          )}
        </div>
      </div>

      <div className={[styles.splitPanel, selected && styles.open].filter(Boolean).join(' ')}>
        {selected && (
          <>
            <div className={styles.panelHeader}>
              <div style={{ fontWeight: 600 }}>{safeText(selected.title)}</div>
              <button className={styles.panelClose} onClick={() => setSelected(null)}>
                &#215;
              </button>
            </div>

            <div className={styles.panelLabels}>
              <Label variant={sevLabelVariant(selected.severity)}>{selected.severity}</Label>
              {selected.rule_name && <Label variant="muted">{safeText(selected.rule_name)}</Label>}
              {selected.confidence && <Label variant="done">{safeText(selected.confidence)}</Label>}
            </div>

            <p className={styles.panelDesc}>{safeText(selected.description)}</p>

            {safeArrayLength(selected.event_ids) > 0 && (
              <div className={styles.relatedEvents}>
                <span className={styles.evidenceLabel}>Related events</span>
                <span
                  role="button"
                  tabIndex={0}
                  className={styles.eventCountLink}
                  aria-label={`${safeArrayLength(selected.event_ids)} related events — view in events page`}
                  onClick={() => {
                    const params = new URLSearchParams();
                    if (selected.actor) params.set('actor', selected.actor);
                    if (selected.rule_name) params.set('action', selected.rule_name);
                    navigate(`/events?${params.toString()}`);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      const params = new URLSearchParams();
                      if (selected.actor) params.set('actor', selected.actor);
                      if (selected.rule_name) params.set('action', selected.rule_name);
                      navigate(`/events?${params.toString()}`);
                    }
                  }}
                >
                  {safeArrayLength(selected.event_ids)} event
                  {safeArrayLength(selected.event_ids) === 1 ? '' : 's'} →
                </span>
              </div>
            )}

            {hasEntries(selected.context_data) && (
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
