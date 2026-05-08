import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  listWorkflowFindings,
  getRepoSecurityScores,
  triggerRepoScan,
} from '../../api/workflowScanner';
import type { WorkflowFinding, RepoSecurityScore } from '../../api/workflowScanner';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { PageHeader } from '../../components/common/PageHeader';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { formatRelativeShort } from '../../utils/dates';
import { ScannerActivityTab } from './ScannerActivityTab';
import styles from './Workflows.module.css';

type Tab = 'findings' | 'scores' | 'activity';

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
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>('findings');
  const [sevFilter, setSevFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedFinding, setSelectedFinding] = useState<WorkflowFinding | null>(null);

  const scanMutation = useMutation({
    mutationFn: triggerRepoScan,
    onSuccess: () => {
      // Poll for new data after a delay
      setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: ['workflow-scanner'] });
      }, 5000);
    },
  });

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
    <div className={styles.splitLayout}>
      <div className={styles.splitMain}>
        <div className={styles.pageHeader}>
          <div>
            <PageHeader
              title="Workflow Security Scanner"
              description="Scan GitHub Actions workflows for security issues"
            />
          </div>
          <div className={styles.headerActions}>
            <Button
              size="sm"
              variant="primary"
              onClick={() => scanMutation.mutate()}
              disabled={scanMutation.isPending}
            >
              {scanMutation.isPending ? 'Analyzing…' : 'Analyze Events'}
            </Button>
            {scanMutation.isSuccess && (
              <span className={styles.scanStatus}>Analysis queued — results appear shortly</span>
            )}
            {scanMutation.isError && <span className={styles.scanError}>Analysis failed</span>}
          </div>
        </div>

        <div className={styles.crossLink}>
          Looking for CI/CD failure metrics?{' '}
          <Link to="/workflows/health" className={styles.crossLinkAnchor}>
            Workflow Health →
          </Link>
        </div>

        <div className={styles.guidanceBox}>
          <div className={styles.guidanceTitle}>What this page shows</div>
          <ul className={styles.guidanceList}>
            <li>
              <strong>Findings</strong> — Security issues detected in workflow YAML files: unpinned
              actions, script injection, excessive permissions, and more.
            </li>
            <li>
              <strong>Repo Scores</strong> — Per-repo security scores (100 = clean, lower = more
              issues). Scores are weighted by severity.
            </li>
            <li>
              Click <strong>Analyze Events</strong> to scan workflow audit log events for security
              anti-patterns — no GitHub API calls are made.
            </li>
          </ul>
        </div>

        <div className={styles.tabs}>
          <button
            className={`${styles.tab} ${tab === 'findings' ? styles.tabActive : ''}`}
            onClick={() => setTab('findings')}
          >
            Findings
            {findingsData && <span className={styles.tabBadge}>{findingsData.total}</span>}
          </button>
          <button
            className={`${styles.tab} ${tab === 'scores' ? styles.tabActive : ''}`}
            onClick={() => setTab('scores')}
          >
            Repo Scores
          </button>
          <button
            className={`${styles.tab} ${tab === 'activity' ? styles.tabActive : ''}`}
            onClick={() => setTab('activity')}
          >
            Scanner Activity
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
              <ErrorBanner
                message="Failed to load findings"
                onRetry={() => void refetchFindings()}
              />
            )}
            {findingsData && findingsData.findings.length === 0 && (
              <div className={styles.emptyState}>
                <div className={styles.emptyIcon}>🔍</div>
                <div className={styles.emptyTitle}>No workflow findings yet</div>
                <div className={styles.emptyDesc}>
                  Click <strong>Analyze Events</strong> above to scan workflow audit log events. The
                  analyzer checks for self-hosted runners, excessive secrets, PR-triggered
                  workflows, public repo risks, and PAT-triggered automation.
                </div>
              </div>
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
                    <tr
                      key={f.id}
                      className={`${styles.findingRow} ${selectedFinding?.id === f.id ? styles.findingRowSelected : ''}`}
                      onClick={() => setSelectedFinding(selectedFinding?.id === f.id ? null : f)}
                    >
                      <td>
                        <Label
                          variant={sevVariant(f.severity)}
                          onClick={() => setSevFilter(f.severity)}
                        >
                          {f.severity}
                        </Label>
                      </td>
                      <td>{f.title}</td>
                      <td className={styles.repoPath}>
                        {f.org}/{f.repo}
                      </td>
                      <td className={styles.repoPath}>{f.workflow_path}</td>
                      <td>
                        <Label
                          variant={f.status === 'open' ? 'attention' : 'muted'}
                          onClick={() => setStatusFilter(f.status)}
                        >
                          {f.status}
                        </Label>
                      </td>
                      <td className={styles.timeCell}>{formatRelativeShort(f.last_seen)}</td>
                    </tr>
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
              <div className={styles.emptyState}>
                <div className={styles.emptyIcon}>📊</div>
                <div className={styles.emptyTitle}>No repository scores available</div>
                <div className={styles.emptyDesc}>
                  Run a scan first to generate security scores for your repositories.
                </div>
              </div>
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

        {tab === 'activity' && <ScannerActivityTab />}
      </div>

      {/* Detail slide-out panel */}
      <div
        className={[styles.splitPanel, selectedFinding && styles.splitPanelOpen]
          .filter(Boolean)
          .join(' ')}
      >
        {selectedFinding && (
          <>
            <div className={styles.panelHeader}>
              <div className={styles.panelTitle}>{selectedFinding.title}</div>
              <button className={styles.panelClose} onClick={() => setSelectedFinding(null)}>
                &#215;
              </button>
            </div>
            <div className={styles.panelBody}>
              <div className={styles.panelMeta}>
                <Label variant={sevVariant(selectedFinding.severity)}>
                  {selectedFinding.severity}
                </Label>
                <Label variant="muted">{selectedFinding.rule_id}</Label>
              </div>

              <div className={styles.panelSection}>
                <div className={styles.panelSectionTitle}>Description</div>
                <p className={styles.panelText}>{selectedFinding.description}</p>
              </div>

              <div className={styles.panelSection}>
                <div className={styles.panelSectionTitle}>Location</div>
                <div className={styles.panelKv}>
                  <span className={styles.panelLabel}>Repository</span>
                  <span>
                    {selectedFinding.org}/{selectedFinding.repo}
                  </span>
                </div>
                <div className={styles.panelKv}>
                  <span className={styles.panelLabel}>Workflow</span>
                  <code>{selectedFinding.workflow_path}</code>
                </div>
              </div>

              {selectedFinding.snippet && (
                <div className={styles.panelSection}>
                  <div className={styles.panelSectionTitle}>Code Snippet</div>
                  <pre className={styles.codeBlock}>{selectedFinding.snippet}</pre>
                </div>
              )}

              {selectedFinding.recommendation && (
                <div className={styles.panelSection}>
                  <div className={styles.panelSectionTitle}>Recommendation</div>
                  <p className={styles.panelText}>{selectedFinding.recommendation}</p>
                </div>
              )}

              <div className={styles.panelSection}>
                <div className={styles.panelSectionTitle}>What to do</div>
                <ul className={styles.panelGuidance}>
                  <li>Review the workflow file in the repository</li>
                  <li>Apply the recommended fix or pin actions to SHA commits</li>
                  <li>Re-scan after fixing to verify the issue is resolved</li>
                </ul>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
