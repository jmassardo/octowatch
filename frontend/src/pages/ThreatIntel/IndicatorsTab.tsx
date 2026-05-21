import { useState, useCallback, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listIndicators,
  createIndicator,
  deleteIndicator,
  bulkCreateIndicators,
  listFeeds,
} from '../../api/threatIntel';
import type {
  ThreatIntelIndicator,
  IndicatorCreateRequest,
  BulkIndicatorItem,
} from '../../api/threatIntel';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Pagination } from '../../components/primitives/Pagination';
import { Drawer } from '../../components/primitives/Drawer';
import { formatAbsolute } from '../../utils/dates';
import { useQueryParam } from '../../hooks/useQueryParam';
import styles from './ThreatIntel.module.css';

const PAGE_SIZE = 50;

interface IndicatorFormData {
  indicator_type: string;
  value: string;
  source: string;
  confidence: number;
  notes: string;
}

const EMPTY_FORM: IndicatorFormData = {
  indicator_type: 'domain',
  value: '',
  source: 'manual',
  confidence: 0.8,
  notes: '',
};

function parseCsvIndicators(content: string): BulkIndicatorItem[] {
  const lines = content.split('\n').filter((l) => l.trim() && !l.startsWith('#'));
  const items: BulkIndicatorItem[] = [];
  for (const line of lines) {
    const parts = line.split(',').map((p) => p.trim());
    if (parts.length >= 2) {
      items.push({
        indicator_type: parts[0] || 'domain',
        value: parts[1],
        source: parts[2] || 'csv-import',
        confidence: parts[3] ? parseFloat(parts[3]) : 0.8,
      });
    } else if (parts.length === 1 && parts[0]) {
      items.push({
        indicator_type: 'domain',
        value: parts[0],
        source: 'csv-import',
      });
    }
  }
  return items;
}

