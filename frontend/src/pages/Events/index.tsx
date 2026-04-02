import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { listEvents } from '../../api/events';
import { getSuggestedActions, getSuggestedActors } from '../../api/suggestions';
import type { EventResponse } from '../../types/events';
import { useDebounce } from '../../hooks/useDebounce';
import { Label } from '../../components/primitives/Label';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Modal } from '../../components/primitives/Modal';
import { EventSearchInput } from './EventSearchInput';
import { EventDetail } from './EventDetail';
import { SEARCH_KEY_MAP, parseSearchFilters, downloadCsv } from './utils';
import { formatCompact } from '../../utils/dates';
import styles from './Events.module.css';

function actionVariant(action: string) {
  if (action.includes('destroy') || action.includes('delete') || action.includes('visibility')) return 'danger' as const;
  if (action.includes('access') || action.includes('rename')) return 'attention' as const;
  return 'muted' as const;
}

export function EventsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const [chips, setChips] = useState<string[]>(() => {
    // Initialize chips from URL query params on first render
    const urlChips: string[] = [];
    const supportedParams = ['repo', 'actor', 'action', 'org'];
    for (const param of supportedParams) {
      const val = searchParams.get(param);
      if (val) {
        urlChips.push(`${param}:${val}`);
      }
    }
    return urlChips;
  });
  const [page, setPage] = useState(1);
  const [detailEvent, setDetailEvent] = useState<EventResponse | null>(null);
  const clearedUrlParams = useRef(false);

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

  const actionSuggestions = actionsData?.actions ?? [];
  const actorSuggestions = actorsData?.actors ?? [];

  // Clear URL params after they have been applied as initial chips
  useEffect(() => {
    if (clearedUrlParams.current) return;
    clearedUrlParams.current = true;
    const supportedParams = ['repo', 'actor', 'action', 'org'];
    const hasParams = supportedParams.some((p) => searchParams.has(p));
    if (hasParams) {
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const debouncedSearch = useDebounce(search, 400);

  // Parse chips into params (split only on first colon to preserve values like timestamps)
  const chipParams = Object.fromEntries(
    chips.flatMap((c) => {
      const idx = c.indexOf(':');
      if (idx === -1) return [];
      const k = c.slice(0, idx);
      const v = c.slice(idx + 1);
      if (!k || !v) return [];
      const paramKey = SEARCH_KEY_MAP[k];
      if (paramKey) return [[paramKey, v]];
      return [];
    }),
  );

  // Parse real-time search input for key:value filters
  const searchFilters = parseSearchFilters(debouncedSearch);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['events', chips, debouncedSearch, page],
    queryFn: () => listEvents({ ...chipParams, ...searchFilters, page, page_size: 20 }),
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  function removeChip(chip: string) {
    setChips((prev) => prev.filter((c) => c !== chip));
  }

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Events Explorer</div>
      <div className={styles.pageSub}>Search and explore raw audit log events across all organizations</div>

      <div className={styles.searchBar}>
        <svg width="16" height="16" fill="var(--fg-subtle)" viewBox="0 0 16 16">
          <path d="M10.68 11.74a6 6 0 01-7.922-8.982 6 6 0 018.982 7.922l3.04 3.04a.749.749 0 11-1.06 1.06zm-3.18.26a4.5 4.5 0 100-9 4.5 4.5 0 000 9z" />
        </svg>
        <EventSearchInput
          value={search}
          onChange={setSearch}
          onSubmit={(val) => {
            if (val.trim() && !chips.includes(val.trim())) {
              setChips((prev) => [...prev, val.trim()]);
            }
            setSearch('');
          }}
          actionSuggestions={actionSuggestions}
          actorSuggestions={actorSuggestions}
          placeholder='Search events... e.g. action:repo.create actor:@suspicious.*'
          id="events-search-input"
        />
      </div>

      <div className={styles.filterChips}>
        {chips.map((c) => (
          <span key={c} className={styles.chip}>
            {c}
            <span className={styles.chipX} onClick={() => removeChip(c)}>&#215;</span>
          </span>
        ))}
        <Button size="sm" style={{ borderRadius: 12 }} onClick={() => document.getElementById('events-search-input')?.focus()}>+ Add filter</Button>
      </div>

      <div className={styles.tableHeader}>
        <span className={styles.resultCount}>{total.toLocaleString()} events matching filters</span>
        <div className={styles.tableActions}>
          <Button size="sm" onClick={() => downloadCsv(items)} disabled={items.length === 0}>Export CSV</Button>
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
        <table>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Action</th>
              <th>Actor</th>
              <th>Repository</th>
              <th>IP / Location</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={6} style={{ padding: 24, textAlign: 'center' }}><Spinner /></td></tr>
            )}
            {!isLoading && items.length === 0 && (
              <tr><td colSpan={6} style={{ padding: 24, textAlign: 'center', color: 'var(--fg-muted)' }}>No events found</td></tr>
            )}
            {items.map((e) => (
              <tr key={e.id}>
                <td className={styles.ts}>{formatCompact(e.created_at)}</td>
                <td><Label variant={actionVariant(e.action)}>{e.action}</Label></td>
                <td><span className={styles.mention}>@{e.actor ?? '—'}</span></td>
                <td>{e.repo ?? e.org ?? '—'}</td>
                <td>
                  {e.source_ip && <code style={{ fontSize: 11 }}>{e.source_ip}</code>}
                  {e.geo_country_code && <span className={styles.country}>{e.geo_country_code}</span>}
                </td>
                <td><Button size="sm" onClick={() => setDetailEvent(e)}>Details</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.total > 20 && (
        <div className={styles.pagination}>
          <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>← Prev</Button>
          <span className={styles.pageInfo}>Page {page} of {Math.ceil(total / 20)}</span>
          <Button size="sm" disabled={!data.has_next} onClick={() => setPage((p) => p + 1)}>Next →</Button>
        </div>
      )}

      <Modal
        open={detailEvent !== null}
        onClose={() => setDetailEvent(null)}
        title={detailEvent ? `Event: ${detailEvent.action}` : ''}
        width={640}
      >
        {detailEvent && (
          <EventDetail event={detailEvent} />
        )}
      </Modal>
    </div>
  );
}
