import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Label } from '../../components/primitives/Label';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { DrilldownModal } from '../../components/primitives/DrilldownModal';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import {
  getWorkflowHealth,
  getBranchProtection,
  getCopilotGovernance,
  getCodespaces,
  getRunnerHealth,
} from '../../api/healthSignals';
import type { WorkflowRow, RunnerRow } from '../../api/healthSignals';
import { formatDateOnly } from '../../utils/dates';
import styles from './OpsHealthPane.module.css';

/* ---------- helpers ---------- */

function failureRateVariant(rate: number): 'danger' | 'attention' | 'success' {
  if (rate > 20) return 'danger';
  if (rate > 10) return 'attention';
  return 'success';
}

/* ---------- sub-components ---------- */

function WorkflowHealthTable({ workflows }: { workflows: WorkflowRow[] }) {
  const columns: ColumnDef<WorkflowRow>[] = [
    {
      key: 'repo',
      header: 'Repository',
      sortable: true,
      filterable: true,
      render: (wf) => wf.repo,
      sortValue: (wf) => wf.repo,
      filterValue: (wf) => wf.repo,
    },
    {
      key: 'workflow',
      header: 'Workflow',
      sortable: true,
      filterable: true,
      render: (wf) => <span className={styles.workflowName}>{wf.workflow_name}</span>,
      sortValue: (wf) => wf.workflow_name,
      filterValue: (wf) => wf.workflow_name,
    },
    {
      key: 'total_runs',
      header: 'Total runs',
      sortable: true,
      render: (wf) => <span className={styles.numCol}>{wf.total_runs}</span>,
      sortValue: (wf) => wf.total_runs,
    },
    {
      key: 'successes',
      header: 'Successes',
      sortable: true,
      render: (wf) => <span className={styles.numCol}>{wf.successes}</span>,
      sortValue: (wf) => wf.successes,
    },
    {
      key: 'failures',
      header: 'Failures',
      sortable: true,
      render: (wf) => <span className={styles.numCol}>{wf.failures}</span>,
      sortValue: (wf) => wf.failures,
    },
    {
      key: 'failure_rate',
      header: 'Failure rate',
      sortable: true,
      render: (wf) => (
        <Label variant={failureRateVariant(wf.failure_rate_pct)}>
          {wf.failure_rate_pct.toFixed(1)}%
        </Label>
      ),
      sortValue: (wf) => wf.failure_rate_pct,
    },
    {
      key: 'last_run',
      header: 'Last run',
      sortable: true,
      render: (wf) => (
        <span style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(wf.last_run)}</span>
      ),
      sortValue: (wf) => wf.last_run,
    },
  ];

  return (
    <div>
      <div className={styles.sectionTitle}>Workflow health</div>
      <div className={styles.sectionSub}>
        Per-workflow run metrics derived from{' '}
        <code className={styles.codeSnippet}>workflow_run.*</code> events.
      </div>
      <div className={styles.tableWrap}>
        <DataTable
          columns={columns}
          data={workflows}
          rowKey={(wf) => `${wf.repo}/${wf.workflow_name}`}
          emptyMessage="No workflow data available"
        />
      </div>
    </div>
  );
}