export function IndicatorsTab() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [feedFilter, setFeedFilter] = useState('');
  const [page, setPage] = useState(1);
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState<IndicatorFormData>(EMPTY_FORM);
  const [bulkResult, setBulkResult] = useState<{ created: number; duplicates: number } | null>(
    null,
  );
  const [selectedIndicatorParam, setSelectedIndicatorParam] = useQueryParam('indicator', '');

  // Debounce search
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const handleSearchChange = useCallback((val: string) => {
    setSearch(val);
    clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(() => {
      setDebouncedSearch(val);
      setPage(1);
    }, 300);
  }, []);

  const {
    data: indicatorsData,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['threat-intel', 'indicators', typeFilter, debouncedSearch, page],
    queryFn: () =>
      listIndicators({
        indicator_type: typeFilter || undefined,
        search: debouncedSearch || undefined,
        active_only: true,
        page,
        page_size: PAGE_SIZE,
      }),
  });

  const { data: feedsData } = useQuery({
    queryKey: ['threat-intel', 'feeds'],
    queryFn: listFeeds,
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: (body: IndicatorCreateRequest) => createIndicator(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['threat-intel', 'indicators'] });
      setShowModal(false);
      setFormData(EMPTY_FORM);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteIndicator(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['threat-intel', 'indicators'] });
    },
  });

  const bulkMutation = useMutation({
    mutationFn: (items: BulkIndicatorItem[]) => bulkCreateIndicators(items),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['threat-intel', 'indicators'] });
      setBulkResult({ created: result.created, duplicates: result.duplicates });
      setTimeout(() => setBulkResult(null), 5000);
    },
  });

  const handleCreate = useCallback(() => {
    createMutation.mutate({
      indicator_type: formData.indicator_type,
      value: formData.value,
      source: formData.source,
      confidence: formData.confidence,
      notes: formData.notes || null,
    });
  }, [formData, createMutation]);

  const handleDelete = useCallback(
    (ind: ThreatIntelIndicator) => {
      if (window.confirm(`Deactivate indicator "${ind.value}"?`)) {
        deleteMutation.mutate(ind.id);
      }
    },
    [deleteMutation],
  );

  const handleFileImport = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        const content = ev.target?.result as string;
        const items = parseCsvIndicators(content);
        if (items.length > 0) {
          bulkMutation.mutate(items);
        }
      };
      reader.readAsText(file);
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    },
    [bulkMutation],
  );

  const handleExport = useCallback(() => {
    const items = indicatorsData?.items ?? [];
    const csvRows = ['indicator_type,value,source,confidence,added_at'];
    for (const ind of items) {
      csvRows.push(
        `${ind.indicator_type},${ind.value},${ind.source},${ind.confidence},${ind.added_at}`,
      );
    }
    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'threat-intel-indicators.csv';
    a.click();
    URL.revokeObjectURL(url);
  }, [indicatorsData]);

  const items = indicatorsData?.items ?? [];
  const total = indicatorsData?.total ?? 0;
  const feeds = feedsData?.items ?? [];

  // Filter by feed if selected
  const filteredItems = feedFilter ? items.filter((i) => String(i.feed_id) === feedFilter) : items;

  const selectedIndicatorId = selectedIndicatorParam ? parseInt(selectedIndicatorParam, 10) : null;
  const selectedIndicator =
    selectedIndicatorId !== null
      ? (filteredItems.find((i) => i.id === selectedIndicatorId) ?? null)
      : null;

  const openIndicatorDetail = useCallback(
    (ind: ThreatIntelIndicator) => {
      setSelectedIndicatorParam(String(ind.id), { replace: true });
    },
    [setSelectedIndicatorParam],
  );

  const closeIndicatorDetail = useCallback(() => {
    setSelectedIndicatorParam('', { replace: true });
  }, [setSelectedIndicatorParam]);

  if (isLoading) {
    return (
      <div className={styles.centered}>
        <Spinner />
      </div>
    );
  }

  if (isError) {
    return <ErrorBanner message="Failed to load indicators" onRetry={refetch} />;
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <input
          className={styles.searchInput}
          placeholder="Search indicators…"
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
          aria-label="Search indicators"
        />
        <select
          className={styles.filterSelect}
          value={typeFilter}
          onChange={(e) => {
            setTypeFilter(e.target.value);
            setPage(1);
          }}
          aria-label="Filter by type"
        >
          <option value="">All types</option>
          <option value="domain">Domain</option>
          <option value="ip">IP</option>
          <option value="pattern">Pattern</option>
        </select>
        <select
          className={styles.filterSelect}
          value={feedFilter}
          onChange={(e) => setFeedFilter(e.target.value)}
          aria-label="Filter by feed"
        >
          <option value="">All feeds</option>
          <option value="manual">Manual</option>
          {feeds.map((f) => (
            <option key={f.id} value={String(f.id)}>
              {f.name}
            </option>
          ))}
        </select>
        <button className={styles.btnPrimary} onClick={() => setShowModal(true)}>
          + Add Indicator
        </button>
        <button className={styles.btnSmall} onClick={() => fileInputRef.current?.click()}>
          Import CSV
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.txt"
          style={{ display: 'none' }}
          onChange={handleFileImport}
          aria-label="Import CSV file"
        />
        <button className={styles.btnSmall} onClick={handleExport} disabled={items.length === 0}>
          Export
        </button>
      </div>

      {bulkResult && (
        <div
          style={{
            padding: '8px 12px',
            marginBottom: 12,
            borderRadius: 6,
            background: 'rgba(var(--success-rgb), 0.1)',
            color: 'var(--done)',
            fontSize: 13,
          }}
        >
          Bulk import complete: {bulkResult.created} created, {bulkResult.duplicates} duplicates
        </div>
      )}

      {filteredItems.length === 0 ? (
        <div className={styles.emptyState}>
          No indicators found. Add indicators manually or import from a CSV file.
        </div>
      ) : (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.dataTable}>
              <thead>
                <tr>
                  <th scope="col">Value</th>
                  <th scope="col">Type</th>
                  <th scope="col">Source</th>
                  <th scope="col">Confidence</th>
                  <th scope="col">First Seen</th>
                  <th scope="col">Notes</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map((ind) => (
                  <tr
                    key={ind.id}
                    onClick={() => openIndicatorDetail(ind)}
                    className={styles.clickableRow}
                    role="button"
                    tabIndex={0}
                    aria-label={`View details for ${ind.value}`}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        openIndicatorDetail(ind);
                      }
                    }}
                  >
                    <td>
                      <code>{ind.value}</code>
                    </td>
                    <td>
                      <span className={styles.typeBadge}>{ind.indicator_type}</span>
                    </td>
                    <td>{ind.source}</td>
                    <td>
                      <div className={styles.confidenceBar}>
                        <div
                          className={styles.confidenceFill}
                          style={{ width: `${ind.confidence * 100}%` }}
                        />
                      </div>
                      <span style={{ marginLeft: 6, fontSize: 11 }}>
                        {Math.round(ind.confidence * 100)}%
                      </span>
                    </td>
                    <td>{formatAbsolute(ind.added_at)}</td>
                    <td>
                      <span className={styles.truncate}>{ind.notes ?? '—'}</span>
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <button className={styles.btnDanger} onClick={() => handleDelete(ind)}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            hasNext={page * PAGE_SIZE < total}
            onPageChange={setPage}
          />
        </>
      )}

      {showModal && (
        <div className={styles.modalOverlay} onClick={() => setShowModal(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <h2 className={styles.modalTitle}>Add Indicator</h2>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Type</label>
              <select
                className={styles.formSelect}
                value={formData.indicator_type}
                onChange={(e) => setFormData({ ...formData, indicator_type: e.target.value })}
              >
                <option value="domain">Domain</option>
                <option value="ip">IP Address</option>
                <option value="pattern">Pattern</option>
              </select>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Value</label>
              <input
                className={styles.formInput}
                value={formData.value}
                onChange={(e) => setFormData({ ...formData, value: e.target.value })}
                placeholder="e.g. malicious-domain.com or 192.168.1.0/24"
              />
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Source</label>
              <input
                className={styles.formInput}
                value={formData.source}
                onChange={(e) => setFormData({ ...formData, source: e.target.value })}
                placeholder="e.g. internal-investigation"
              />
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Confidence (0-1)</label>
              <input
                className={styles.formInput}
                type="number"
                step={0.05}
                min={0}
                max={1}
                value={formData.confidence}
                onChange={(e) => setFormData({ ...formData, confidence: Number(e.target.value) })}
              />
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Notes (optional)</label>
              <textarea
                className={styles.formTextarea}
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Additional context…"
              />
            </div>

            <div className={styles.modalActions}>
              <button className={styles.btnSmall} onClick={() => setShowModal(false)}>
                Cancel
              </button>
              <button
                className={styles.btnPrimary}
                onClick={handleCreate}
                disabled={!formData.value || !formData.source || createMutation.isPending}
              >
                Create Indicator
              </button>
            </div>
          </div>
        </div>
      )}

      <Drawer open={!!selectedIndicator} onClose={closeIndicatorDetail} title="Indicator Details">
        {selectedIndicator && (
          <div className={styles.drawerContent}>
            <dl className={styles.detailList}>
              <dt>Value</dt>
              <dd>
                <code>{selectedIndicator.value}</code>
              </dd>

              <dt>Type</dt>
              <dd>
                <span className={styles.typeBadge}>{selectedIndicator.indicator_type}</span>
              </dd>

              <dt>Source</dt>
              <dd>{selectedIndicator.source}</dd>

              <dt>Confidence</dt>
              <dd>{Math.round(selectedIndicator.confidence * 100)}%</dd>

              <dt>Active</dt>
              <dd>{selectedIndicator.active ? 'Yes' : 'No'}</dd>

              <dt>First Seen</dt>
              <dd>{formatAbsolute(selectedIndicator.added_at)}</dd>

              <dt>Added By</dt>
              <dd>{selectedIndicator.added_by}</dd>

              <dt>Expires</dt>
              <dd>
                {selectedIndicator.expires_at
                  ? formatAbsolute(selectedIndicator.expires_at)
                  : 'Never'}
              </dd>

              <dt>Feed ID</dt>
              <dd>{selectedIndicator.feed_id ?? 'Manual'}</dd>

              <dt>Notes</dt>
              <dd>{selectedIndicator.notes ?? '—'}</dd>

              {selectedIndicator.metadata_json && (
                <>
                  <dt>Metadata</dt>
                  <dd>
                    <pre style={{ fontSize: 11, margin: 0, whiteSpace: 'pre-wrap' }}>
                      {JSON.stringify(selectedIndicator.metadata_json, null, 2)}
                    </pre>
                  </dd>
                </>
              )}
            </dl>

            <div className={styles.drawerActions}>
              <button
                className={styles.btnDanger}
                onClick={() => {
                  handleDelete(selectedIndicator);
                  closeIndicatorDetail();
                }}
              >
                Remove
              </button>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
