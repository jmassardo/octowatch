import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { listFeeds, createFeed, updateFeed, deleteFeed, refreshFeed } from '../../api/threatIntel';
import type { ThreatIntelFeed, FeedCreateRequest, FeedUpdateRequest } from '../../api/threatIntel';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Drawer } from '../../components/primitives/Drawer';
import { formatAbsolute } from '../../utils/dates';
import styles from './ThreatIntel.module.css';

function feedStatusClass(feed: ThreatIntelFeed): string {
  if (!feed.enabled) return styles.statusPaused;
  if (feed.last_fetch_status === 'error') return styles.statusError;
  if (feed.last_fetch_status === 'refreshing') return styles.statusRefreshing;
  return styles.statusActive;
}

function feedStatusLabel(feed: ThreatIntelFeed): string {
  if (!feed.enabled) return 'Paused';
  if (feed.last_fetch_status === 'error') return 'Error';
  if (feed.last_fetch_status === 'refreshing') return 'Refreshing';
  return 'Active';
}

interface FeedFormData {
  name: string;
  url: string;
  feed_type: string;
  refresh_interval_minutes: number;
  enabled: boolean;
}

const EMPTY_FORM: FeedFormData = {
  name: '',
  url: '',
  feed_type: 'domain',
  refresh_interval_minutes: 1440,
  enabled: true,
};

