import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listChains, getChainMetrics, getChain, updateChain } from '../../api/correlations';
import type {
  CorrelationChainSummary,
  CorrelationChain,
  ChainMember,
} from '../../api/correlations';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { MetricCard } from '../../components/primitives/MetricCard';
import { SeverityDot } from '../../components/primitives/SeverityDot';
import { Label } from '../../components/primitives/Label';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Drawer } from '../../components/primitives/Drawer';
import { formatRelativeShort, formatCompact } from '../../utils/dates';
import styles from './Threats.module.css';

type Severity = 'critical' | 'high' | 'medium' | 'low';

function isSeverity(v: string): v is Severity {
  return ['critical', 'high', 'medium', 'low'].includes(v);
}

const STATUS_LABELS: Record<string, string> = {
  open: 'Open',
  investigating: 'Investigating',
  resolved: 'Resolved',
};

/* ── Chain detail drawer ──────────────────────────────────────────────── */

function ChainDetailDrawer({
  chain,
  onClose,
  onStatusChange,
}: {
  chain: CorrelationChain;
  onClose: () => void;
  onStatusChange: (status: string) => void;
}) {
  return (
    <Drawer open onClose={onClose} title={chain.title}>
      <div className={styles.chainDrawer}>
        <div className={styles.chainMeta}>
          <div className={styles.chainMetaRow}>
            <span className={styles.chainMetaLabel}>Status</span>
            <Label variant={chain.status === 'resolved' ? 'muted' : 'attention'}>
              {STATUS_LABELS[chain.status] ?? chain.status}
            </Label>
          </div>
          <div className={styles.chainMetaRow}>
            <span className={styles.chainMetaLabel}>Severity</span>
            <span>
              {isSeverity(chain.severity) && <SeverityDot severity={chain.severity} />}
              {chain.severity}
            </span>
          </div>
          <div className={styles.chainMetaRow}>
            <span className={styles.chainMetaLabel}>Assignee</span>
            <span>{chain.assignee ?? '—'}</span>
          </div>
          <div className={styles.chainMetaRow}>
            <span className={styles.chainMetaLabel}>Detections</span>
            <span>{chain.detection_count}</span>
          </div>
          <div className={styles.chainMetaRow}>
            <span className={styles.chainMetaLabel}>Created</span>
            <span>{formatCompact(chain.created_at)}</span>
          </div>
          {chain.notes && (
            <div className={styles.chainMetaRow}>
              <span className={styles.chainMetaLabel}>Notes</span>
              <span>{chain.notes}</span>
            </div>
          )}
        </div>

        <div className={styles.chainActions}>
          {chain.status !== 'investigating' && (
            <Button size="sm" variant="primary" onClick={() => onStatusChange('investigating')}>
              Investigate
            </Button>
          )}
          {chain.status !== 'resolved' && (
            <Button size="sm" variant="default" onClick={() => onStatusChange('resolved')}>
              Resolve
            </Button>
          )}
          {chain.status === 'resolved' && (
            <Button size="sm" variant="default" onClick={() => onStatusChange('open')}>
              Reopen
            </Button>
          )}
        </div>

        <div className={styles.chainTimeline}>
          <h4 className={styles.chainTimelineTitle}>Correlated Detections</h4>
          {chain.members.map((member: ChainMember) => (
            <div key={member.detection_id} className={styles.chainTimelineItem}>
              <div className={styles.chainTimelineDot} />
              <div className={styles.chainTimelineContent}>
                <div className={styles.chainTimelineHeader}>
                  {isSeverity(member.detection_severity) && (
                    <SeverityDot severity={member.detection_severity} />
                  )}
                  <span className={styles.chainTimelineDetTitle}>{member.detection_title}</span>
                </div>
                <div className={styles.chainTimelineMeta}>
                  <span>{formatCompact(member.detection_triggered_at)}</span>
                  {member.detection_actor && <span>· @{member.detection_actor}</span>}
                  <Label variant="muted">{member.correlation_type}</Label>
                  <span className={styles.chainConfidence}>
                    {Math.round(member.confidence * 100)}%
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Drawer>
  );
}

/* ── Main pane ────────────────────────────────────────────────────────── */

interface ChainsPaneProps {
  className?: string;
}

export function ChainsPane({ className }: ChainsPaneProps) {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [selectedChainId, setSelectedChainId] = useState<string | null>(null);

  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ['chain-metrics'],
    queryFn: getChainMetrics,
  });

  const {
    data: chainList,
    isLoading: listLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['chains', statusFilter, page],
    queryFn: () =>
      listChains({
        status: statusFilter || undefined,
        page,
        page_size: 25,
      }),
  });

  const { data: selectedChain } = useQuery({
    queryKey: ['chain-detail', selectedChainId],
    queryFn: () => getChain(selectedChainId!),
    enabled: selectedChainId !== null,
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => updateChain(id, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chains'] });
      queryClient.invalidateQueries({ queryKey: ['chain-metrics'] });
      queryClient.invalidateQueries({ queryKey: ['chain-detail'] });
    },
  });

  const columns: ColumnDef<CorrelationChainSummary>[] = [
    {
      key: 'severity',
      header: 'Severity',
      sortable: true,
      render: (row) => (
        <span>
          {isSeverity(row.severity) && <SeverityDot severity={row.severity} />}
          {row.severity}
        </span>
      ),
      sortValue: (row) => {
        const order: Record<string, number> = {
          critical: 4,
          high: 3,
          medium: 2,
          low: 1,
        };
        return order[row.severity] ?? 0;
      },
      width: '100px',
    },
    {
      key: 'title',
      header: 'Title',
      sortable: true,
      render: (row) => <span className={styles.chainTitle}>{row.title}</span>,
      sortValue: (row) => row.title,
    },
    {
      key: 'detection_count',
      header: 'Detections',
      sortable: true,
      render: (row) => <span>{row.detection_count}</span>,
      sortValue: (row) => row.detection_count,
      width: '100px',
    },
    {
      key: 'status',
      header: 'Status',
      sortable: true,
      render: (row) => (
        <Label
          variant={
            row.status === 'resolved'
              ? 'muted'
              : row.status === 'investigating'
                ? 'attention'
                : 'severe'
          }
        >
          {STATUS_LABELS[row.status] ?? row.status}
        </Label>
      ),
      sortValue: (row) => row.status,
      width: '120px',
    },
    {
      key: 'assignee',
      header: 'Assignee',
      render: (row) => <span>{row.assignee ?? '—'}</span>,
      width: '120px',
    },
    {
      key: 'created_at',
      header: 'Age',
      sortable: true,
      render: (row) => <span>{formatRelativeShort(row.created_at)}</span>,
      sortValue: (row) => row.created_at,
      width: '100px',
    },
  ];

  return (
    <div className={className}>
      {/* Metrics cards */}
      <div className={styles.chainsMetrics}>
        <MetricCard
          value={metricsLoading ? '...' : String(metrics?.active_chains ?? 0)}
          label="Active Chains"
        />
        <MetricCard
          value={metricsLoading ? '...' : String(metrics?.avg_chain_size ?? 0)}
          label="Avg Chain Size"
        />
        <MetricCard
          value={metricsLoading ? '...' : String(metrics?.chains_resolved_today ?? 0)}
          label="Resolved Today"
        />
        <MetricCard
          value={metricsLoading ? '...' : String(metrics?.total_chains ?? 0)}
          label="Total Chains"
        />
      </div>

      {/* Status filter */}
      <div className={styles.chainsFilter}>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          aria-label="Filter by status"
          className={styles.filterSelect}
        >
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="investigating">Investigating</option>
          <option value="resolved">Resolved</option>
        </select>
      </div>

      {/* Content */}
      {listLoading && (
        <div className={styles.center}>
          <Spinner />
        </div>
      )}

      {isError && <ErrorBanner message="Failed to load chains" onRetry={refetch} />}

      {chainList && !listLoading && (
        <>
          <DataTable
            columns={columns}
            data={chainList.items}
            rowKey={(row) => row.chain_id}
            onRowClick={(row) => setSelectedChainId(row.chain_id)}
            emptyMessage="No investigation chains found"
          />

          {chainList.has_next && (
            <div className={styles.chainsPagination}>
              <Button
                size="sm"
                variant="default"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                Previous
              </Button>
              <span className={styles.pageIndicator}>Page {page}</span>
              <Button
                size="sm"
                variant="default"
                onClick={() => setPage((p) => p + 1)}
                disabled={!chainList.has_next}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}

      {/* Detail drawer */}
      {selectedChain && selectedChainId && (
        <ChainDetailDrawer
          chain={selectedChain}
          onClose={() => setSelectedChainId(null)}
          onStatusChange={(newStatus) => {
            updateMutation.mutate({ id: selectedChainId, status: newStatus });
          }}
        />
      )}
    </div>
  );
}
