import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PageHeader } from '../../components/common/PageHeader';
import { Button } from '../../components/primitives/Button';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { useOrg } from '../../hooks/useOrg';
import {
  fetchTargets,
  fetchDeliveries,
  createTarget,
  updateTarget,
  deleteTarget,
  testTarget,
  retryDelivery,
  type AutomationTarget,
  type AutomationDelivery,
  type CreateTargetRequest,
  type UpdateTargetRequest,
} from '../../api/automation';
import styles from './Automation.module.css';

type TabId = 'targets' | 'deliveries';

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function TargetTypeBadge({ type }: { type: 'webhook' | 'dispatch' }) {
  const cls = type === 'webhook' ? styles.badgeWebhook : styles.badgeDispatch;
  return <span className={`${styles.badge} ${cls}`}>{type}</span>;
}

function EnabledBadge({ enabled }: { enabled: boolean }) {
  const cls = enabled ? styles.badgeEnabled : styles.badgeDisabled;
  return <span className={`${styles.badge} ${cls}`}>{enabled ? 'Enabled' : 'Disabled'}</span>;
}

function DeliveryStatusBadge({ status }: { status: AutomationDelivery['status'] }) {
  const classMap: Record<AutomationDelivery['status'], string> = {
    delivered: styles.badgeDelivered,
    failed: styles.badgeFailed,
    pending: styles.badgePending,
    retrying: styles.badgeRetrying,
  };
  return <span className={`${styles.badge} ${classMap[status]}`}>{status}</span>;
}

interface TargetFormProps {
  initial?: AutomationTarget;
  onSubmit: (data: CreateTargetRequest | UpdateTargetRequest) => void;
  onCancel: () => void;
  isSubmitting: boolean;
}

