import { useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { listEvents, getEvent } from '../../api/events';
import {
  getSuggestedActions,
  getSuggestedActors,
  getSuggestedRepos,
  getSuggestedOrgs,
  getSuggestedNamespaces,
} from '../../api/suggestions';
import type { EventListParams, EventResponse } from '../../types/events';
import { useDebounce } from '../../hooks/useDebounce';
import { Label } from '../../components/primitives/Label';
import { Button } from '../../components/primitives/Button';
import { PageHeader } from '../../components/common/PageHeader';
import { EmptyState } from '../../components/common/EmptyState';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';

import { EventSearchInput } from './EventSearchInput';
import { EventDetail } from './EventDetail';
import { SEARCH_KEY_MAP, parseSearchFilters, downloadCsv } from './utils';
import { formatCompact } from '../../utils/dates';
import styles from './Events.module.css';

function actionVariant(action: string) {
  if (action.includes('destroy') || action.includes('delete') || action.includes('visibility'))
    return 'danger' as const;
  if (action.includes('access') || action.includes('rename')) return 'attention' as const;
  return 'muted' as const;
}

/** Threshold at which we show a "narrow your filters" message. */
const LARGE_RESULT_THRESHOLD = 5_000;

/** Threshold for showing "500,000+" text. */
const VERY_LARGE_RESULT_THRESHOLD = 500_000;

function formatResultCount(total: number, isEstimated: boolean): string {
  if (isEstimated && total >= VERY_LARGE_RESULT_THRESHOLD) {
    return '500,000+';
  }
  const formatted = total.toLocaleString();
  return isEstimated ? `≈ ${formatted}` : formatted;
}

// Reverse map: API param name → user-friendly chip key
const API_TO_CHIP_KEY: Record<string, string> = {
  source_ip: 'ip',
  geo_country_code: 'country',
  actor_is_bot: 'bot',
};

const SUPPORTED_FILTER_PARAMS = [
  'repo',
  'actor',
  'action',
  'org',
  'since',
  'until',
  'namespace',
  'source_ip',
  'geo_country_code',
  'actor_is_bot',
];

export function EventsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState('');

  // Derive chips from URL query params (URL is source of truth)
  const chips = useMemo(() => {
    const result: string[] = [];
    for (const param of SUPPORTED_FILTER_PARAMS) {
      const val = searchParams.get(param);
      if (val) {
        const chipKey = API_TO_CHIP_KEY[param] ?? param;
        result.push(`${chipKey}:${val}`);
      }
    }
    return result;
  }, [searchParams]);

  const [page, setPage] = useState(1);
  const [cursors, setCursors] = useState<string[]>([]);
  const [sortKey] = useState<NonNullable<EventListParams['sort']>>('created_at_desc');
  const [detailEvent, setDetailEvent] = useState<EventResponse | null>(null);

  // Deep link: restore selected event from URL ?event=<id>
  const selectedEventId = searchParams.get('event');
  const { data: deepLinkEvent } = useQuery({
    queryKey: ['event-detail', selectedEventId],
    queryFn: () => getEvent(Number(selectedEventId)),
    enabled: selectedEventId !== null && !isNaN(Number(selectedEventId)),
  });

  // Derive the effective detail event: local state or deep-linked
  const effectiveDetailEvent = detailEvent ?? deepLinkEvent ?? null;

  /** Select an event and update the URL */
  const selectEvent = useCallback(
    (event: EventResponse | null) => {
      setDetailEvent(event);
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (event) {
            next.set('event', String(event.id));
          } else {
            next.delete('event');
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const { data: actionsData } = useQuery({
    queryKey: ['suggestions', 'actions'],
    queryFn: getSuggestedActions,
    staleTime: 5 * 60 * 1000,
  });

  const { data: actorsData } = useQuery({
    queryKey: ['suggestions', 'actors'],
    queryFn: getSuggestedActors,
    staleTime: 5 * 60 * 1000,
  });

  const { data: reposData } = useQuery({
    queryKey: ['suggestions', 'repos'],
    queryFn: getSuggestedRepos,
    staleTime: 5 * 60 * 1000,
  });

  const { data: orgsData } = useQuery({
    queryKey: ['suggestions', 'orgs'],
    queryFn: getSuggestedOrgs,
    staleTime: 5 * 60 * 1000,
  });

  const { data: namespacesData } = useQuery({
    queryKey: ['suggestions', 'namespaces'],
    queryFn: getSuggestedNamespaces,
    staleTime: 5 * 60 * 1000,
  });

  const actionSuggestions = actionsData?.actions ?? [];
  const actorSuggestions = actorsData?.actors ?? [];
  const repoSuggestions = reposData?.repos ?? [];
  const orgSuggestions = orgsData?.orgs ?? [];
  const namespaceSuggestions = namespacesData?.namespaces ?? [];

  const debouncedSearch = useDebounce(search, 400);

  // Parse chips into params (split only on first colon to preserve values like timestamps)
  const chipParams = Object.fromEntries(
    chips.flatMap((c): [string, string | boolean][] => {
      const idx = c.indexOf(':');
      if (idx === -1) return [];
      const k = c.slice(0, idx);
      const v = c.slice(idx + 1);
      if (!k || !v) return [];
      const paramKey = SEARCH_KEY_MAP[k];
      if (!paramKey) return [];
      if (paramKey === 'actor_is_bot') return [[paramKey, v.toLowerCase() === 'true']];
      return [[paramKey, v]];
    }),
  );

  // Parse real-time search input for key:value filters
  const searchFilters = parseSearchFilters(debouncedSearch);

  // Add a chip by updating URL params
  const addChip = useCallback(
    (chip: string) => {
      const idx = chip.indexOf(':');
      if (idx === -1) return;
      const k = chip.slice(0, idx);
      const v = chip.slice(idx + 1);
      const paramKey = SEARCH_KEY_MAP[k];
      if (!paramKey || !v) return;
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set(paramKey, v);
        return next;
      });
      setCursors([]);
      setPage(1);
    },
    [setSearchParams],
  );

  const currentCursor = cursors.length > 0 ? cursors[cursors.length - 1] : undefined;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['events', chips, debouncedSearch, currentCursor, sortKey],
    queryFn: () =>
      listEvents({
        ...chipParams,
        ...searchFilters,
        sort: sortKey,
        cursor: currentCursor,
        page_size: 20,
      }),
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const countIsEstimated = data?.count_is_estimated ?? false;

  function removeChip(chip: string) {
    const idx = chip.indexOf(':');
    if (idx === -1) return;
    const k = chip.slice(0, idx);
    const paramKey = SEARCH_KEY_MAP[k];
    if (!paramKey) return;
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete(paramKey);
      return next;
    });
    setPage(1);
    setCursors([]);
  }

  const eventColumns: ColumnDef<EventResponse>[] = useMemo(
    () => [
      {
        key: 'created_at',
        header: 'Timestamp',
        sortable: true,
        filterable: true,
        helpText: 'When the event occurred',
        render: (e) => <span className={styles.ts}>{formatCompact(e.created_at)}</span>,
        sortValue: (e) => new Date(e.created_at),
        filterValue: (e) => formatCompact(e.created_at),
      },
      {
        key: 'action',
        header: 'Action',
        sortable: true,
        filterable: true,
        helpText: 'The audit log action that was performed',
        render: (e) => (
          <span
            role="button"
            tabIndex={0}
            style={{ cursor: 'pointer' }}
            title={`Filter by action: ${e.action}`}
            onClick={(ev) => {
              ev.stopPropagation();
              const chip = `action:${e.action}`;
              if (!chips.includes(chip)) {
                addChip(chip);
                setPage(1);
              }
            }}
            onKeyDown={(ev) => {
              if (ev.key === 'Enter' || ev.key === ' ') {
                ev.stopPropagation();
                const chip = `action:${e.action}`;
                if (!chips.includes(chip)) {
                  addChip(chip);
                  setPage(1);
                }
              }
            }}
          >
            <Label variant={actionVariant(e.action)}>{e.action}</Label>
          </span>
        ),
        sortValue: (e) => e.action,
        filterValue: (e) => e.action,
      },
      {
        key: 'actor',
        header: 'Actor',
        sortable: true,
        filterable: true,
        helpText: 'The user or bot that performed the action',
        render: (e) => (
          <span
            className={styles.mention}
            role="button"
            tabIndex={0}
            style={{ cursor: e.actor ? 'pointer' : undefined }}
            title={e.actor ? `Filter by actor: ${e.actor}` : undefined}
            onClick={(ev) => {
              if (!e.actor) return;
              ev.stopPropagation();
              const chip = `actor:${e.actor}`;
              if (!chips.includes(chip)) {
                addChip(chip);
                setPage(1);
              }
            }}
            onKeyDown={(ev) => {
              if (!e.actor) return;
              if (ev.key === 'Enter' || ev.key === ' ') {
                ev.stopPropagation();
                const chip = `actor:${e.actor}`;
                if (!chips.includes(chip)) {
                  addChip(chip);
                  setPage(1);
                }
              }
            }}
          >
            @{e.actor ?? '—'}
          </span>
        ),
        sortValue: (e) => e.actor ?? '',
        filterValue: (e) => e.actor ?? '',
      },
      {
        key: 'repo',
        header: 'Repository',
        sortable: true,
        filterable: true,
        helpText: 'The repository or organization associated with the event',
        render: (e) => {
          const val = e.repo ?? e.org;
          const chipKey = e.repo ? 'repo' : 'org';
          return (
            <span
              role="button"
              tabIndex={0}
              style={{ cursor: val ? 'pointer' : undefined }}
              title={val ? `Filter by ${chipKey}: ${val}` : undefined}
              onClick={(ev) => {
                if (!val) return;
                ev.stopPropagation();
                const chip = `${chipKey}:${val}`;
                if (!chips.includes(chip)) {
                  addChip(chip);
                  setPage(1);
                }
              }}
              onKeyDown={(ev) => {
                if (!val) return;
                if (ev.key === 'Enter' || ev.key === ' ') {
                  ev.stopPropagation();
                  const chip = `${chipKey}:${val}`;
                  if (!chips.includes(chip)) {
                    addChip(chip);
                    setPage(1);
                  }
                }
              }}
            >
              {val ?? '—'}
            </span>
          );
        },
        sortValue: (e) => e.repo ?? e.org ?? '',
        filterValue: (e) => e.repo ?? e.org ?? '',
      },
      {
        key: 'ip_location',
        header: 'IP / Location',
        sortable: true,
        filterable: true,
        helpText: 'Source IP address and geographic location of the event',
        render: (e) => (
          <>
            {e.source_ip && <code style={{ fontSize: 11 }}>{e.source_ip}</code>}
            {e.geo_country_code && <span className={styles.country}>{e.geo_country_code}</span>}
          </>
        ),
        sortValue: (e) => e.source_ip ?? '',
        filterValue: (e) => [e.source_ip ?? '', e.geo_country_code ?? ''].join(' ').trim(),
      },
    ],
    [chips, addChip],
  );

  return (
    <div className={styles.splitLayout}>
      <div className={styles.splitMain}>
        <PageHeader
          title="Events Explorer"
          description="Search and explore raw audit log events across all organizations"
          showHelp
        />

        <div className={styles.searchBar}>
          <svg width="16" height="16" fill="var(--fg-subtle)" viewBox="0 0 16 16">
            <path d="M10.68 11.74a6 6 0 01-7.922-8.982 6 6 0 018.982 7.922l3.04 3.04a.749.749 0 11-1.06 1.06zm-3.18.26a4.5 4.5 0 100-9 4.5 4.5 0 000 9z" />
          </svg>
          <EventSearchInput
            value={search}
            onChange={(val) => {
              setSearch(val);
              setCursors([]);
              setPage(1);
            }}
            onSubmit={(val) => {
              if (val.trim() && !chips.includes(val.trim())) {
                addChip(val.trim());
              }
              setSearch('');
            }}
            actionSuggestions={actionSuggestions}
            actorSuggestions={actorSuggestions}
            repoSuggestions={repoSuggestions}
            orgSuggestions={orgSuggestions}
            namespaceSuggestions={namespaceSuggestions}
            placeholder="Search events... e.g. action:repo.create actor:@suspicious.*"
            id="events-search-input"
          />
        </div>

        <div className={styles.filterChips}>
          {chips.map((c) => (
            <span key={c} className={styles.chip}>
              {c}
              <span className={styles.chipX} onClick={() => removeChip(c)}>
                &#215;
              </span>
            </span>
          ))}
        </div>

        <div className={styles.tableHeader}>
          <span className={styles.resultCount}>
            {formatResultCount(total, countIsEstimated)} events matching filters
          </span>
          <div className={styles.tableActions}>
            <Button size="sm" onClick={() => downloadCsv(items)} disabled={items.length === 0}>
              Export CSV
            </Button>
            <Button
              size="sm"
              onClick={() => {
                const name = window.prompt('Query name');
                if (name?.trim()) {
                  const saved = JSON.parse(
                    localStorage.getItem('octowatch-saved-queries') ?? '[]',
                  ) as { name: string; chips: string[] }[];
                  saved.push({ name: name.trim(), chips });
                  localStorage.setItem('octowatch-saved-queries', JSON.stringify(saved));
                }
              }}
            >
              Save query
            </Button>
          </div>
        </div>

        {isError && <ErrorBanner message="Failed to load events" onRetry={refetch} />}

        <div className={styles.tableWrap}>
          {isLoading ? (
            <div style={{ padding: 24, textAlign: 'center' }}>
              <Spinner />
            </div>
          ) : (
            <DataTable<EventResponse>
              columns={eventColumns}
              data={items}
              rowKey={(e) => e.id}
              onRowClick={(e) => selectEvent(e)}
              emptyMessage={
                <EmptyState
                  variant="filtered"
                  title="No events found"
                  description="No events match the current filters."
                />
              }
            />
          )}
        </div>

        {total > LARGE_RESULT_THRESHOLD && (
          <p className={styles.resultCount} style={{ marginTop: 8, fontStyle: 'italic' }}>
            Showing first {LARGE_RESULT_THRESHOLD.toLocaleString()} results. Narrow your filters to
            find specific events.
          </p>
        )}

        {data && data.total > 20 && (
          <div className={styles.pagination}>
            <Button
              size="sm"
              disabled={page <= 1}
              onClick={() => {
                setCursors((prev) => prev.slice(0, -1));
                setPage((p) => p - 1);
              }}
            >
              ← Prev
            </Button>
            <span className={styles.pageInfo}>Page {page}</span>
            <Button
              size="sm"
              disabled={!data.has_next || !data.next_cursor}
              onClick={() => {
                if (data.next_cursor) {
                  setCursors((prev) => [...prev, data.next_cursor!]);
                  setPage((p) => p + 1);
                }
              }}
            >
              Next →
            </Button>
          </div>
        )}
      </div>

      <div
        className={[styles.splitPanel, effectiveDetailEvent && styles.splitPanelOpen]
          .filter(Boolean)
          .join(' ')}
      >
        {effectiveDetailEvent && (
          <>
            <div className={styles.panelHeader}>
              <div style={{ fontWeight: 600 }}>{effectiveDetailEvent.action}</div>
              <button
                className={styles.panelClose}
                aria-label="Close"
                onClick={() => selectEvent(null)}
              >
                &#215;
              </button>
            </div>
            <EventDetail event={effectiveDetailEvent} />
          </>
        )}
      </div>
    </div>
  );
}
