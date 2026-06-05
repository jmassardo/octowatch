import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Drawer } from '../../components/primitives/Drawer';
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
  const [selectedRow, setSelectedRow] = useState<WorkflowRow | null>(null);
  const columns: ColumnDef<WorkflowRow>[] = [
    {
      key: 'repo',
      header: 'Repository',
      sortable: true,
      filterable: true,
      render: (wf) => wf.repo,
      sortValue: (wf) => wf.repo,
      filterValue: (wf) => wf.repo,
      helpText:
        'The GitHub repository where this workflow is defined. Filter to focus on specific repos.',
    },
    {
      key: 'workflow',
      header: 'Workflow',
      sortable: true,
      filterable: true,
      render: (wf) => <span className={styles.workflowName}>{wf.workflow_name}</span>,
      sortValue: (wf) => wf.workflow_name,
      filterValue: (wf) => wf.workflow_name,
      helpText: 'The GitHub Actions workflow name. Derived from workflow_run audit events.',
    },
    {
      key: 'total_runs',
      header: 'Total runs',
      sortable: true,
      render: (wf) => <span className={styles.numCol}>{wf.total_runs}</span>,
      sortValue: (wf) => wf.total_runs,
      helpText:
        'Total number of workflow runs in the last 30 days. Derived from workflow_run.completed events.',
    },
    {
      key: 'successes',
      header: 'Successes',
      sortable: true,
      render: (wf) => <span className={styles.numCol}>{wf.successes}</span>,
      sortValue: (wf) => wf.successes,
      helpText:
        'Number of successful workflow runs. Derived from workflow_run.completed events with success conclusion.',
    },
    {
      key: 'failures',
      header: 'Failures',
      sortable: true,
      render: (wf) => <span className={styles.numCol}>{wf.failures}</span>,
      sortValue: (wf) => wf.failures,
      helpText:
        'Number of failed workflow runs. Derived from workflow_run.completed events with failure conclusion.',
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
      helpText:
        'Percentage of recent workflow runs that failed. Derived from workflow_run audit events. Investigate workflows with rates above 20%.',
    },
    {
      key: 'last_run_at',
      header: 'Last run',
      sortable: true,
      render: (wf) => (
        <span style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(wf.last_run_at)}</span>
      ),
      sortValue: (wf) => wf.last_run_at,
      helpText:
        'Date of the most recent workflow run. Stale workflows may indicate disabled or broken CI pipelines.',
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
          onRowClick={(row) => setSelectedRow(row)}
        />
      </div>
      <Drawer open={!!selectedRow} onClose={() => setSelectedRow(null)} title="Workflow Details">
        {selectedRow && (
          <dl style={{ padding: '16px' }}>
            {Object.entries(selectedRow).map(([key, value]) => (
              <div key={key} style={{ marginBottom: 8 }}>
                <dt style={{ fontSize: '0.8em', color: 'var(--fg-muted)', marginBottom: 2 }}>
                  {key}
                </dt>
                <dd style={{ margin: 0 }}>{String(value ?? '—')}</dd>
              </div>
            ))}
          </dl>
        )}
      </Drawer>
    </div>
  );
}

