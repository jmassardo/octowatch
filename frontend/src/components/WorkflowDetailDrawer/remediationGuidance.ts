import type { WorkflowRunRecord } from '../../api/workflowMetrics';

// ── Pattern analysis ────────────────────────────────────────────────────────

export interface FailurePattern {
  /** Total runs in the window. */
  totalRuns: number;
  /** Number of runs that ended in failure/timed_out (not success). */
  failedRuns: number;
  /** Failure rate as a percentage (0–100). */
  failureRate: number;
  /** How many of the most recent consecutive runs failed. */
  consecutiveFailures: number;
  /** Human-readable summary of the pattern. */
  summary: string;
}

/**
 * Analyze an array of runs (most-recent first) and return pattern data.
 */
export function analyzeFailurePattern(runs: WorkflowRunRecord[]): FailurePattern {
  if (runs.length === 0) {
    return {
      totalRuns: 0,
      failedRuns: 0,
      failureRate: 0,
      consecutiveFailures: 0,
      summary: 'No runs found in the selected period.',
    };
  }

  const totalRuns = runs.length;
  const failedRuns = runs.filter(
    (r) => r.conclusion === 'failure' || r.conclusion === 'timed_out',
  ).length;
  const failureRate = Math.round((failedRuns / totalRuns) * 100);

  let consecutiveFailures = 0;
  for (const run of runs) {
    if (run.conclusion === 'failure' || run.conclusion === 'timed_out') {
      consecutiveFailures++;
    } else {
      break;
    }
  }

  const summary = buildPatternSummary(totalRuns, failedRuns, failureRate, consecutiveFailures);

  return { totalRuns, failedRuns, failureRate, consecutiveFailures, summary };
}

function buildPatternSummary(
  totalRuns: number,
  failedRuns: number,
  failureRate: number,
  consecutiveFailures: number,
): string {
  if (failedRuns === 0) {
    return `All ${totalRuns} recent runs succeeded.`;
  }
  if (failedRuns === totalRuns) {
    return `Every run (${totalRuns} of ${totalRuns}) has failed — this workflow appears completely broken.`;
  }
  const parts: string[] = [];
  parts.push(`${failedRuns} of the last ${totalRuns} runs failed (${failureRate}% failure rate).`);
  if (consecutiveFailures > 1) {
    parts.push(`The last ${consecutiveFailures} consecutive runs all failed.`);
  }
  return parts.join(' ');
}

// ── Remediation guidance ────────────────────────────────────────────────────

export interface RemediationSuggestion {
  title: string;
  description: string;
}

/**
 * Return actionable remediation suggestions based on the last conclusion
 * and observed failure pattern.
 */
export function getRemediationSuggestions(
  lastConclusion: string,
  pattern: FailurePattern,
): RemediationSuggestion[] {
  const suggestions: RemediationSuggestion[] = [];

  if (lastConclusion === 'failure') {
    suggestions.push({
      title: 'Check recent code changes',
      description:
        'Review commits merged around the time failures started. A broken test, missing dependency, or config change is the most common cause.',
    });
    suggestions.push({
      title: 'Review build and test logs',
      description:
        'Open the failing run on GitHub Actions and expand the failed step. Look for dependency errors (npm ERR!, pip install failures), compilation errors, or assertion failures.',
    });
    suggestions.push({
      title: 'Verify secrets and environment variables',
      description:
        'Expired tokens, rotated API keys, or missing secrets are a frequent cause of persistent failures. Check Settings → Secrets and variables.',
    });
  }

  if (lastConclusion === 'timed_out') {
    suggestions.push({
      title: 'Increase the workflow timeout',
      description:
        'If the job is legitimately slow, increase timeout-minutes in the workflow YAML. The default is 360 minutes per job.',
    });
    suggestions.push({
      title: 'Look for infinite loops or hung processes',
      description:
        'A process waiting for input, a network call with no timeout, or an infinite retry loop can cause the runner to hang until the job times out.',
    });
    suggestions.push({
      title: 'Check runner resource limits',
      description:
        'Self-hosted runners may have limited CPU, memory, or disk. GitHub-hosted runners have fixed limits — large builds may need a larger runner type.',
    });
  }

  if (pattern.failureRate === 100 && pattern.totalRuns >= 3) {
    suggestions.push({
      title: 'Consider disabling the workflow',
      description:
        'This workflow has failed every run in the lookback window. If it is not actively maintained, disabling it avoids wasted runner minutes and alert noise.',
    });
  }

  if (pattern.consecutiveFailures >= 5) {
    suggestions.push({
      title: 'Escalate to the workflow owner',
      description:
        "Persistent consecutive failures usually indicate a systemic issue (broken config, removed dependency, infrastructure change) that needs the code owner's attention.",
    });
  }

  if (suggestions.length === 0) {
    suggestions.push({
      title: 'Investigate on GitHub Actions',
      description:
        'Open the latest failing run on GitHub Actions and review the logs for the failed step. The error output will point to the root cause.',
    });
  }

  return suggestions;
}
