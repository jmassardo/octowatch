import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listDetections,
  updateDetectionStatus,
  deleteDetection,
  assignDetection,
} from '../../api/detections';
import { listRules } from '../../api/rules';
import { getSuggestedRepos, getSuggestedActors } from '../../api/suggestions';
import type { DetectionResponse } from '../../types/detections';
import { SeverityDot } from '../../components/primitives/SeverityDot';
import { Label } from '../../components/primitives/Label';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Pagination } from '../../components/primitives/Pagination';
import { Autocomplete } from '../../components/primitives/Autocomplete';
import { InvestigationTimeline } from './InvestigationTimeline';
import { formatRelativeShort } from '../../utils/dates';
import { useOrg } from '../../hooks/useOrg';
import { useCurrentUser } from '../../hooks/useCurrentUser';
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

function EvidenceValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  const [expanded, setExpanded] = useState(false);

  if (value === null || value === undefined) {
    return <span className={styles.evidenceMuted}>—</span>;
  }
  if (typeof value === 'string') {
    return <span className={styles.evidenceVal}>{value}</span>;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return <span className={styles.evidenceVal}>{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className={styles.evidenceMuted}>[]</span>;
    }
    const allPrimitive = value.every(
      (v) => typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean',
    );
    if (allPrimitive && value.length <= 5) {
      return <span className={styles.evidenceVal}>{value.join(', ')}</span>;
    }
    return (
      <div>
        <button
          type="button"
          className={styles.expandToggle}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? '▾' : '▸'} {value.length} item{value.length !== 1 ? 's' : ''}
        </button>
        {expanded && (
          <div className={styles.evidenceNested}>
            {value.map((item, i) => (
              <div key={i} className={styles.evidenceRow}>
                <span className={styles.evidenceKey}>[{i}]</span>
                <EvidenceValue value={item} depth={depth + 1} />
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) {
      return <span className={styles.evidenceMuted}>{'{}'}</span>;
    }
    return (
      <div>
        <button
          type="button"
          className={styles.expandToggle}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? '▾' : '▸'} {entries.length} field{entries.length !== 1 ? 's' : ''}
        </button>
        {expanded && (
          <div className={styles.evidenceNested}>
            {entries.map(([k, v]) => (
              <div key={k} className={styles.evidenceRow}>
                <span className={styles.evidenceKey}>{k}</span>
                <EvidenceValue value={v} depth={depth + 1} />
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }
  return <span className={styles.evidenceVal}>{String(value)}</span>;
}

function EvidenceDisplay({ data }: { data: Record<string, unknown> }) {
  return (
    <div className={styles.evidenceTable}>
      {Object.entries(data).map(([key, value]) => (
        <div key={key} className={styles.evidenceRow}>
          <span className={styles.evidenceKey}>{key}</span>
          <div className={styles.evidenceValWrap}>
            <EvidenceValue value={value} />
          </div>
        </div>
      ))}
    </div>
  );
}

type TabFilter = 'open' | 'investigating' | 'closed' | 'acknowledged' | 'all';

export function ThreatsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<TabFilter>('open');
  const [selectedOverride, setSelectedOverride] = useState<DetectionResponse | null>(null);
  const [investigatingId, setInvestigatingId] = useState<number | null>(null);
  const initialSeverity = searchParams.get('severity') ?? '';
  const initialRepo = searchParams.get('repo') ?? '';
  const initialActor = searchParams.get('actor') ?? '';
  const initialSince = searchParams.get('since') ?? '';
  const initialUntil = searchParams.get('until') ?? '';
  const initialOrg = searchParams.get('org') ?? '';
  const initialRuleId = searchParams.get('rule_id') ?? '';
  const selectedIdParam = searchParams.get('id') ?? '';
  const [severityFilter, setSeverityFilter] = useState(initialSeverity);
  const [repoFilter, setRepoFilter] = useState(initialRepo);
  const [debouncedRepo, setDebouncedRepo] = useState(initialRepo);
  const [actorFilter, setActorFilter] = useState(initialActor);
  const [debouncedActor, setDebouncedActor] = useState(initialActor);
  const [sinceFilter, setSinceFilter] = useState(initialSince);
  const [untilFilter, setUntilFilter] = useState(initialUntil);
  const [orgFilter, setOrgFilter] = useState(initialOrg);
  const [ruleIdFilter, setRuleIdFilter] = useState(initialRuleId);
  const [page, setPage] = useState(1);
  const { selectedOrg } = useOrg();
  const { data: currentUser } = useCurrentUser();

  useEffect(() => {
    const id = setTimeout(() => setDebouncedRepo(repoFilter), 300);
    return () => clearTimeout(id);
  }, [repoFilter]);

  useEffect(() => {
    const id = setTimeout(() => setDebouncedActor(actorFilter), 300);
    return () => clearTimeout(id);
  }, [actorFilter]);

  // Fetch rules for the rule filter dropdown
  const { data: rulesData } = useQuery({
    queryKey: ['rules', 'all'],
    queryFn: () => listRules({ limit: 500 }),
    staleTime: 5 * 60 * 1000,
  });
  const ruleOptions = rulesData?.items ?? [];
  const orgs: readonly string[] = currentUser?.scoped_orgs ?? [];

  const { data: reposData } = useQuery({
    queryKey: ['suggestions', 'repos'],
    queryFn: getSuggestedRepos,
    staleTime: 5 * 60 * 1000,
  });

  const { data: actorsData } = useQuery({
    queryKey: ['suggestions', 'actors'],
    queryFn: getSuggestedActors,
    staleTime: 5 * 60 * 1000,
  });

  const repoSuggestions = reposData?.repos ?? [];
  const actorSuggestions = actorsData?.actors ?? [];

  // Effective org: explicit orgFilter takes priority, then global selectedOrg
  const effectiveOrg = orgFilter || selectedOrg || undefined;

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

  const syncFilters = useCallback(
    (overrides: Record<string, string> = {}) => {
      const all: Record<string, string> = {
        severity: severityFilter,
        repo: repoFilter,
        actor: actorFilter,
        since: sinceFilter,
        until: untilFilter,
        org: orgFilter,
        rule_id: ruleIdFilter,
        ...overrides,
      };
      // Preserve the id param if a detection is selected
      if (selectedIdParam) {
        all.id = selectedIdParam;
      }
      const next: Record<string, string> = {};
      for (const [k, v] of Object.entries(all)) {
        if (v) next[k] = v;
      }
      setSearchParams(next, { replace: true });
    },
    [
      severityFilter,
      repoFilter,
      actorFilter,
      sinceFilter,
      untilFilter,
      orgFilter,
      ruleIdFilter,
      selectedIdParam,
      setSearchParams,
    ],
  );

  // Select detection and update URL with id param
  const selectDetection = useCallback(
    (d: DetectionResponse | null) => {
      setSelectedOverride(d);
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (d) {
          next.set('id', String(d.id));
        } else {
          next.delete('id');
        }
        return next;
      });
    },
    [setSearchParams],
  );

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: [
      'detections',
      tab,
      severityFilter,
      debouncedRepo,
      debouncedActor,
      sinceFilter,
      untilFilter,
      effectiveOrg,
      ruleIdFilter,
      page,
    ],
    queryFn: () =>
      listDetections({
        status: statusMap[tab],
        severity: severityFilter || undefined,
        repo: debouncedRepo || undefined,
        actor: debouncedActor || undefined,
        since: sinceFilter || undefined,
        until: untilFilter || undefined,
        org: effectiveOrg,
        rule_id: ruleIdFilter ? Number(ruleIdFilter) : undefined,
        page,
        page_size: PAGE_SIZE,
      }),
  });

  // Derive `selected` from URL id param + data, with override for user clicks
  const selected: DetectionResponse | null =
    selectedOverride ??
    (selectedIdParam && data?.items
      ? (data.items.find((d) => String(d.id) === selectedIdParam) ?? null)
      : null);

  // Fetch counts for each tab so badges stay current
  const { data: openData } = useQuery({
    queryKey: ['detections', 'count-open', effectiveOrg],
    queryFn: () => listDetections({ status: 'open', org: effectiveOrg, page_size: 1 }),
  });
  const { data: investData } = useQuery({
    queryKey: ['detections', 'count-investigating', effectiveOrg],
    queryFn: () => listDetections({ status: 'investigating', org: effectiveOrg, page_size: 1 }),
  });
  const { data: closedData } = useQuery({
    queryKey: ['detections', 'count-closed', effectiveOrg],
    queryFn: () => listDetections({ status: 'resolved', org: effectiveOrg, page_size: 1 }),
  });
  const { data: ackData } = useQuery({
    queryKey: ['detections', 'count-ack', effectiveOrg],
    queryFn: () => listDetections({ status: 'false_positive', org: effectiveOrg, page_size: 1 }),
  });
  const { data: allData } = useQuery({
    queryKey: ['detections', 'count-all', effectiveOrg],
    queryFn: () => listDetections({ org: effectiveOrg, page_size: 1 }),
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
      selectDetection(null);
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
        <div className={styles.filterBar}>
          {/* Row 1: dropdowns */}
          <div className={styles.filterRow}>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 0 }}>
              <select
                value={severityFilter}
                onChange={(e) => {
                  setSeverityFilter(e.target.value);
                  setPage(1);
                  syncFilters({ severity: e.target.value });
                }}
                className={styles.filterSelect}
              >
                <option value="">All severities</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
              <span
                title="Detection severity as defined by the triggering rule. Critical = immediate response needed."
                style={{ cursor: 'help', opacity: 0.5, fontSize: '0.8em', marginLeft: 4 }}
              >
                ⓘ
              </span>
            </label>

            {orgs.length > 1 && (
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: 0 }}>
                <select
                  value={orgFilter}
                  onChange={(e) => {
                    setOrgFilter(e.target.value);
                    setPage(1);
                    syncFilters({ org: e.target.value });
                  }}
                  className={styles.filterSelect}
                >
                  <option value="">All organizations</option>
                  {[...orgs]
                    .sort((a, b) => a.localeCompare(b))
                    .map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                </select>
                <span
                  title="Filter detections by the GitHub organization where the event originated."
                  style={{ cursor: 'help', opacity: 0.5, fontSize: '0.8em', marginLeft: 4 }}
                >
                  ⓘ
                </span>
              </label>
            )}

            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 0 }}>
              <select
                value={ruleIdFilter}
                onChange={(e) => {
                  setRuleIdFilter(e.target.value);
                  setPage(1);
                  syncFilters({ rule_id: e.target.value });
                }}
                className={styles.filterSelect}
              >
                <option value="">All rules</option>
                {[...ruleOptions]
                  .sort((a, b) => a.name.localeCompare(b.name))
                  .map((r) => (
                    <option key={r.id} value={String(r.id)}>
                      {r.name}
                    </option>
                  ))}
              </select>
              <span
                title="Filter by the detection rule that triggered the alert."
                style={{ cursor: 'help', opacity: 0.5, fontSize: '0.8em', marginLeft: 4 }}
              >
                ⓘ
              </span>
            </label>
          </div>

          {/* Row 2: text inputs + date/time pickers */}
          <div className={styles.filterRow}>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 0 }}>
              <Autocomplete
                value={repoFilter}
                onChange={(v) => {
                  setRepoFilter(v);
                  setPage(1);
                  syncFilters({ repo: v });
                }}
                suggestions={repoSuggestions}
                placeholder="Filter by repo…"
                className={styles.filterInput}
                ariaLabel="Filter by repo"
              />
              <span
                title="Filter by repository name. Matches detections linked to a specific repo."
                style={{ cursor: 'help', opacity: 0.5, fontSize: '0.8em', marginLeft: 4 }}
              >
                ⓘ
              </span>
            </label>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 0 }}>
              <Autocomplete
                value={actorFilter}
                onChange={(v) => {
                  setActorFilter(v);
                  setPage(1);
                  syncFilters({ actor: v });
                }}
                suggestions={actorSuggestions}
                placeholder="Filter by actor…"
                className={styles.filterInput}
                ariaLabel="Filter by actor"
              />
              <span
                title="Filter by the GitHub user who performed the action that triggered the detection."
                style={{ cursor: 'help', opacity: 0.5, fontSize: '0.8em', marginLeft: 4 }}
              >
                ⓘ
              </span>
            </label>
            <div className={styles.dateGroup}>
              <label className={styles.dateLabel}>
                From{' '}
                <span
                  title="Start of the time range for detection results. Only detections triggered after this time are shown."
                  style={{ cursor: 'help', opacity: 0.5, fontSize: '0.8em', marginLeft: 2 }}
                >
                  ⓘ
                </span>
              </label>
              <input
                type="datetime-local"
                aria-label="Since date/time"
                value={sinceFilter}
                onChange={(e) => {
                  setSinceFilter(e.target.value);
                  setPage(1);
                  syncFilters({ since: e.target.value });
                }}
                className={styles.filterDatetime}
              />
            </div>
            <div className={styles.dateGroup}>
              <label className={styles.dateLabel}>
                To{' '}
                <span
                  title="End of the time range for detection results. Only detections triggered before this time are shown."
                  style={{ cursor: 'help', opacity: 0.5, fontSize: '0.8em', marginLeft: 2 }}
                >
                  ⓘ
                </span>
              </label>
              <input
                type="datetime-local"
                aria-label="Until date/time"
                value={untilFilter}
                onChange={(e) => {
                  setUntilFilter(e.target.value);
                  setPage(1);
                  syncFilters({ until: e.target.value });
                }}
                className={styles.filterDatetime}
              />
            </div>
          </div>
        </div>

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
              onClick={() => selectDetection(d)}
            >
              <SeverityDot severity={d.severity} style={{ marginTop: 4 }} />
              <div className={styles.ilMeta}>
                <div className={styles.ilTitle}>{safeText(d.title)}</div>
                <div className={styles.ilSub}>
                  <Label variant={sevLabelVariant(d.severity)}>{d.severity}</Label>
                  {d.rule_name && <Label variant="muted">{safeText(d.rule_name)}</Label>}
                  {d.actor && (
                    <span>
                      actor:{' '}
                      <Link
                        to={`/actors/${encodeURIComponent(d.actor)}`}
                        className={styles.mention}
                        onClick={(e) => e.stopPropagation()}
                      >
                        @{safeText(d.actor)}
                      </Link>
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

      <div
        className={[
          styles.splitPanel,
          selected && styles.open,
          selected &&
            styles[
              `severity${selected.severity.charAt(0).toUpperCase()}${selected.severity.slice(1)}` as keyof typeof styles
            ],
        ]
          .filter(Boolean)
          .join(' ')}
      >
        {selected && (
          <>
            <div className={styles.panelHeader}>
              <div style={{ fontWeight: 600 }}>{safeText(selected.title)}</div>
              <button className={styles.panelClose} onClick={() => selectDetection(null)}>
                &#215;
              </button>
            </div>

            <div className={styles.panelLabels}>
              <Label variant={sevLabelVariant(selected.severity)}>{selected.severity}</Label>
              {selected.rule_name && <Label variant="muted">{safeText(selected.rule_name)}</Label>}
              {selected.confidence && <Label variant="done">{safeText(selected.confidence)}</Label>}
            </div>

            <div className={styles.sectionHeader}>Summary</div>
            <p className={styles.panelDesc}>{safeText(selected.description)}</p>

            <div className={styles.sectionHeader}>Key Details</div>
            <div className={styles.keyDetails}>
              {selected.actor && (
                <>
                  <span className={styles.keyDetailsLabel}>Actor</span>
                  <span className={styles.keyDetailsValue}>
                    <Link
                      to={`/actors/${encodeURIComponent(selected.actor)}`}
                      className={styles.mention}
                    >
                      @{safeText(selected.actor)}
                    </Link>
                  </span>
                </>
              )}
              {safeText(
                selected.repo || selected.context_data?.repo || selected.context_data?.repository,
              ) && (
                <>
                  <span className={styles.keyDetailsLabel}>Repository</span>
                  <span className={styles.keyDetailsValue}>
                    {safeText(
                      selected.repo ||
                        selected.context_data?.repo ||
                        selected.context_data?.repository,
                    )}
                  </span>
                </>
              )}
              {safeText(
                selected.org || selected.context_data?.org || selected.context_data?.organization,
              ) && (
                <>
                  <span className={styles.keyDetailsLabel}>Organization</span>
                  <span className={styles.keyDetailsValue}>
                    {safeText(
                      selected.org ||
                        selected.context_data?.org ||
                        selected.context_data?.organization,
                    )}
                  </span>
                </>
              )}
              {safeText(selected.context_data?.action) && (
                <>
                  <span className={styles.keyDetailsLabel}>Action</span>
                  <span className={styles.keyDetailsValue}>
                    {safeText(selected.context_data.action)}
                  </span>
                </>
              )}
              {safeText(selected.context_data?.what_changed) && (
                <>
                  <span className={styles.keyDetailsLabel}>What Changed</span>
                  <span className={styles.keyDetailsValue}>
                    {safeText(selected.context_data.what_changed)}
                  </span>
                </>
              )}
              {selected.source_ip && (
                <>
                  <span className={styles.keyDetailsLabel}>Source IP</span>
                  <span className={styles.keyDetailsValue}>{safeText(selected.source_ip)}</span>
                </>
              )}
              {selected.triggered_at && (
                <>
                  <span className={styles.keyDetailsLabel}>Triggered</span>
                  <span className={styles.keyDetailsValue}>
                    {formatRelativeShort(selected.triggered_at)}
                  </span>
                </>
              )}
              {selected.assigned_to && (
                <>
                  <span className={styles.keyDetailsLabel}>Assigned To</span>
                  <span className={styles.keyDetailsValue}>{safeText(selected.assigned_to)}</span>
                </>
              )}
            </div>

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
                <div className={styles.sectionHeader}>Evidence</div>
                <EvidenceDisplay data={selected.context_data} />
              </>
            )}

            <div className={styles.panelActions}>
              <Button size="sm" variant="primary" onClick={() => setInvestigatingId(selected.id)}>
                🔍 Investigate
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  window.open(
                    `/query?sql=${encodeURIComponent(`SELECT * FROM events WHERE id IN (SELECT unnest(event_ids) FROM detections WHERE id = ${selected.id})`)}`,
                    '_self',
                  );
                }}
              >
                📋 Run Playbook
              </Button>
              <Button
                size="sm"
                variant="danger"
                onClick={() => {
                  if (
                    window.confirm('Delete this detection record? This action cannot be undone.')
                  ) {
                    suspendMutation.mutate(selected.id);
                  }
                }}
                disabled={suspendMutation.isPending}
              >
                Delete Detection
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
      {investigatingId !== null && (
        <div className={styles.timelineOverlay}>
          <InvestigationTimeline
            detectionId={investigatingId}
            onClose={() => setInvestigatingId(null)}
          />
        </div>
      )}
    </div>
  );
}
