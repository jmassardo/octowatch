import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listEvents } from '../../api/events';
import { useDebounce } from '../../hooks/useDebounce';
import { Label } from '../../components/primitives/Label';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Events.module.css';

function actionVariant(action: string) {
  if (action.includes('destroy') || action.includes('delete') || action.includes('visibility')) return 'danger' as const;
  if (action.includes('access') || action.includes('rename')) return 'attention' as const;
  return 'muted' as const;
}

function formatTs(iso: string): string {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  }).format(new Date(iso)).replace(',', '');
}

export function EventsPage() {
  const [search, setSearch] = useState('');
  const [chips, setChips] = useState<string[]>(['org:acme-corp', 'action:repo.*', 'after:2024-01-14']);
  const [page, setPage] = useState(1);

  const debouncedSearch = useDebounce(search, 400);

  // Parse chips into params
  const params = Object.fromEntries(
    chips.flatMap((c) => {
      const [k, v] = c.split(':');
      if (!k || !v) return [];
      if (k === 'org') return [['org', v]];
      if (k === 'actor') return [['actor', v]];
      if (k === 'action') return [['action', v]];
      if (k === 'after') return [['since', v]];
      if (k === 'before') return [['until', v]];
      return [];
    }),
  );

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['events', chips, debouncedSearch, page],
    queryFn: () => listEvents({ ...params, page, page_size: 20 }),
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  function removeChip(chip: string) {
    setChips((prev) => prev.filter((c) => c !== chip));
  }

  function handleSearchKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && search.trim()) {
      const val = search.trim();
      if (!chips.includes(val)) setChips((prev) => [...prev, val]);
      setSearch('');
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Events Explorer</div>
      <div className={styles.pageSub}>Search and explore raw audit log events across all organizations</div>

      <div className={styles.searchBar}>
        <svg width="16" height="16" fill="var(--fg-subtle)" viewBox="0 0 16 16">
          <path d="M10.68 11.74a6 6 0 01-7.922-8.982 6 6 0 018.982 7.922l3.04 3.04a.749.749 0 11-1.06 1.06zm-3.18.26a4.5 4.5 0 100-9 4.5 4.5 0 000 9z" />
        </svg>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={handleSearchKey}
          placeholder='Search events... e.g. action:repo.create actor:@suspicious.*'
        />
      </div>

      <div className={styles.filterChips}>
        {chips.map((c) => (
          <span key={c} className={styles.chip}>
            {c}
            <span className={styles.chipX} onClick={() => removeChip(c)}>&#215;</span>
          </span>
        ))}
        <Button size="sm" style={{ borderRadius: 12 }}>+ Add filter</Button>
      </div>

      <div className={styles.tableHeader}>
        <span className={styles.resultCount}>{total.toLocaleString()} events matching filters</span>
        <div className={styles.tableActions}>
          <Button size="sm">Export CSV</Button>
          <Button size="sm">Save query</Button>
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
                <td className={styles.ts}>{formatTs(e.created_at)}</td>
                <td><Label variant={actionVariant(e.action)}>{e.action}</Label></td>
                <td><span className={styles.mention}>@{e.actor ?? '—'}</span></td>
                <td>{e.repo ?? e.org ?? '—'}</td>
                <td>
                  {e.source_ip && <code style={{ fontSize: 11 }}>{e.source_ip}</code>}
                  {e.geo_country_code && <span className={styles.country}>{e.geo_country_code}</span>}
                </td>
                <td><Button size="sm">Details</Button></td>
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
    </div>
  );
}