function RunnerFleetTable({ runners }: { runners: RunnerRow[] }) {
  const columns: ColumnDef<RunnerRow>[] = [
    {
      key: 'org',
      header: 'Organization',
      sortable: true,
      filterable: true,
      render: (r) => r.org,
      sortValue: (r) => r.org,
      filterValue: (r) => r.org,
    },
    {
      key: 'runner_name',
      header: 'Runner name',
      sortable: true,
      filterable: true,
      render: (r) => r.runner_name,
      sortValue: (r) => r.runner_name,
      filterValue: (r) => r.runner_name,
    },
    {
      key: 'version',
      header: 'Version',
      sortable: true,
      render: (r) => <span className={styles.numCol}>{r.version}</span>,
      sortValue: (r) => r.version,
    },
    {
      key: 'group',
      header: 'Group',
      sortable: true,
      filterable: true,
      render: (r) => r.group,
      sortValue: (r) => r.group,
      filterValue: (r) => r.group,
    },
    {
      key: 'last_event',
      header: 'Last event',
      sortable: true,
      render: (r) => (
        <span style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(r.last_event)}</span>
      ),
      sortValue: (r) => r.last_event,
    },
  ];

  return (
    <div>
      <div className={styles.sectionTitle}>Runner fleet</div>
      <div className={styles.sectionSub}>
        Self-hosted runner inventory derived from{' '}
        <code className={styles.codeSnippet}>action.self_hosted_runner.*</code> events.
      </div>
      <div className={styles.tableWrap}>
        <DataTable
          columns={columns}
          data={runners}
          rowKey={(r) => `${r.org}/${r.runner_name}`}
          emptyMessage="No runner data available"
        />
      </div>
    </div>
  );
}

/* ---------- main pane ---------- */