function TargetForm({ initial, onSubmit, onCancel, isSubmitting }: TargetFormProps) {
  const [name, setName] = useState(initial?.name ?? '');
  const [targetType, setTargetType] = useState<'webhook' | 'dispatch'>(
    initial?.target_type ?? 'webhook',
  );
  const [webhookUrl, setWebhookUrl] = useState(initial?.webhook_url ?? '');
  const [dispatchRepo, setDispatchRepo] = useState(initial?.dispatch_repo ?? '');
  const [dispatchEventType, setDispatchEventType] = useState(initial?.dispatch_event_type ?? '');
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const data: CreateTargetRequest = {
      name,
      target_type: targetType,
      webhook_url: targetType === 'webhook' ? webhookUrl : undefined,
      dispatch_repo: targetType === 'dispatch' ? dispatchRepo : undefined,
      dispatch_event_type: targetType === 'dispatch' ? dispatchEventType : undefined,
      enabled,
    };
    onSubmit(data);
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <div className={styles.formRow}>
        <label className={styles.formLabel} htmlFor="target-name">
          Name
        </label>
        <input
          id="target-name"
          className={styles.formInput}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="My automation target"
          required
        />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel} htmlFor="target-type">
          Type
        </label>
        <select
          id="target-type"
          className={styles.filterSelect}
          value={targetType}
          onChange={(e) => setTargetType(e.target.value as 'webhook' | 'dispatch')}
        >
          <option value="webhook">Webhook</option>
          <option value="dispatch">Repository Dispatch</option>
        </select>
      </div>
      {targetType === 'webhook' && (
        <div className={styles.formRow}>
          <label className={styles.formLabel} htmlFor="webhook-url">
            Webhook URL
          </label>
          <input
            id="webhook-url"
            className={styles.formInput}
            value={webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
            placeholder="https://example.com/webhook"
            required
          />
        </div>
      )}
      {targetType === 'dispatch' && (
        <>
          <div className={styles.formRow}>
            <label className={styles.formLabel} htmlFor="dispatch-repo">
              Repository
            </label>
            <input
              id="dispatch-repo"
              className={styles.formInput}
              value={dispatchRepo}
              onChange={(e) => setDispatchRepo(e.target.value)}
              placeholder="owner/repo"
              required
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel} htmlFor="dispatch-event">
              Event Type
            </label>
            <input
              id="dispatch-event"
              className={styles.formInput}
              value={dispatchEventType}
              onChange={(e) => setDispatchEventType(e.target.value)}
              placeholder="octowatch-detection"
              required
            />
          </div>
        </>
      )}
      <div className={styles.formRow}>
        <label className={styles.formLabel}>
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />{' '}
          Enabled
        </label>
      </div>
      <div className={styles.formActions}>
        <Button type="submit" variant="primary" disabled={isSubmitting}>
          {initial ? 'Update' : 'Create'} Target
        </Button>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function TargetsTab() {
  const { selectedOrg } = useOrg();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editingTarget, setEditingTarget] = useState<AutomationTarget | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['automation-targets', selectedOrg],
    queryFn: fetchTargets,
  });

  const createMutation = useMutation({
    mutationFn: (req: CreateTargetRequest) => createTarget(req),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['automation-targets'] });
      setShowForm(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, req }: { id: number; req: UpdateTargetRequest }) => updateTarget(id, req),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['automation-targets'] });
      setEditingTarget(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteTarget,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['automation-targets'] });
    },
  });

  const testMutation = useMutation({
    mutationFn: (id: number) => testTarget(id),
  });

  const targets = data?.targets ?? [];

  if (isLoading) {
    return <div className={styles.empty}>Loading targets…</div>;
  }

  return (
    <div>
      {!showForm && !editingTarget && (
        <div style={{ marginBottom: 16 }}>
          <Button variant="primary" onClick={() => setShowForm(true)}>
            Add Target
          </Button>
        </div>
      )}

      {showForm && (
        <TargetForm
          onSubmit={(data) => createMutation.mutate(data as CreateTargetRequest)}
          onCancel={() => setShowForm(false)}
          isSubmitting={createMutation.isPending}
        />
      )}

      {editingTarget && (
        <TargetForm
          initial={editingTarget}
          onSubmit={(data) =>
            updateMutation.mutate({ id: editingTarget.id, req: data as UpdateTargetRequest })
          }
          onCancel={() => setEditingTarget(null)}
          isSubmitting={updateMutation.isPending}
        />
      )}

      {targets.length === 0 ? (
        <div className={styles.empty}>
          No automation targets configured. Click &quot;Add Target&quot; to create one.
        </div>
      ) : (
        <div className={styles.targetList}>
          {targets.map((target) => (
            <div key={target.id} className={styles.targetCard}>
              <div className={styles.targetInfo}>
                <p className={styles.targetName}>{target.name}</p>
                <div className={styles.targetMeta}>
                  <TargetTypeBadge type={target.target_type} />
                  <EnabledBadge enabled={target.enabled} />
                  {target.is_catch_all && (
                    <span className={`${styles.badge} ${styles.badgeWebhook}`}>catch-all</span>
                  )}
                  <span>Created {formatDate(target.created_at)}</span>
                </div>
              </div>
              <div className={styles.targetActions}>
                <Button
                  onClick={() => testMutation.mutate(target.id)}
                  disabled={testMutation.isPending}
                >
                  Test
                </Button>
                <Button onClick={() => setEditingTarget(target)}>Edit</Button>
                <Button
                  variant="danger"
                  onClick={() => {
                    if (window.confirm(`Delete target "${target.name}"?`)) {
                      deleteMutation.mutate(target.id);
                    }
                  }}
                >
                  Delete
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DeliveriesTab() {
  const { selectedOrg } = useOrg();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [targetFilter, setTargetFilter] = useState<string>('');

  const { data, isLoading } = useQuery({
    queryKey: ['automation-deliveries', selectedOrg, statusFilter, targetFilter],
    queryFn: () =>
      fetchDeliveries({
        status: statusFilter || undefined,
        target_id: targetFilter ? Number(targetFilter) : undefined,
        limit: 100,
      }),
  });

  const { data: targetsData } = useQuery({
    queryKey: ['automation-targets', selectedOrg],
    queryFn: fetchTargets,
  });

  const retryMutation = useMutation({
    mutationFn: retryDelivery,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['automation-deliveries'] });
    },
  });

  const deliveries = data?.deliveries ?? [];
  const targets = targetsData?.targets ?? [];

  const columns: ColumnDef<AutomationDelivery>[] = [
    {
      key: 'target_name',
      header: 'Target',
      render: (row) => row.target_name,
      sortable: true,
      sortValue: (row) => row.target_name,
    },
    {
      key: 'detection_id',
      header: 'Detection',
      render: (row) => `#${row.detection_id}`,
      sortable: true,
      sortValue: (row) => row.detection_id,
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <DeliveryStatusBadge status={row.status} />,
      sortable: true,
      sortValue: (row) => row.status,
    },
    {
      key: 'attempts',
      header: 'Attempts',
      render: (row) => String(row.attempts),
      sortable: true,
      sortValue: (row) => row.attempts,
    },
    {
      key: 'response_code',
      header: 'Response',
      render: (row) => (row.response_code !== null ? String(row.response_code) : '—'),
    },
    {
      key: 'created_at',
      header: 'Created',
      render: (row) => formatDate(row.created_at),
      sortable: true,
      sortValue: (row) => row.created_at,
    },
    {
      key: 'actions',
      header: '',
      render: (row) =>
        row.status === 'failed' ? (
          <Button onClick={() => retryMutation.mutate(row.id)} disabled={retryMutation.isPending}>
            Retry
          </Button>
        ) : null,
    },
  ];

  if (isLoading) {
    return <div className={styles.empty}>Loading deliveries…</div>;
  }

  return (
    <div>
      <div className={styles.filters}>
        <select
          className={styles.filterSelect}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          <option value="delivered">Delivered</option>
          <option value="failed">Failed</option>
          <option value="pending">Pending</option>
          <option value="retrying">Retrying</option>
        </select>
        <select
          className={styles.filterSelect}
          value={targetFilter}
          onChange={(e) => setTargetFilter(e.target.value)}
          aria-label="Filter by target"
        >
          <option value="">All targets</option>
          {targets.map((t) => (
            <option key={t.id} value={String(t.id)}>
              {t.name}
            </option>
          ))}
        </select>
      </div>

      <DataTable
        columns={columns}
        data={deliveries}
        rowKey={(row) => row.id}
        emptyMessage="No deliveries found."
      />
    </div>
  );
}

export function AutomationPage() {
  const [activeTab, setActiveTab] = useState<TabId>('targets');

  return (
    <div className={styles.page}>
      <PageHeader title="Automation" description="Configure automated responses to detections." />

      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === 'targets' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('targets')}
          type="button"
        >
          Targets
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'deliveries' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('deliveries')}
          type="button"
        >
          Deliveries
        </button>
      </div>

      {activeTab === 'targets' && <TargetsTab />}
      {activeTab === 'deliveries' && <DeliveriesTab />}
    </div>
  );
}
