import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listWorkflowFindings, getRepoSecurityScores } from '../../api/workflowScanner';
import type { WorkflowFinding, RepoSecurityScore } from '../../api/workflowScanner';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Label } from '../../components/primitives/Label';
import { formatRelativeShort } from '../../utils/dates';
import styles from './Workflows.module.css';

type Tab = 'findings' | 'scores';

function sevVariant(sev: string) {
  if (sev === 'critical') return 'danger' as const;
  if (sev === 'high') return 'severe' as const;
  if (sev === 'medium') return 'attention' as const;
  return 'muted' as const;
}

function scoreClass(score: number): string {
  if (score >= 80) return styles.scoreGood;
  if (score >= 50) return styles.scoreWarn;
  return styles.scoreBad;
}

function FindingRow({ finding }: { finding: WorkflowFinding }) {
  return (
    <tr className={styles.findingRow}>
      <td>
        <Label variant={sevVariant(finding.severity)}>{finding.severity}</Label>
      </td>
      <td>{finding.title}</td>
      <td className={styles.repoPath}>
        {finding.org}/{finding.repo}
      </td>
      <td className={styles.repoPath}>{finding.workflow_path}</td>
      <td>
        <Label variant={finding.status === 'open' ? 'attention' : 'muted'}>{finding.status}</Label>
      </td>
      <td className={styles.timeCell}>{formatRelativeShort(finding.last_seen)}</td>
    </tr>
  );
}

function ScoreCard({ score }: { score: RepoSecurityScore }) {
  return (
    <div className={styles.scoreCard}>
      <div className={styles.scoreHeader}>
        <span className={styles.scoreRepo}>
          {score.org}/{score.repo}
        </span>
        <span className={`${styles.scoreValue} ${scoreClass(score.score)}`}>
          {Math.round(score.score)}
        </span>
      </div>
      <div className={styles.scoreMeta}>
        <span>{score.finding_count} findings</span>
        {score.critical_count > 0 && <span>{score.critical_count} critical</span>}
        {score.high_count > 0 && <span>{score.high_count} high</span>}
      </div>
    </div>
  );
}

export function WorkflowsPage() {
  const [tab, setTab] = useState<Tab>('findings');
  const [sevFilter, setSevFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const {
    data: findingsData,
    isLoading: loadingFindings,
    isError: findingsError,
    refetch: refetchFindings,
  } = useQuery({
    queryKey: ['workflow-scanner', 'findings', sevFilter, statusFilter],
    queryFn: () =>
      listWorkflowFindings({
        severity: sevFilter || undefined,
        status: statusFilter || undefined,
        page_size: 50,
      }),
    enabled: tab === 'findings',
  });

  const {
    data: scores,
    isLoading: loadingScores,
    isError: scoresError,
    refetch: refetchScores,
  } = useQuery({
    queryKey: ['workflow-scanner', 'scores'],
    queryFn: () => getRepoSecurityScores(),
    enabled: tab === 'scores',
  });

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Workflow Security Scanner</div>
      <div className={styles.pageSub}>
        Scan GitHub Actions workflows for security issues and misconfigurations
      </div>

      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${tab === 'findings' ? styles.tabActive : ''}`}
          onClick={() => setTab('findings')}
        >
          Findings
        </button>
        <button
          className={`${styles.tab} ${tab === 'scores' ? styles.tabActive : ''}`}
          onClick={() => setTab('scores')}
        >
          Repo Scores
        </button>
      </div>

      {tab === 'findings' && (
        <>
          <div className={styles.filters}>
            <select
              className={styles.filterSelect}
              value={sevFilter}
              onChange={(e) => setSevFilter(e.target.value)}
            >
              <option value="">All severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <select
              className={styles.filterSelect}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">All statuses</option>
              <option value="open">Open</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
            </select>
          </div>

          {loadingFindings && <Spinner />}
          {findingsError && (
            <ErrorBanner message="Failed to load findings" onRetry={() => void refetchFindings()} />
          )}
          {findingsData && findingsData.findings.length === 0 && (
            <div className={styles.emptyState}>No workflow findings found</div>
          )}
          {findingsData && findingsData.findings.length > 0 && (
            <table className={styles.findingsTable}>
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Title</th>
                  <th>Repository</th>
                  <th>Workflow</th>
                  <th>Status</th>
                  <th>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {findingsData.findings.map((f) => (
                  <FindingRow key={f.id} finding={f} />
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      {tab === 'scores' && (
        <>
          {loadingScores && <Spinner />}
          {scoresError && (
            <ErrorBanner message="Failed to load scores" onRetry={() => void refetchScores()} />
          )}
          {scores && scores.length === 0 && (
            <div className={styles.emptyState}>No repository scores available</div>
          )}
          {scores && scores.length > 0 && (
            <div className={styles.scoreGrid}>
              {scores.map((s) => (
                <ScoreCard key={`${s.org}/${s.repo}`} score={s} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