export function OpsHealthPane() {
  const [opsDrilldown, setOpsDrilldown] = useState<{
    title: string;
    metricName: string;
  } | null>(null);

  const workflowQuery = useQuery({
    queryKey: ['health', 'workflows'],
    queryFn: getWorkflowHealth,
    staleTime: 60_000,
  });

  const branchQuery = useQuery({
    queryKey: ['health', 'branch-protection'],
    queryFn: getBranchProtection,
    staleTime: 60_000,
  });

  const copilotQuery = useQuery({
    queryKey: ['health', 'copilot-governance'],
    queryFn: getCopilotGovernance,
    staleTime: 60_000,
  });

  const codespacesQuery = useQuery({
    queryKey: ['health', 'codespaces'],
    queryFn: getCodespaces,
    staleTime: 60_000,
  });

  const runnerQuery = useQuery({
    queryKey: ['health', 'runners'],
    queryFn: getRunnerHealth,
    staleTime: 60_000,
  });

  const isLoading =
    workflowQuery.isLoading ||
    branchQuery.isLoading ||
    copilotQuery.isLoading ||
    codespacesQuery.isLoading ||
    runnerQuery.isLoading;

  const isError =
    workflowQuery.isError ||
    branchQuery.isError ||
    copilotQuery.isError ||
    codespacesQuery.isError ||
    runnerQuery.isError;

  if (isLoading) {
    return (
      <div className={styles.centered}>
        <Spinner size={28} />
      </div>
    );
  }

  if (isError) {
    const retryAll = () => {
      void workflowQuery.refetch();
      void branchQuery.refetch();
      void copilotQuery.refetch();
      void codespacesQuery.refetch();
      void runnerQuery.refetch();
    };
    return <ErrorBanner message="Failed to load operations health data" onRetry={retryAll} />;
  }

  const workflows = workflowQuery.data?.workflows ?? [];
  const branch = branchQuery.data;
  const copilot = copilotQuery.data;
  const codespaces = codespacesQuery.data;
  const runners = runnerQuery.data?.runners ?? [];

  return (
    <div className={styles.pane}>
      <SampleDataBanner message="Operations health signals are derived from audit log events. Workflow and runner metrics reflect the last 30 days of activity." />

      {/* Workflow Health Table */}
      <WorkflowHealthTable workflows={workflows} />

      {/* Branch Protection (30d) */}
      <div>
        <div className={styles.sectionTitle}>Branch protection changes (30d)</div>
        <div className={styles.sectionSub}>
          Policy weakening events derived from{' '}
          <code className={styles.codeSnippet}>protected_branch.*</code> events.
        </div>
        <div className={styles.metricGrid}>
          <MetricCard
            value={String(branch?.protections_removed ?? 0)}
            label="Protections removed"
            accent={branch != null && branch.protections_removed > 0}
            onClick={() =>
              setOpsDrilldown({
                title: 'Protections removed (30d)',
                metricName: 'protections_removed',
              })
            }
          />
          <MetricCard
            value={String(branch?.policy_overrides ?? 0)}
            label="Policy overrides"
            accent={branch != null && branch.policy_overrides > 0}
            onClick={() =>
              setOpsDrilldown({
                title: 'Policy overrides (30d)',
                metricName: 'policy_overrides',
              })
            }
          />
          <MetricCard
            value={String(branch?.modified ?? 0)}
            label="Modified"
            onClick={() =>
              setOpsDrilldown({
                title: 'Branch protections modified (30d)',
                metricName: 'modified',
              })
            }
          />
          <MetricCard
            value={String(branch?.distinct_repos_affected ?? 0)}
            label="Repos affected"
            onClick={() =>
              setOpsDrilldown({
                title: 'Repos with branch protection changes (30d)',
                metricName: 'repos_affected',
              })
            }
          />
        </div>
      </div>

      {/* Copilot Governance */}
      <div>
        <div className={styles.sectionTitle}>Copilot governance</div>
        <div className={styles.sectionSub}>
          Seat management events derived from <code className={styles.codeSnippet}>copilot.*</code>{' '}
          events.
        </div>
        <div className={styles.metricGrid}>
          <MetricCard
            value={String(copilot?.seats_granted_90d ?? 0)}
            label="Seats granted (90d)"
            onClick={() =>
              setOpsDrilldown({
                title: 'Copilot seats granted (90d)',
                metricName: 'seats_granted',
              })
            }
          />
          <MetricCard
            value={String(copilot?.seats_removed ?? 0)}
            label="Seats removed"
            onClick={() =>
              setOpsDrilldown({
                title: 'Copilot seats removed',
                metricName: 'seats_removed',
              })
            }
          />
          <MetricCard
            value={String(copilot?.unique_users ?? 0)}
            label="Unique users"
            onClick={() =>
              setOpsDrilldown({
                title: 'Copilot unique users',
                metricName: 'unique_users',
              })
            }
          />
        </div>
      </div>

      {/* Codespace Activity */}
      <div>
        <div className={styles.sectionTitle}>Codespace activity</div>
        <div className={styles.sectionSub}>
          Codespace lifecycle events derived from{' '}
          <code className={styles.codeSnippet}>codespaces.*</code> events.
        </div>
        <div className={styles.metricGrid}>
          <MetricCard
            value={String(codespaces?.active_never_suspended ?? 0)}
            label="Active never suspended"
            accent={codespaces != null && codespaces.active_never_suspended > 0}
            onClick={() =>
              setOpsDrilldown({
                title: 'Codespaces active (never suspended)',
                metricName: 'active_never_suspended',
              })
            }
          />
          <MetricCard
            value={String(codespaces?.large_machine_count ?? 0)}
            label="Large machine count"
            onClick={() =>
              setOpsDrilldown({
                title: 'Large machine codespaces',
                metricName: 'large_machine',
              })
            }
          />
          <MetricCard
            value={String(codespaces?.unique_users ?? 0)}
            label="Unique users"
            onClick={() =>
              setOpsDrilldown({
                title: 'Codespace unique users',
                metricName: 'codespace_users',
              })
            }
          />
        </div>
      </div>

      {/* Ops Drilldown Modal */}
      <DrilldownModal
        open={opsDrilldown !== null}
        onClose={() => setOpsDrilldown(null)}
        title={opsDrilldown?.title ?? ''}
        data={
          opsDrilldown
            ? [
                {
                  metric: opsDrilldown.metricName,
                  note: 'Per-event detail requires GitHub API integration.',
                },
              ]
            : []
        }
        columns={[
          {
            key: 'metric',
            header: 'Metric',
            render: (r: { metric: string; note: string }) => r.metric,
          },
          {
            key: 'note',
            header: 'Note',
            render: (r: { metric: string; note: string }) => r.note,
          },
        ]}
        rowKey={(r: { metric: string }) => r.metric}
      />

      {/* Runner Fleet Table */}
      <RunnerFleetTable runners={runners} />
    </div>
  );
}
