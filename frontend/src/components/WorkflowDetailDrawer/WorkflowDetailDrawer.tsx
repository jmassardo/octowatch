import { useQuery } from '@tanstack/react-query';
import { Drawer } from '../primitives/Drawer';
import { Spinner } from '../primitives/Spinner';
import { ErrorBanner } from '../primitives/ErrorBanner';
import { getWorkflowRunHistory } from '../../api/workflowMetrics';
import type { WorkflowFailureSummary, WorkflowRunRecord } from '../../api/workflowMetrics';
import { formatRelativeShort } from '../../utils/dates';
import { analyzeFailurePattern, getRemediationSuggestions } from './remediationGuidance';
import type { FailurePattern, RemediationSuggestion } from './remediationGuidance';
import styles from './WorkflowDetailDrawer.module.css';

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—';
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function dotClass(conclusion: string): string {
  switch (conclusion) {
    case 'success':
      return styles.dotSuccess;
    case 'failure':
      return styles.dotFailure;
    case 'timed_out':
      return styles.dotTimeout;
    default:
      return styles.dotMuted;
  }
}

function failureRateColorClass(rate: number): string {
  if (rate >= 80) return styles.statDanger;
  if (rate >= 40) return styles.statWarning;
  return styles.statSuccess;
}

function buildGitHubRunUrl(org: string, repo: string, runId: string): string {
  return `https://github.com/${org}/${repo}/actions/runs/${runId}`;
}

function buildGitHubWorkflowUrl(org: string, repo: string): string {
  return `https://github.com/${org}/${repo}/actions`;
}

// ── Sub-components ───────────────────────────────────────────────────────────

interface PatternAnalysisProps {
  pattern: FailurePattern;
}

function PatternAnalysis({ pattern }: PatternAnalysisProps) {
  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>Failure Pattern Analysis</div>
      <div className={styles.patternBox}>
        <div className={styles.patternStats}>
          <div className={styles.statBlock}>
            <span className={styles.statValue}>{pattern.totalRuns}</span>
            <span className={styles.statLabel}>Runs</span>
          </div>
          <div className={styles.statBlock}>
            <span className={`${styles.statValue} ${styles.statDanger}`}>{pattern.failedRuns}</span>
            <span className={styles.statLabel}>Failed</span>
          </div>
          <div className={styles.statBlock}>
            <span className={`${styles.statValue} ${failureRateColorClass(pattern.failureRate)}`}>
              {pattern.failureRate}%
            </span>
            <span className={styles.statLabel}>Fail Rate</span>
          </div>
          <div className={styles.statBlock}>
            <span className={`${styles.statValue} ${styles.statDanger}`}>
              {pattern.consecutiveFailures}
            </span>
            <span className={styles.statLabel}>Streak</span>
          </div>
        </div>
        <p className={styles.patternSummary}>{pattern.summary}</p>
      </div>
    </div>
  );
}

interface RunHistoryListProps {
  runs: WorkflowRunRecord[];
  org: string;
  repo: string;
}

function RunHistoryList({ runs, org, repo }: RunHistoryListProps) {
  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>Recent Runs ({runs.length})</div>
      {runs.length === 0 ? (
        <div className={styles.emptyMsg}>No runs found in this period.</div>
      ) : (
        <ul className={styles.runList}>
          {runs.map((run, idx) => (
            <li key={run.run_id ?? idx} className={styles.runItem}>
              <span className={`${styles.runDot} ${dotClass(run.conclusion)}`} />
              <div className={styles.runMeta}>
                <span className={styles.runConclusion}>{run.conclusion}</span>
                <span className={styles.runTime}>{formatRelativeShort(run.started_at)}</span>
                <span className={styles.runDuration}>{formatDuration(run.duration_seconds)}</span>
              </div>
              {run.run_id && (
                <a
                  className={styles.runLink}
                  href={buildGitHubRunUrl(org, repo, run.run_id)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  View →
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

interface RemediationSectionProps {
  suggestions: RemediationSuggestion[];
}

function RemediationSection({ suggestions }: RemediationSectionProps) {
  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>Remediation Guidance</div>
      <ul className={styles.suggestionList}>
        {suggestions.map((s, idx) => (
          <li key={idx} className={styles.suggestion}>
            <div className={styles.suggestionTitle}>{s.title}</div>
            <p className={styles.suggestionDesc}>{s.description}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

interface WorkflowDetailDrawerProps {
  /** The selected workflow to show details for. `null` when closed. */
  workflow: WorkflowFailureSummary | null;
  /** How many days of history to fetch. */
  lookbackDays: number;
  /** Called when the drawer should close. */
  onClose: () => void;
}

export function WorkflowDetailDrawer({
  workflow,
  lookbackDays,
  onClose,
}: WorkflowDetailDrawerProps) {
  const isOpen = workflow !== null;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: [
      'workflow-detail',
      'run-history',
      workflow?.org,
      workflow?.repo,
      workflow?.workflow_name,
      lookbackDays,
    ],
    queryFn: () =>
      getWorkflowRunHistory({
        org: workflow!.org,
        repo: workflow!.repo,
        workflow_name: workflow!.workflow_name,
        lookback_days: lookbackDays,
        limit: 20,
      }),
    enabled: isOpen,
    staleTime: 60_000,
  });

  const runs = data?.runs ?? [];
  const pattern = analyzeFailurePattern(runs);
  const suggestions = workflow ? getRemediationSuggestions(workflow.last_conclusion, pattern) : [];

  const drawerTitle = workflow ? `${workflow.workflow_name}` : 'Workflow Detail';

  return (
    <Drawer open={isOpen} onClose={onClose} title={drawerTitle} titleId="workflow-detail-title">
      {workflow && (
        <>
          {/* Metadata */}
          <div className={styles.metaGrid}>
            <span className={styles.metaLabel}>Organization</span>
            <span className={styles.metaValue}>{workflow.org}</span>
            <span className={styles.metaLabel}>Repository</span>
            <span className={styles.metaValue}>{workflow.repo}</span>
            <span className={styles.metaLabel}>Last conclusion</span>
            <span className={styles.metaValue}>{workflow.last_conclusion}</span>
            <span className={styles.metaLabel}>Consecutive</span>
            <span className={styles.metaValue}>
              {workflow.consecutive_count}× {workflow.last_conclusion}
            </span>
          </div>

          {/* Loading / error */}
          {isLoading && (
            <div className={styles.centered}>
              <Spinner />
            </div>
          )}
          {isError && (
            <ErrorBanner message="Failed to load run history" onRetry={() => void refetch()} />
          )}

          {/* Content (only after data loads) */}
          {!isLoading && !isError && (
            <>
              <PatternAnalysis pattern={pattern} />
              <RunHistoryList runs={runs} org={workflow.org} repo={workflow.repo} />
              <RemediationSection suggestions={suggestions} />

              {/* Direct link to GitHub Actions */}
              <div className={styles.section}>
                <a
                  className={styles.ghLinkButton}
                  href={buildGitHubWorkflowUrl(workflow.org, workflow.repo)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  View all runs on GitHub Actions →
                </a>
              </div>
            </>
          )}
        </>
      )}
    </Drawer>
  );
}
