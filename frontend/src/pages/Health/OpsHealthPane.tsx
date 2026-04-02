import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Label } from '../../components/primitives/Label';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
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
  return (
    <div>
      <div className={styles.sectionTitle}>Workflow health</div>
      <div className={styles.sectionSub}>
        Per-workflow run metrics derived from{' '}
        <code className={styles.codeSnippet}>workflow_run.*</code> events.
      </div>
      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Repository</th>
              <th>Workflow</th>
              <th>Total runs</th>
              <th>Successes</th>
              <th>Failures</th>
              <th>Failure rate</th>
              <th>Last run</th>
            </tr>
          </thead>
          <tbody>
            {workflows.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  style={{ textAlign: 'center', color: 'var(--fg-muted)', padding: 24 }}
                >
                  No workflow data available
                </td>
              </tr>
            )}
            {workflows.map((wf) => (
              <tr key={`${wf.repo}/${wf.workflow_name}`}>
                <td>{wf.repo}</td>
                <td className={styles.workflowName}>{wf.workflow_name}</td>
                <td className={styles.numCol}>{wf.total_runs}</td>
                <td className={styles.numCol}>{wf.successes}</td>
                <td className={styles.numCol}>{wf.failures}</td>
                <td>
                  <Label variant={failureRateVariant(wf.failure_rate_pct)}>
                    {wf.failure_rate_pct.toFixed(1)}%
                  </Label>
                </td>
                <td style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(wf.last_run)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RunnerFleetTable({ runners }: { runners: RunnerRow[] }) {
  return (
    <div>
      <div className={styles.sectionTitle}>Runner fleet</div>
      <div className={styles.sectionSub}>
        Self-hosted runner inventory derived from{' '}
        <code className={styles.codeSnippet}>action.self_hosted_runner.*</code> events.
      </div>
      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Organization</th>
              <th>Runner name</th>
              <th>Version</th>
              <th>Group</th>
              <th>Last event</th>
            </tr>
          </thead>
          <tbody>
            {runners.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  style={{ textAlign: 'center', color: 'var(--fg-muted)', padding: 24 }}
                >
                  No runner data available
                </td>
              </tr>
            )}
            {runners.map((r) => (
              <tr key={`${r.org}/${r.runner_name}`}>
                <td>{r.org}</td>
                <td>{r.runner_name}</td>
                <td className={styles.numCol}>{r.version}</td>
                <td>{r.group}</td>
                <td style={{ color: 'var(--fg-muted)' }}>{formatDateOnly(r.last_event)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
          />
          <MetricCard
            value={String(branch?.policy_overrides ?? 0)}
            label="Policy overrides"
            accent={branch != null && branch.policy_overrides > 0}
          />
          <MetricCard value={String(branch?.modified ?? 0)} label="Modified" />
          <MetricCard value={String(branch?.distinct_repos_affected ?? 0)} label="Repos affected" />
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
          <MetricCard value={String(copilot?.seats_granted_90d ?? 0)} label="Seats granted (90d)" />
          <MetricCard value={String(copilot?.seats_removed ?? 0)} label="Seats removed" />
          <MetricCard value={String(copilot?.unique_users ?? 0)} label="Unique users" />
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
          />
          <MetricCard
            value={String(codespaces?.large_machine_count ?? 0)}
            label="Large machine count"
          />
          <MetricCard value={String(codespaces?.unique_users ?? 0)} label="Unique users" />
        </div>
      </div>

      {/* Runner Fleet Table */}
      <RunnerFleetTable runners={runners} />
    </div>
  );
}
