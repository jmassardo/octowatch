import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { listDetections } from '../../api/detections';
import { listRules } from '../../api/rules';
import { getSuggestedRepos, getSuggestedActors } from '../../api/suggestions';
import type { DetectionResponse } from '../../types/detections';
import { SeverityDot } from '../../components/primitives/SeverityDot';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Pagination } from '../../components/primitives/Pagination';
import { Autocomplete } from '../../components/primitives/Autocomplete';
import { PageHeader } from '../../components/common/PageHeader';
import { InfoTooltip } from '../../components/common/InfoTooltip';
import { EmptyState } from '../../components/common/EmptyState';
import { DetectionDetailPane } from './DetectionDetailPane';
import { ChainsPane } from './ChainsPane';
import { formatRelativeShort } from '../../utils/dates';
import { useOrg } from '../../hooks/useOrg';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useEnumQueryParam, useQueryParam, useQueryParamInt, useSetQueryParams } from '../../hooks/useQueryParam';
import styles from './Threats.module.css';

/**
 * Safely convert any value to a display string.
 */
function safeText(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}

type TabFilter = 'open' | 'investigating' | 'closed' | 'acknowledged' | 'all' | 'chains';

const TAB_KEYS = ['open', 'investigating', 'closed', 'acknowledged', 'all', 'chains'] as const;

export function ThreatsPage() {
  const [tab] = useEnumQueryParam('tab', TAB_KEYS, 'open');
  const [selectedOverride, setSelectedOverride] = useState<DetectionResponse | null>(null);
  const [severityFilter] = useQueryParam('severity', '');
  const [sinceFilter] = useQueryParam('since', '');
  const [untilFilter] = useQueryParam('until', '');
  const [orgFilter] = useQueryParam('org', '');
  const [ruleIdFilter] = useQueryParam('rule_id', '');
  const [repoFilter] = useQueryParam('repo', '');
  const [actorFilter] = useQueryParam('actor', '');
  const [selectedIdParam, setSelectedIdParam] = useQueryParam('id', '');
  const [page, setPage] = useQueryParamInt('page', 1);
  const setParams = useSetQueryParams();
  const [debouncedRepo, setDebouncedRepo] = useState(repoFilter);
  const [debouncedActor, setDebouncedActor] = useState(actorFilter);
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

  const statusMap: Record<TabFilter, string | undefined> = {
    open: 'open',
    investigating: 'investigating',
    closed: 'resolved',
    acknowledged: 'false_positive',
    all: undefined,
    chains: undefined,
  };

  const PAGE_SIZE = 25;

  // Select detection and update URL with id param
  const selectDetection = useCallback(
    (d: DetectionResponse | null) => {
      setSelectedOverride(d);
      setSelectedIdParam(d ? String(d.id) : '', { replace: true });
    },
    [setSelectedIdParam],
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
    chains: null,
  };

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
        <PageHeader
          title="Threat Detections"
          description="Rule-based and ML-powered detections from audit log analysis"
          showHelp
        />
        <div className={styles.filterBar}>
          {/* Row 1: dropdowns */}
          <div className={styles.filterRow}>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 0 }}>
              <select
                value={severityFilter}
                onChange={(e) => {
                  setParams({ severity: e.target.value || null, page: null });
                }}
                className={styles.filterSelect}
              >
                <option value="">All severities</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
              <span style={{ marginLeft: 4 }}>
                <InfoTooltip content="**Severity** is defined by the triggering rule. Critical findings usually need immediate response." />
              </span>
            </label>

            {orgs.length > 1 && (
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: 0 }}>
                <select
                  value={orgFilter}
                  onChange={(e) => {
                    setParams({ org: e.target.value || null, page: null });
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
                  setParams({ rule_id: e.target.value || null, page: null });
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
                  setParams({ repo: v || null, page: null });
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
                  setParams({ actor: v || null, page: null });
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
                  setParams({ since: e.target.value || null, page: null });
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
                  setParams({ until: e.target.value || null, page: null });
                }}
                className={styles.filterDatetime}
              />
            </div>
          </div>
        </div>

        <div className={styles.issueList}>
          <div className={styles.ilFilters}>
            {(
              ['open', 'investigating', 'closed', 'acknowledged', 'all', 'chains'] as TabFilter[]
            ).map((t) => {
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
                        : t === 'chains'
                          ? 'Chains'
                          : 'All';
              return (
                <button
                  key={t}
                  className={[styles.ilTab, tab === t && styles.active].filter(Boolean).join(' ')}
                  onClick={() => {
                    setParams({ tab: t === 'open' ? null : t, page: null });
                  }}
                >
                  {tabLabel}
                  {count != null && <span className={styles.tabBadge}>{count}</span>}
                  {count == null && countStr}
                </button>
              );
            })}
          </div>

          {tab === 'chains' ? (
            <ChainsPane className={styles.chainsTab} />
          ) : (
            <>
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
                  {tab === 'open' ? (
                    <EmptyState
                      variant="setup"
                      icon="✅"
                      title="No open threats detected"
                      description="All clear — no active detections match the current filters."
                    />
                  ) : tab === 'closed' ? (
                    <EmptyState
                      variant="default"
                      icon="📋"
                      title="No closed detections"
                      description="Resolved detections will appear here."
                    />
                  ) : (
                    <EmptyState
                      variant="filtered"
                      title="No detections found"
                      description="No detections match the current filters. Try resetting them."
                    />
                  )}
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
            </>
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
          <DetectionDetailPane
            selected={selected}
            actorSuggestions={actorSuggestions}
            onClose={() => selectDetection(null)}
            onDeleted={() => selectDetection(null)}
          />
        )}
      </div>
    </div>
  );
}