export function FeedsTab() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { feedId: feedIdParam } = useParams<{ feedId?: string }>();
  const [showModal, setShowModal] = useState(false);
  const [editingFeed, setEditingFeed] = useState<ThreatIntelFeed | null>(null);
  const [formData, setFormData] = useState<FeedFormData>(EMPTY_FORM);

  const {
    data: feedsData,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['threat-intel', 'feeds'],
    queryFn: listFeeds,
  });

  const createMutation = useMutation({
    mutationFn: (body: FeedCreateRequest) => createFeed(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['threat-intel', 'feeds'] });
      closeModal();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: FeedUpdateRequest }) => updateFeed(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['threat-intel', 'feeds'] });
      closeModal();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteFeed(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['threat-intel', 'feeds'] });
    },
  });

  const refreshMutation = useMutation({
    mutationFn: (id: number) => refreshFeed(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['threat-intel', 'feeds'] });
    },
  });

  const closeModal = useCallback(() => {
    setShowModal(false);
    setEditingFeed(null);
    setFormData(EMPTY_FORM);
  }, []);

  const openCreate = useCallback(() => {
    setEditingFeed(null);
    setFormData(EMPTY_FORM);
    setShowModal(true);
  }, []);

  const openEdit = useCallback((feed: ThreatIntelFeed) => {
    setEditingFeed(feed);
    setFormData({
      name: feed.name,
      url: feed.url,
      feed_type: feed.feed_type,
      refresh_interval_minutes: feed.refresh_interval_minutes,
      enabled: feed.enabled,
    });
    setShowModal(true);
  }, []);

  const handleSubmit = useCallback(() => {
    if (editingFeed) {
      updateMutation.mutate({ id: editingFeed.id, body: formData });
    } else {
      createMutation.mutate(formData);
    }
  }, [editingFeed, formData, updateMutation, createMutation]);

  const handleDelete = useCallback(
    (feed: ThreatIntelFeed) => {
      if (window.confirm(`Delete feed "${feed.name}" and all its indicators?`)) {
        deleteMutation.mutate(feed.id);
      }
    },
    [deleteMutation],
  );

  const feeds = feedsData?.items ?? [];

  const selectedFeedId = feedIdParam ? parseInt(feedIdParam, 10) : null;
  const selectedFeed =
    selectedFeedId !== null ? (feeds.find((f) => f.id === selectedFeedId) ?? null) : null;

  const openFeedDetail = useCallback(
    (feed: ThreatIntelFeed) => {
      navigate(`/threat-intel/feeds/${feed.id}`, { replace: true });
    },
    [navigate],
  );

  const closeFeedDetail = useCallback(() => {
    navigate('/threat-intel/feeds', { replace: true });
  }, [navigate]);

  if (isLoading) {
    return (
      <div className={styles.centered}>
        <Spinner />
      </div>
    );
  }

  if (isError) {
    return <ErrorBanner message="Failed to load feeds" onRetry={refetch} />;
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <button className={styles.btnPrimary} onClick={openCreate}>
          + Add Feed
        </button>
      </div>

      {feeds.length === 0 ? (
        <div className={styles.emptyState}>
          No threat intelligence feeds configured yet. Click &quot;Add Feed&quot; to get started.
        </div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.dataTable}>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Type</th>
                <th scope="col">Source URL</th>
                <th scope="col">Status</th>
                <th scope="col">Indicators</th>
                <th scope="col">Last Refresh</th>
                <th scope="col">Interval</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {feeds.map((feed) => (
                <tr
                  key={feed.id}
                  onClick={() => openFeedDetail(feed)}
                  className={styles.clickableRow}
                  role="button"
                  tabIndex={0}
                  aria-label={`View details for ${feed.name}`}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      openFeedDetail(feed);
                    }
                  }}
                >
                  <td>
                    <strong>{feed.name}</strong>
                  </td>
                  <td>
                    <span className={styles.typeBadge}>{feed.feed_type}</span>
                  </td>
                  <td>
                    <span className={styles.truncate} title={feed.url}>
                      {feed.url}
                    </span>
                  </td>
                  <td>
                    <span className={[styles.statusBadge, feedStatusClass(feed)].join(' ')}>
                      {feedStatusLabel(feed)}
                    </span>
                    {feed.last_fetch_status === 'error' && (
                      <span className={styles.errorTooltip} title="Last fetch failed">
                        ⚠
                      </span>
                    )}
                  </td>
                  <td>{feed.last_indicator_count ?? '—'}</td>
                  <td>{feed.last_fetched_at ? formatAbsolute(feed.last_fetched_at) : '—'}</td>
                  <td>{Math.round(feed.refresh_interval_minutes / 60)}h</td>
                  <td>
                    <div className={styles.actionsCell} onClick={(e) => e.stopPropagation()}>
                      <button
                        className={styles.btnSmall}
                        onClick={() => refreshMutation.mutate(feed.id)}
                        disabled={refreshMutation.isPending}
                        title="Refresh now"
                      >
                        ↻
                      </button>
                      <button className={styles.btnSmall} onClick={() => openEdit(feed)}>
                        Edit
                      </button>
                      <button className={styles.btnDanger} onClick={() => handleDelete(feed)}>
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showModal && (
        <div className={styles.modalOverlay} onClick={closeModal}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <h2 className={styles.modalTitle}>{editingFeed ? 'Edit Feed' : 'Add Feed'}</h2>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Feed Name</label>
              <input
                className={styles.formInput}
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g. AlienVault OTX"
              />
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Source URL</label>
              <input
                className={styles.formInput}
                value={formData.url}
                onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                placeholder="https://example.com/feed.txt"
              />
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Type</label>
              <select
                className={styles.formSelect}
                value={formData.feed_type}
                onChange={(e) => setFormData({ ...formData, feed_type: e.target.value })}
              >
                <option value="domain">Domain</option>
                <option value="ip">IP Address</option>
              </select>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Refresh Interval (minutes)</label>
              <input
                className={styles.formInput}
                type="number"
                min={15}
                max={43200}
                value={formData.refresh_interval_minutes}
                onChange={(e) =>
                  setFormData({ ...formData, refresh_interval_minutes: Number(e.target.value) })
                }
              />
            </div>

            {editingFeed && (
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>Enabled</label>
                <input
                  type="checkbox"
                  className={styles.toggle}
                  checked={formData.enabled}
                  onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                />
              </div>
            )}

            <div className={styles.modalActions}>
              <button className={styles.btnSmall} onClick={closeModal}>
                Cancel
              </button>
              <button
                className={styles.btnPrimary}
                onClick={handleSubmit}
                disabled={
                  !formData.name ||
                  !formData.url ||
                  createMutation.isPending ||
                  updateMutation.isPending
                }
              >
                {editingFeed ? 'Save Changes' : 'Create Feed'}
              </button>
            </div>
          </div>
        </div>
      )}

      <Drawer open={!!selectedFeed} onClose={closeFeedDetail} title="Feed Details">
        {selectedFeed && (
          <div className={styles.drawerContent}>
            <dl className={styles.detailList}>
              <dt>Name</dt>
              <dd>{selectedFeed.name}</dd>

              <dt>Source URL</dt>
              <dd>
                <a
                  href={selectedFeed.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.matchLink}
                >
                  {selectedFeed.url}
                </a>
              </dd>

              <dt>Feed Type</dt>
              <dd>
                <span className={styles.typeBadge}>{selectedFeed.feed_type}</span>
              </dd>

              <dt>Status</dt>
              <dd>
                <span className={[styles.statusBadge, feedStatusClass(selectedFeed)].join(' ')}>
                  {feedStatusLabel(selectedFeed)}
                </span>
              </dd>

              <dt>Enabled</dt>
              <dd>{selectedFeed.enabled ? 'Yes' : 'No'}</dd>

              <dt>Refresh Interval</dt>
              <dd>
                {selectedFeed.refresh_interval_minutes} minutes (
                {Math.round(selectedFeed.refresh_interval_minutes / 60)}h)
              </dd>

              <dt>Indicator Count</dt>
              <dd>{selectedFeed.last_indicator_count ?? '—'}</dd>

              <dt>Last Fetch Status</dt>
              <dd>{selectedFeed.last_fetch_status ?? '—'}</dd>

              <dt>Last Fetched</dt>
              <dd>
                {selectedFeed.last_fetched_at
                  ? formatAbsolute(selectedFeed.last_fetched_at)
                  : 'Never'}
              </dd>

              <dt>Created By</dt>
              <dd>{selectedFeed.created_by}</dd>

              <dt>Created At</dt>
              <dd>{formatAbsolute(selectedFeed.created_at)}</dd>

              <dt>Updated At</dt>
              <dd>{formatAbsolute(selectedFeed.updated_at)}</dd>
            </dl>

            <div className={styles.drawerActions}>
              <button
                className={styles.btnSmall}
                onClick={() => {
                  refreshMutation.mutate(selectedFeed.id);
                }}
                disabled={refreshMutation.isPending}
              >
                ↻ Refresh Now
              </button>
              <button
                className={styles.btnSmall}
                onClick={() => {
                  closeFeedDetail();
                  openEdit(selectedFeed);
                }}
              >
                Edit
              </button>
              <button
                className={styles.btnDanger}
                onClick={() => {
                  handleDelete(selectedFeed);
                  closeFeedDetail();
                }}
              >
                Delete
              </button>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