function RunnerFleetTable({ runners }: { runners: RunnerRow[] }) {
  const [selectedRow, setSelectedRow] = useState<RunnerRow | null>(null);
  const columns: ColumnDef<RunnerRow>[] = [
    {
      key: 'org',
      header: 'Organization',
      sortable: true,
      filterable: true,
      render: (r) => r.org,
      sortValue: (r) => r.org,
      filterValue: (r) => r.org,
      helpText: 'The GitHub organization that owns this self-hosted runner.',
    },
    {
      key: 'runner_name',
      header: 'Runner name',
      sortable: true,
      filterable: true,
      render: (r) => r.runner_name,
      sortValue: (r) => r.runner_name,
      filterValue: (r) => r.runner_name,
      helpText:
        'Name of the self-hosted runner. Derived from action.self_hosted_runner.* audit events.',
    },
    {
      key: 'version',
      header: 'Version',
      sortable: true,
      render: (r) => <span className={styles.numCol}>{r.version}</span>,
      sortValue: (r) => r.version,
      helpText:
        'Runner agent version. Outdated versions may miss security patches or lack new features.',
    },
    {
      key: 'group',
      header: 'Group',
      sortable: true,
      filterable: true,
      render: (r) => r.group,
      sortValue: (r) => r.group,
      filterValue: (r) => r.group,
      helpText:
        'Runner group assignment for access control. Review group membership for least-privilege compliance.',
    },
    {
      key: 'last_event',
      header: 'Last event',
      sortable: true,
      render: (r) => (
        <span style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(r.last_event)}</span>
      ),
      sortValue: (r) => r.last_event,
      helpText:
        'Most recent audit event for this runner. Stale runners may be offline or decommissioned.',
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
          onRowClick={(row) => setSelectedRow(row)}
        />
      </div>
      <Drawer open={!!selectedRow} onClose={() => setSelectedRow(null)} title="Runner Details">
        {selectedRow && (
          <dl style={{ padding: '16px' }}>
            {Object.entries(selectedRow).map(([key, value]) => (
              <div key={key} style={{ marginBottom: 8 }}>
                <dt style={{ fontSize: '0.8em', color: 'var(--fg-muted)', marginBottom: 2 }}>
                  {key}
                </dt>
                <dd style={{ margin: 0 }}>{String(value ?? '—')}</dd>
              </div>
            ))}
          </dl>
        )}
      </Drawer>
    </div>
  );
}

/* ---------- main pane ---------- */

export function OpsHealthPane() {
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
            helpText="Number of branch protection rules removed in the last 30 days. Sourced from protected_branch.destroy events. Investigate unexpected removals."
          />
          <MetricCard
            value={String(branch?.policy_overrides ?? 0)}
            label="Policy overrides"
            accent={branch != null && branch.policy_overrides > 0}
            helpText="Number of branch protection policy overrides in the last 30 days. Sourced from protected_branch.policy_override events. Review for unauthorized weakening."
          />
          <MetricCard
            value={String(branch?.modified ?? 0)}
            label="Modified"
            helpText="Number of branch protection rules modified in the last 30 days. Sourced from protected_branch.update events."
          />
          <MetricCard
            value={String(branch?.distinct_repos_affected ?? 0)}
            label="Repos affected"
            helpText="Number of distinct repositories with branch protection changes in the last 30 days. High counts may indicate a policy rollout or a security concern."
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
            helpText="Number of Copilot seats granted in the last 90 days. Derived from copilot.seat_assignment_created events."
          />
          <MetricCard
            value={String(copilot?.seats_removed ?? 0)}
            label="Seats removed"
            helpText="Number of Copilot seats removed. Derived from copilot.seat_cancelled events. Review for unexpected seat churn."
          />
          <MetricCard
            value={String(copilot?.unique_users ?? 0)}
            label="Unique users"
            helpText="Number of unique users with Copilot activity. Derived from copilot.* audit events."
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
            helpText="Codespaces that have never been suspended. Derived from codespaces.create events with no corresponding suspend. These may incur ongoing compute costs."
          />
          <MetricCard
            value={String(codespaces?.large_machine_count ?? 0)}
            label="Large machine count"
            helpText="Number of codespaces using large machine types. Derived from codespaces.create events. Large machines have higher hourly cost."
          />
          <MetricCard
            value={String(codespaces?.unique_users ?? 0)}
            label="Unique users"
            helpText="Number of unique users with codespace activity. Derived from codespaces.* audit events."
          />
        </div>
      </div>

      {/* Runner Fleet Table */}
      <RunnerFleetTable runners={runners} />
    </div>
  );
}
