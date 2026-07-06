import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTabParam } from '../../hooks/useTabParam';
import { PageHeader } from '../../components/common/PageHeader';
import { Button } from '../../components/primitives/Button';
import {
  listNotifications,
  markNotificationRead,
  markAllNotificationsRead,
} from '../../api/notifications';
import type {
  NotificationSeverity,
  NotificationSource,
  NotificationItem,
} from '../../types/notifications';
import { NotificationPreferences } from './NotificationPreferences';
import styles from './Notifications.module.css';

function formatRelativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return 'just now';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDays = Math.floor(diffHr / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

function severityClass(severity: NotificationSeverity): string {
  switch (severity) {
    case 'critical':
      return styles.badgeCritical;
    case 'warning':
      return styles.badgeWarning;
    default:
      return styles.badgeInfo;
  }
}

type TabId = 'alerts' | 'preferences';

const TAB_KEYS: readonly TabId[] = ['alerts', 'preferences'];

export function NotificationsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useTabParam('/notifications', TAB_KEYS, 'alerts');
  const [page, setPage] = useState(1);
  const [severityFilter, setSeverityFilter] = useState<NotificationSeverity | ''>('');
  const [readFilter, setReadFilter] = useState<string>('');
  const [sourceFilter, setSourceFilter] = useState<NotificationSource | ''>('');

  const pageSize = 20;

  const { data, isLoading, isError } = useQuery({
    queryKey: ['notifications', page, severityFilter, readFilter, sourceFilter],
    queryFn: () =>
      listNotifications({
        page,
        page_size: pageSize,
        severity: severityFilter || undefined,
        read: readFilter === '' ? undefined : readFilter === 'true',
        source: sourceFilter || undefined,
      }),
  });

  const markReadMutation = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });

  const markAllMutation = useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });

  function handleNotificationClick(item: NotificationItem) {
    if (!item.read) {
      markReadMutation.mutate(item.id);
    }
    if (item.link) {
      navigate(item.link);
    }
  }

  if (activeTab === 'preferences') {
    return (
      <div className={styles.page}>
        <PageHeader
          title="Notifications"
          description="Manage your notification settings and preferences"
        />
        <div className={styles.tabs}>
          <button className={`${styles.tab}`} onClick={() => setActiveTab('alerts')}>
            Notifications
          </button>
          <button
            className={`${styles.tab} ${styles.tabActive}`}
            onClick={() => setActiveTab('preferences')}
          >
            Preferences
          </button>
        </div>
        <NotificationPreferences />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <PageHeader title="Notifications" description="View and manage your notification alerts" />

      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${styles.tabActive}`}
          onClick={() => setActiveTab('alerts')}
        >
          Notifications
          {data && data.unread_count > 0 && ` (${data.unread_count})`}
        </button>
        <button className={`${styles.tab}`} onClick={() => setActiveTab('preferences')}>
          Preferences
        </button>
      </div>

      <div className={styles.filters}>
        <select
          className={styles.filterSelect}
          value={severityFilter}
          onChange={(e) => {
            setSeverityFilter(e.target.value as NotificationSeverity | '');
            setPage(1);
          }}
          aria-label="Filter by severity"
        >
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>

        <select
          className={styles.filterSelect}
          value={readFilter}
          onChange={(e) => {
            setReadFilter(e.target.value);
            setPage(1);
          }}
          aria-label="Filter by read status"
        >
          <option value="">All</option>
          <option value="false">Unread</option>
          <option value="true">Read</option>
        </select>

        <select
          className={styles.filterSelect}
          value={sourceFilter}
          onChange={(e) => {
            setSourceFilter(e.target.value as NotificationSource | '');
            setPage(1);
          }}
          aria-label="Filter by source"
        >
          <option value="">All sources</option>
          <option value="detection">Detection</option>
          <option value="sync">Sync</option>
          <option value="system">System</option>
        </select>

        <div className={styles.markAllBtn}>
          <Button
            size="sm"
            variant="default"
            onClick={() => markAllMutation.mutate()}
            disabled={!data || data.unread_count === 0}
          >
            Mark all read
          </Button>
        </div>
      </div>

      {isLoading && <div className={styles.loading}>Loading notifications…</div>}

      {isError && <div className={styles.error}>Failed to load notifications</div>}

      {data && data.items.length === 0 && (
        <div className={styles.empty}>
          <div className={styles.emptyIcon}>🔔</div>
          <div className={styles.emptyTitle}>No notifications</div>
          <div className={styles.emptyText}>
            You&apos;re all caught up! New notifications will appear here.
          </div>
        </div>
      )}

      {data && data.items.length > 0 && (
        <>
          <div className={styles.list} role="list" aria-label="Notifications">
            {data.items.map((item) => (
              <div
                key={item.id}
                className={`${styles.item}${!item.read ? ` ${styles.itemUnread}` : ''}`}
                role="listitem"
                onClick={() => handleNotificationClick(item)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleNotificationClick(item);
                  }
                }}
                tabIndex={0}
              >
                {!item.read ? (
                  <div className={styles.unreadDot} aria-label="Unread" />
                ) : (
                  <div className={styles.readDotPlaceholder} />
                )}
                <div className={styles.itemContent}>
                  <div className={styles.itemHeader}>
                    <span className={styles.itemTitle}>{item.title}</span>
                    <div className={styles.itemMeta}>
                      <span className={`${styles.badge} ${severityClass(item.severity)}`}>
                        {item.severity}
                      </span>
                      <span className={styles.sourceBadge}>{item.source}</span>
                      <span className={styles.itemTime}>{formatRelativeTime(item.created_at)}</span>
                    </div>
                  </div>
                  <div className={styles.itemMessage}>{item.message}</div>
                </div>
              </div>
            ))}
          </div>

          <div className={styles.pagination}>
            <span>
              Showing {(data.page - 1) * data.page_size + 1}–
              {Math.min(data.page * data.page_size, data.total)} of {data.total}
            </span>
            <div className={styles.paginationButtons}>
              <Button
                size="sm"
                variant="default"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
              >
                Previous
              </Button>
              <Button
                size="sm"
                variant="default"
                onClick={() => setPage((p) => p + 1)}
                disabled={!data.has_next}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
