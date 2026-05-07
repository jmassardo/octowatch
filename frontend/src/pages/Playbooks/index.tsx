import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listPlaybookTemplates,
  listPlaybookExecutions,
  createPlaybookTemplate,
  updatePlaybookTemplate,
  deletePlaybookTemplate,
} from '../../api/playbooks';
import type {
  PlaybookTemplate,
  PlaybookExecution,
  CreateTemplatePayload,
  UpdateTemplatePayload,
} from '../../api/playbooks';
import { PageHeader } from '../../components/common/PageHeader';
import { Card } from '../../components/primitives/Card';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { Label } from '../../components/primitives/Label';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { EmptyState } from '../../components/common/EmptyState';
import { formatRelativeShort } from '../../utils/dates';
import { PlaybookRunner } from './PlaybookRunner';
import { PlaybookEditor } from './PlaybookEditor';
import styles from './Playbooks.module.css';

type Tab = 'templates' | 'active' | 'history';

/**
 * PlaybooksPage — Main page for the remediation playbook system.
 *
 * Three tabs:
 * - Template Library: grid of available playbook templates
 * - Active Executions: DataTable of in-progress executions
 * - History: completed executions
 */
export function PlaybooksPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>('templates');
  const [runningExecId, setRunningExecId] = useState<number | null>(null);
  const [editingTemplate, setEditingTemplate] = useState<PlaybookTemplate | null>(null);
  const [creatingNew, setCreatingNew] = useState(false);

  // ── Queries ─────────────────────────────────────────────────────
  const {
    data: templates,
    isLoading: templatesLoading,
    error: templatesError,
  } = useQuery({
    queryKey: ['playbook-templates'],
    queryFn: () => listPlaybookTemplates(),
  });

  const {
    data: executionsData,
    isLoading: executionsLoading,
    error: executionsError,
  } = useQuery({
    queryKey: ['playbook-executions'],
    queryFn: () => listPlaybookExecutions(),
    refetchInterval: 10_000,
  });

  const allExecutions = useMemo(() => executionsData?.items ?? [], [executionsData]);

  const activeExecutions = useMemo(
    () => allExecutions.filter((e) => e.status === 'in_progress' || e.status === 'pending'),
    [allExecutions],
  );

  const completedExecutions = useMemo(
    () =>
      allExecutions.filter(
        (e) => e.status === 'completed' || e.status === 'cancelled' || e.status === 'failed',
      ),
    [allExecutions],
  );

  // ── Mutations ───────────────────────────────────────────────────
  const createMutation = useMutation({
    mutationFn: (data: CreateTemplatePayload) => createPlaybookTemplate(data),
    onSuccess: () => {
      setCreatingNew(false);
      void queryClient.invalidateQueries({ queryKey: ['playbook-templates'] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateTemplatePayload }) =>
      updatePlaybookTemplate(id, data),
    onSuccess: () => {
      setEditingTemplate(null);
      void queryClient.invalidateQueries({ queryKey: ['playbook-templates'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deletePlaybookTemplate(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['playbook-templates'] });
    },
  });

  // ── Playbook Runner view ────────────────────────────────────────
  if (runningExecId !== null) {
    return <PlaybookRunner executionId={runningExecId} onBack={() => setRunningExecId(null)} />;
  }

  // ── Editor view ─────────────────────────────────────────────────
  if (creatingNew) {
    return (
      <PlaybookEditor
        onSave={(data) => createMutation.mutate(data as CreateTemplatePayload)}
        onCancel={() => setCreatingNew(false)}
        saving={createMutation.isPending}
      />
    );
  }

  if (editingTemplate) {
    return (
      <PlaybookEditor
        template={editingTemplate}
        onSave={(data) =>
          updateMutation.mutate({ id: editingTemplate.id, data: data as UpdateTemplatePayload })
        }
        onCancel={() => setEditingTemplate(null)}
        saving={updateMutation.isPending}
      />
    );
  }

  // ── Template name lookup for executions ─────────────────────────
  const templateMap = new Map((templates ?? []).map((t) => [t.id, t]));

  function getTemplateName(templateId: number): string {
    return templateMap.get(templateId)?.name ?? `Template #${templateId}`;
  }

  function getStepProgress(exec: PlaybookExecution): string {
    const completed = exec.step_results.filter((s) => s.completed).length;
    return `${completed} / ${exec.step_results.length}`;
  }

  // ── Column definitions ──────────────────────────────────────────
  const activeColumns: ColumnDef<PlaybookExecution>[] = [
    {
      key: 'playbook',
      header: 'Playbook',
      render: (row) => getTemplateName(row.template_id),
      sortValue: (row) => getTemplateName(row.template_id),
      sortable: true,
    },
    {
      key: 'detection',
      header: 'Detection',
      render: (row) => `#${row.detection_id}`,
    },
    {
      key: 'progress',
      header: 'Progress',
      render: (row) => getStepProgress(row),
    },
    {
      key: 'assignee',
      header: 'Started By',
      render: (row) => row.started_by,
    },
    {
      key: 'started',
      header: 'Started',
      render: (row) => formatRelativeShort(row.started_at),
      sortValue: (row) => row.started_at,
      sortable: true,
    },
    {
      key: 'actions',
      header: '',
      render: (row) => (
        <Button size="sm" variant="primary" onClick={() => setRunningExecId(row.id)}>
          Continue
        </Button>
      ),
    },
  ];

  const historyColumns: ColumnDef<PlaybookExecution>[] = [
    {
      key: 'playbook',
      header: 'Playbook',
      render: (row) => getTemplateName(row.template_id),
      sortable: true,
      sortValue: (row) => getTemplateName(row.template_id),
    },
    {
      key: 'detection',
      header: 'Detection',
      render: (row) => `#${row.detection_id}`,
    },
    {
      key: 'status',
      header: 'Outcome',
      render: (row) => (
        <Label
          variant={
            row.status === 'completed' ? 'success' : row.status === 'failed' ? 'danger' : 'muted'
          }
        >
          {row.status}
        </Label>
      ),
    },
    {
      key: 'startedBy',
      header: 'Executed By',
      render: (row) => row.started_by,
    },
    {
      key: 'started',
      header: 'Started',
      render: (row) => formatRelativeShort(row.started_at),
      sortValue: (row) => row.started_at,
      sortable: true,
    },
    {
      key: 'completed',
      header: 'Completed',
      render: (row) => (row.completed_at ? formatRelativeShort(row.completed_at) : '—'),
      sortValue: (row) => row.completed_at ?? '',
      sortable: true,
    },
    {
      key: 'actions',
      header: '',
      render: (row) => (
        <Button size="sm" onClick={() => setRunningExecId(row.id)}>
          View
        </Button>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <PageHeader
        title="Playbooks"
        description="Guided remediation workflows for incident response"
        actions={[
          {
            label: '+ New Template',
            onClick: () => setCreatingNew(true),
            variant: 'primary',
          },
        ]}
      />

      {/* Tabs */}
      <div className={styles.tabs} role="tablist">
        {(
          [
            ['templates', 'Template Library'],
            ['active', `Active (${activeExecutions.length})`],
            ['history', `History (${completedExecutions.length})`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            className={`${styles.tab} ${tab === key ? styles.tabActive : ''}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Template Library tab */}
      {tab === 'templates' && (
        <>
          {templatesLoading && <Spinner />}
          {templatesError && <ErrorBanner message="Failed to load templates." />}
          {templates && templates.length === 0 && (
            <EmptyState
              title="No playbook templates"
              description="Create a new playbook template to get started."
            />
          )}
          {templates && templates.length > 0 && (
            <div className={styles.templateGrid}>
              {templates.map((t) => (
                <Card key={t.id} className={styles.templateCard}>
                  <h3 className={styles.templateName}>{t.name}</h3>
                  <p className={styles.templateDesc}>{t.description ?? 'No description'}</p>
                  <div className={styles.templateMeta}>
                    <span>{t.steps.length} steps</span>
                    <span>
                      {t.detection_categories.length > 0
                        ? t.detection_categories.join(', ')
                        : 'All categories'}
                    </span>
                  </div>
                  <div className={styles.templateActions}>
                    <Button size="sm" onClick={() => setEditingTemplate(t)}>
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => {
                        if (window.confirm(`Delete template "${t.name}"? This cannot be undone.`)) {
                          deleteMutation.mutate(t.id);
                        }
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}

      {/* Active Executions tab */}
      {tab === 'active' && (
        <>
          {executionsLoading && <Spinner />}
          {executionsError && <ErrorBanner message="Failed to load executions." />}
          {!executionsLoading && activeExecutions.length === 0 && (
            <EmptyState
              title="No active executions"
              description="Start a playbook from a detection to begin."
            />
          )}
          {activeExecutions.length > 0 && (
            <DataTable
              columns={activeColumns}
              data={activeExecutions}
              rowKey={(r) => r.id}
              onRowClick={(r) => setRunningExecId(r.id)}
            />
          )}
        </>
      )}

      {/* History tab */}
      {tab === 'history' && (
        <>
          {executionsLoading && <Spinner />}
          {executionsError && <ErrorBanner message="Failed to load history." />}
          {!executionsLoading && completedExecutions.length === 0 && (
            <EmptyState
              title="No completed executions"
              description="Completed playbook runs will appear here."
            />
          )}
          {completedExecutions.length > 0 && (
            <DataTable
              columns={historyColumns}
              data={completedExecutions}
              rowKey={(r) => r.id}
              onRowClick={(r) => setRunningExecId(r.id)}
            />
          )}
        </>
      )}
    </div>
  );
}
