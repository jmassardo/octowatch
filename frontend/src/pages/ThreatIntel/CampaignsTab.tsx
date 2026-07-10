import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listCampaigns,
  getCampaignDetail,
  updateCampaign,
  promoteCampaignRules,
} from '../../api/threatIntel';
import type { Campaign, CampaignDetail, CampaignListParams } from '../../api/threatIntel';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Drawer } from '../../components/primitives/Drawer';
import { formatAbsolute } from '../../utils/dates';
import styles from './ThreatIntel.module.css';

function severityBadge(severity: string): string {
  switch (severity) {
    case 'critical':
      return styles.severityCritical;
    case 'high':
      return styles.severityHigh;
    case 'medium':
      return styles.severityMedium;
    default:
      return styles.severityLow;
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'active':
      return '🟢 Active';
    case 'monitoring':
      return '🟡 Monitoring';
    case 'archived':
      return '⚪ Archived';
    default:
      return status;
  }
}

export function CampaignsTab() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const params: CampaignListParams = {
    page,
    page_size: pageSize,
    ...(statusFilter ? { status: statusFilter } : {}),
  };

  const { data, isLoading, isError } = useQuery({
    queryKey: ['threat-intel', 'campaigns', params],
    queryFn: () => listCampaigns(params),
  });

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['threat-intel', 'campaigns', selectedId, 'detail'],
    queryFn: () => getCampaignDetail(selectedId!),
    enabled: selectedId !== null,
  });

  const archiveMutation = useMutation({
    mutationFn: (id: number) => updateCampaign(id, { status: 'archived' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['threat-intel', 'campaigns'] });
      setSelectedId(null);
    },
  });

  const promoteMutation = useMutation({
    mutationFn: (id: number) => promoteCampaignRules(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['threat-intel', 'campaigns'] });
    },
  });

  if (isLoading) return <Spinner />;
  if (isError) return <ErrorBanner message="Failed to load campaigns" />;

  const campaigns = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className={styles.tabContent}>
      <div className={styles.toolbar}>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className={styles.filterSelect}
          aria-label="Filter campaigns by status"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="monitoring">Monitoring</option>
          <option value="archived">Archived</option>
        </select>
        <span className={styles.resultCount}>
          {total} campaign{total !== 1 ? 's' : ''}
        </span>
      </div>

      <table className={styles.dataTable} aria-label="Campaigns">
        <thead>
          <tr>
            <th>Name</th>
            <th>Severity</th>
            <th>Status</th>
            <th>Indicators</th>
            <th>Detections</th>
            <th>Last Updated</th>
          </tr>
        </thead>
        <tbody>
          {campaigns.map((c: Campaign) => (
            <tr
              key={c.id}
              className={styles.clickableRow}
              onClick={() => setSelectedId(c.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && setSelectedId(c.id)}
            >
              <td className={styles.campaignName}>{c.name}</td>
              <td>
                <span className={`${styles.badge} ${severityBadge(c.severity)}`}>{c.severity}</span>
              </td>
              <td>{statusLabel(c.status)}</td>
              <td>{c.indicator_count}</td>
              <td>{c.detection_count ?? '—'}</td>
              <td>{formatAbsolute(c.last_updated)}</td>
            </tr>
          ))}
          {campaigns.length === 0 && (
            <tr>
              <td colSpan={6} className={styles.emptyState}>
                No campaigns found
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div className={styles.pagination}>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
            ← Previous
          </button>
          <span>
            Page {page} of {totalPages}
          </span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            Next →
          </button>
        </div>
      )}

      <Drawer
        open={selectedId !== null}
        onClose={() => setSelectedId(null)}
        title={detail?.name ?? 'Campaign Detail'}
      >
        {detailLoading ? (
          <Spinner />
        ) : detail ? (
          <CampaignDetailPanel
            detail={detail}
            onArchive={() => archiveMutation.mutate(detail.id)}
            onPromote={() => promoteMutation.mutate(detail.id)}
            archiving={archiveMutation.isPending}
            promoting={promoteMutation.isPending}
          />
        ) : null}
      </Drawer>
    </div>
  );
}

function CampaignDetailPanel({
  detail,
  onArchive,
  onPromote,
  archiving,
  promoting,
}: {
  detail: CampaignDetail;
  onArchive: () => void;
  onPromote: () => void;
  archiving: boolean;
  promoting: boolean;
}) {
  const mitre = detail.mitre_attack ?? [];

  return (
    <div className={styles.detailPanel}>
      <div className={styles.detailMeta}>
        <span className={`${styles.badge} ${severityBadge(detail.severity)}`}>
          {detail.severity}
        </span>
        <span>{statusLabel(detail.status)}</span>
        {detail.source_feed_name && <span>Feed: {detail.source_feed_name}</span>}
      </div>

      {detail.description && <p className={styles.detailDescription}>{detail.description}</p>}

      {mitre.length > 0 && (
        <section className={styles.detailSection}>
          <h4>MITRE ATT&amp;CK</h4>
          <div className={styles.mitreList}>
            {mitre.map((t) => (
              <span key={t} className={styles.mitreBadge}>
                {t}
              </span>
            ))}
          </div>
        </section>
      )}

      <section className={styles.detailSection}>
        <h4>Indicators by Type</h4>
        <ul className={styles.statList}>
          {detail.indicators_by_type.map((item) => (
            <li key={item.type}>
              <strong>{item.count}</strong> {item.type}
            </li>
          ))}
        </ul>
      </section>

      {detail.rules.length > 0 && (
        <section className={styles.detailSection}>
          <h4>Auto-generated Rules ({detail.rules.length})</h4>
          <ul className={styles.ruleList}>
            {detail.rules.map((r) => (
              <li key={r.id} className={r.enabled ? '' : styles.disabledRule}>
                {r.name}
                {r.source === 'feed' && <span className={styles.feedBadge}>auto</span>}
                {r.expires_at && (
                  <span className={styles.expiryNote}>expires {formatAbsolute(r.expires_at)}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className={styles.detailActions}>
        {detail.status === 'active' && (
          <>
            <button className={styles.btnSecondary} onClick={onArchive} disabled={archiving}>
              {archiving ? 'Archiving...' : 'Archive Campaign'}
            </button>
            {detail.rules.some((r) => r.source === 'feed') && (
              <button className={styles.btnPrimary} onClick={onPromote} disabled={promoting}>
                {promoting ? 'Promoting...' : 'Promote Rules to Permanent'}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
