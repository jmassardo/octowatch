import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getActionsVolumeReport } from '../../api/reports';
import { listEvents } from '../../api/events';
import { getWorkflowHealth, getBranchProtection } from '../../api/healthSignals';
import { ContributionCalendar } from '../../components/charts/ContributionCalendar';
import { LineAreaChart } from '../../components/charts/LineAreaChart';
import { BarChart } from '../../components/charts/BarChart';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { Modal } from '../../components/primitives/Modal';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import type { ActionsVolumeBucket } from '../../types/reports';
import type { WorkflowRow } from '../../api/healthSignals';
import styles from './Velocity.module.css';

interface FailingWorkflow {
  readonly workflow: string;
  readonly repository: string;
  readonly failureRate: number;
  readonly lastFailed: string;
  readonly p50Duration: string;
}

interface ActiveRepo {
  readonly name: string;
  readonly commits: number;
  readonly prsMerged: number;
  readonly cfr: number;
  readonly mttr: string;
  readonly contributors: number;
}

const SAMPLE_FAILING_WORKFLOWS: readonly FailingWorkflow[] = [
  { workflow: 'deploy-production.yml', repository: 'acme/infra-deploy', failureRate: 60, lastFailed: '14 min ago', p50Duration: '4m 22s' },
  { workflow: 'e2e-tests.yml', repository: 'acme/checkout-service', failureRate: 28, lastFailed: '2h ago', p50Duration: '12m 08s' },
  { workflow: 'integration-tests.yml', repository: 'globex/auth-service', failureRate: 15, lastFailed: '5h ago', p50Duration: '8m 41s' },
];

const SAMPLE_ACTIVE_REPOS: readonly ActiveRepo[] = [
  { name: 'acme/payments-api', commits: 847, prsMerged: 214, cfr: 2.1, mttr: '38m', contributors: 28 },
  { name: 'acme/checkout-service', commits: 623, prsMerged: 187, cfr: 1.8, mttr: '22m', contributors: 19 },
  { name: 'acme/infra-deploy', commits: 412, prsMerged: 98, cfr: 14.3, mttr: '1h 12m', contributors: 12 },
  { name: 'globex/auth-service', commits: 318, prsMerged: 76, cfr: 6.2, mttr: '45m', contributors: 9 },
  { name: 'globex/api-gateway', commits: 275, prsMerged: 61, cfr: 0, mttr: '—', contributors: 8 },
];

function getFailureRateVariant(rate: number): 'danger' | 'attention' | 'success' {
  if (rate > 20) return 'danger';
  if (rate > 10) return 'attention';
  return 'success';
}

function getCfrVariant(cfr: number): 'danger' | 'attention' | 'success' {
  if (cfr > 10) return 'danger';
  if (cfr > 5) return 'attention';
  return 'success';
}

function WorkflowHealthSection({ workflows }: { workflows: WorkflowRow[] }) {
  const topFailing = [...workflows]
    .filter((wf) => wf.failure_rate_pct > 0)
    .sort((a, b) => b.failure_rate_pct - a.failure_rate_pct)
    .slice(0, 10);

  return (
    <div style={{ marginTop: 8 }}>
      <div className={styles.sectionTitle}>Workflow health — audit log signals</div>
      <div className={styles.tableWrap} style={{ marginBottom: 20 }}>
        <table>
          <thead>
            <tr>
              <th>Repository</th>
              <th>Workflow</th>
              <th>Total runs</th>
              <th>Failures</th>
              <th>Failure rate</th>
              <th>Last run</th>
            </tr>
          </thead>
          <tbody>
            {topFailing.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', color: 'var(--fg-muted)', padding: 24 }}>
                  No failing workflows detected
                </td>
              </tr>
            )}
            {topFailing.map((wf) => (
              <tr key={`${wf.repo}/${wf.workflow_name}`}>
                <td>{wf.repo}</td>
                <td className={styles.workflowName}>{wf.workflow_name}</td>
                <td style={{ fontVariantNumeric: 'tabular-nums' }}>{wf.total_runs}</td>
                <td style={{ fontVariantNumeric: 'tabular-nums' }}>{wf.failures}</td>
                <td>
                  <Label variant={getFailureRateVariant(wf.failure_rate_pct)}>
                    {wf.failure_rate_pct.toFixed(1)}%
                  </Label>
                </td>
                <td style={{ color: 'var(--fg-muted)' }}>
                  {new Date(wf.last_run).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                  })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface BranchProtectionProps {
  branchProt: {
    protections_removed: number;
    policy_overrides: number;
    modified: number;
    distinct_repos_affected: number;
  } | undefined;
}

function BranchProtectionSection({ branchProt }: BranchProtectionProps) {
  const total = branchProt
    ? branchProt.protections_removed + branchProt.policy_overrides + branchProt.modified
    : 0;

  return (
    <div style={{ marginTop: 8 }}>
      <div className={styles.sectionTitle}>Branch protection changes (30d)</div>
      <div className={styles.metricStrip} style={{ marginBottom: 12 }}>
        <MetricCard
          value={String(branchProt?.protections_removed ?? 0)}
          label="Protections removed"
        />
        <MetricCard
          value={String(branchProt?.policy_overrides ?? 0)}
          label="Policy overrides"
        />
        <MetricCard
          value={String(branchProt?.modified ?? 0)}
          label="Modified"
        />
        <MetricCard
          value={String(branchProt?.distinct_repos_affected ?? 0)}
          label="Repos affected"
        />
      </div>
      {total === 0 && (
        <div style={{ color: 'var(--fg-muted)', fontSize: 13, padding: '8px 0', marginBottom: 20 }}>
          No branch protection weakening events detected in the last 30 days.
        </div>
      )}
    </div>
  );
}

export function VelocityPage() {
  const navigate = useNavigate();
  const [doraModalOpen, setDoraModalOpen] = useState(false);
  const [failureBucket, setFailureBucket] = useState<ActionsVolumeBucket | null>(null);
  const changeFailureRef = useRef<HTMLDivElement>(null);
  const workflowSuccessRef = useRef<HTMLDivElement>(null);
  const dailyRunsRef = useRef<HTMLDivElement>(null);
  const reposRef = useRef<HTMLDivElement>(null);
  const calendarRef = useRef<HTMLDivElement>(null);
  const failuresRef = useRef<HTMLDivElement>(null);

  const { data: actionsData, isLoading, isError, refetch } = useQuery({
    queryKey: ['reports', 'actions-volume'],
    queryFn: () => getActionsVolumeReport({ window_days: 30, granularity: 'daily' }),
  });

  const { data: prEvents } = useQuery({
    queryKey: ['events', 'pr-events'],
    queryFn: () => listEvents({ action: 'pull_request', page_size: 500, sort: 'created_at_desc' }),
  });

  const { data: repoEvents } = useQuery({
    queryKey: ['events', 'velocity-repos'],
    queryFn: () => listEvents({ page_size: 500, sort: 'created_at_desc' }),
  });

  const { data: workflowHealthData } = useQuery({
    queryKey: ['health', 'workflows-velocity'],
    queryFn: getWorkflowHealth,
    staleTime: 60_000,
  });

  const { data: branchProtData } = useQuery({
    queryKey: ['health', 'branch-protection-velocity'],
    queryFn: getBranchProtection,
    staleTime: 60_000,
  });

  const buckets = (actionsData?.data ?? []) as unknown as ActionsVolumeBucket[];

  // Aggregate totals from actions volume data
  const totalRuns = buckets.reduce((sum, b) => sum + (b.workflow_runs_total ?? 0), 0);
  const totalSucceeded = buckets.reduce((sum, b) => sum + (b.workflow_runs_succeeded ?? 0), 0);
  const overallSuccessRate = totalRuns > 0 ? ((totalSucceeded / totalRuns) * 100).toFixed(1) : null;

  const totalFailed = buckets.reduce((sum, b) => sum + (b.workflow_runs_failed ?? 0), 0);
  const changeFailureRate = totalRuns > 0 ? ((totalFailed / totalRuns) * 100).toFixed(1) : null;

  const prMerged = prEvents?.total ?? null;

  // Derive chart data from API buckets
  const chartLabels = buckets.map((b) => {
    const d = new Date(b.bucket);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  });
  const workflowSuccessChartData = buckets.map((b) => b.success_rate_pct ?? 0);
  const changeFailureChartData = buckets.map((b) =>
    b.workflow_runs_total > 0
      ? Math.round((b.workflow_runs_failed / b.workflow_runs_total) * 1000) / 10
      : 0,
  );
  const dailyRunsChartData = buckets.map((b) => b.workflow_runs_total ?? 0);
  const chartDaysLabel = buckets.length > 0 ? `${buckets.length} days` : '—';

  // Derive active repos from events data
  const hasRealRepoData = (repoEvents?.items.length ?? 0) > 0;
  const realRepoNames = (() => {
    if (!hasRealRepoData) return [];
    const repoMap = new Map<string, { events: number; actors: Set<string> }>();
    for (const e of repoEvents!.items) {
      if (!e.repo) continue;
      const existing = repoMap.get(e.repo) ?? { events: 0, actors: new Set<string>() };
      existing.events++;
      if (e.actor) existing.actors.add(e.actor);
      repoMap.set(e.repo, existing);
    }
    return [...repoMap.entries()]
      .sort(([, a], [, b]) => b.events - a.events)
      .slice(0, 5)
      .map(([name]) => name);
  })();

  const metrics = [
    { value: prMerged != null ? prMerged.toLocaleString() : '—', label: 'PRs merged (30d)', delta: 'last 30 days', dir: 'neutral' as const, scrollRef: 'calendar' as const },
    { value: '—', label: 'Lead time for changes', delta: 'Requires GitHub API integration', dir: 'neutral' as const, scrollRef: null },
    { value: '—', label: 'PR cycle time (median)', delta: 'Requires GitHub API integration', dir: 'neutral' as const, scrollRef: null },
    { value: changeFailureRate != null ? `${changeFailureRate}%` : '—', label: 'Change failure rate', delta: changeFailureRate != null ? (parseFloat(changeFailureRate) < 5 ? '< 5% target ✓' : '≥ 5% target') : '—', dir: changeFailureRate != null && parseFloat(changeFailureRate) < 5 ? 'up' as const : 'down' as const, scrollRef: 'changeFailure' as const },
    { value: '—', label: 'Deployments (30d)', delta: 'Requires GitHub API integration', dir: 'neutral' as const, scrollRef: null },
    { value: overallSuccessRate != null ? `${overallSuccessRate}%` : '—', label: 'Workflow success', delta: '30-day average', dir: overallSuccessRate != null && parseFloat(overallSuccessRate) >= 90 ? 'up' as const : 'down' as const, scrollRef: 'workflowSuccess' as const },
    { value: '—', label: 'WIP (items in flight)', delta: 'Requires GitHub API integration', dir: 'neutral' as const, scrollRef: null },
    { value: '—', label: 'Planned work ratio', delta: 'Requires GitHub API integration', dir: 'neutral' as const, scrollRef: null },
  ];

  const refMap = {
    calendar: calendarRef,
    changeFailure: changeFailureRef,
    workflowSuccess: workflowSuccessRef,
    dailyRuns: dailyRunsRef,
    repos: reposRef,
    failures: failuresRef,
  } as const;

  // Most recent failing buckets (last 7 days of failed runs > 0)
  const recentFailingBuckets = buckets
    .filter((b) => (b.workflow_runs_failed ?? 0) > 0)
    .slice(-7)
    .reverse();

  return (
    <div className={styles.page}>
      <div className={styles.titleRow}>
        <div className={styles.pageTitle}>Engineering Velocity</div>
        <div className={styles.doraGroup}>
          <span className={styles.doraLabel}>DORA tier</span>
          <span
            className={[styles.doraBadge, styles.doraBadgeClickable].join(' ')}
            role="button"
            tabIndex={0}
            aria-label="DORA Elite tier — click for details"
            onClick={() => setDoraModalOpen(true)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setDoraModalOpen(true);
              }
            }}
          >
            ★ Elite
          </span>
        </div>
      </div>
      <div className={styles.pageSub}>
        Flow metrics, DORA indicators, and delivery throughput — use as conversation starters, not scorecards
      </div>

      <div className={styles.contextCard}>
        <svg width="14" height="14" fill="var(--accent)" viewBox="0 0 16 16" style={{ flexShrink: 0, marginTop: 1 }}>
          <path d="M0 8a8 8 0 1116 0A8 8 0 010 8zm8-6.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM6.5 7.75A.75.75 0 017.25 7h1a.75.75 0 01.75.75v2.75h.25a.75.75 0 010 1.5h-2a.75.75 0 010-1.5h.25v-2h-.25a.75.75 0 01-.75-.75zM8 6a1 1 0 110-2 1 1 0 010 2z" />
        </svg>
        <span>
          Metrics here measure <strong>system behavior</strong>, not individual performance. A metric moving in an
          unexpected direction is a question to investigate, not a judgment to make.
        </span>
      </div>

      {isError && <ErrorBanner message="Failed to load metrics" onRetry={refetch} />}

      <div className={styles.metricStrip}>
        {metrics.map((m, i) => (
          <MetricCard
            key={i}
            value={m.value}
            label={m.label}
            delta={m.delta}
            deltaDir={m.dir}
            onClick={m.scrollRef ? () => { refMap[m.scrollRef].current?.scrollIntoView({ behavior: 'smooth' }); } : undefined}
          />
        ))}
      </div>

      {isLoading && <Spinner />}

      <div ref={calendarRef}>
        <Card style={{ marginBottom: 20 }}>
          <CardHeader actions={<span style={{ fontWeight: 400 }}>commit + PR + deploy activity</span>}>
            Team contribution calendar — last 13 weeks
          </CardHeader>
          <ContributionCalendar />
        </Card>
      </div>

      <div className={styles.chartsGrid}>
        <div className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Lead time for changes <span className={styles.chartSub}>— requires integration</span>
          </div>
          <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-muted)', fontSize: 13 }}>
            No data available — requires GitHub deployment API integration
          </div>
        </div>

        <div ref={changeFailureRef} className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Change failure rate <span className={styles.chartSub}>— {chartDaysLabel}</span>
          </div>
          {chartLabels.length > 0 ? (
            <LineAreaChart
              xAxisData={chartLabels}
              series={[
                { name: 'CFR', data: changeFailureChartData, color: 'rgb(248, 81, 73)', areaOpacity: 0.15 },
                { name: 'Threshold (5%)', data: Array.from({ length: chartLabels.length }, () => 5), color: 'rgb(248, 81, 73)', dashed: true },
              ]}
              yAxisFormatter={(v: number) => `${v}%`}
            />
          ) : (
            <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-muted)', fontSize: 13 }}>
              No workflow data available
            </div>
          )}
        </div>

        <div ref={workflowSuccessRef} className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Workflow success rate <span className={styles.chartSub}>— {chartDaysLabel}</span>
          </div>
          {chartLabels.length > 0 ? (
            <LineAreaChart
              xAxisData={chartLabels}
              series={[
                { name: 'Success rate', data: workflowSuccessChartData, color: 'rgb(63, 185, 80)', areaOpacity: 0.15 },
              ]}
              yAxisFormatter={(v: number) => `${v}%`}
            />
          ) : (
            <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-muted)', fontSize: 13 }}>
              No workflow data available
            </div>
          )}
        </div>

        <div ref={dailyRunsRef} className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Daily workflow runs <span className={styles.chartSub}>— {chartDaysLabel}</span>
          </div>
          {chartLabels.length > 0 ? (
            <BarChart
              xAxisData={chartLabels}
              series={[
                { name: 'Workflow runs', data: dailyRunsChartData, color: '#58a6ff' },
              ]}
            />
          ) : (
            <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-muted)', fontSize: 13 }}>
              No workflow data available
            </div>
          )}
        </div>
      </div>

      {recentFailingBuckets.length > 0 && (
        <div ref={failuresRef}>
          <div className={styles.sectionTitle}>Recent workflow failures — last 30 days</div>
          <div className={styles.tableWrap} style={{ marginBottom: 20 }}>
            <table>
              <thead><tr><th>Date bucket</th><th>Total runs</th><th>Failed</th><th>Success rate</th></tr></thead>
              <tbody>
                {recentFailingBuckets.map((b, i) => (
                  <tr
                    key={i}
                    className={styles.clickableRow}
                    role="button"
                    tabIndex={0}
                    aria-label={`Failure details for ${new Date(b.bucket).toLocaleDateString()}`}
                    onClick={() => setFailureBucket(b)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setFailureBucket(b);
                      }
                    }}
                  >
                    <td>{new Date(b.bucket).toLocaleDateString()}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{b.workflow_runs_total ?? 0}</td>
                    <td><Label variant={(b.workflow_runs_failed ?? 0) > 10 ? 'danger' : 'attention'}>{b.workflow_runs_failed ?? 0}</Label></td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{b.success_rate_pct != null ? `${Math.round(b.success_rate_pct)}%` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className={styles.sectionTitle}>Top failing workflows</div>
      <SampleDataBanner message="Top failing workflows display sample data. Per-workflow failure metrics require GitHub Actions API integration for individual run data." />
      <div className={styles.tableWrap} style={{ marginBottom: 20 }}>
        <table>
          <thead>
            <tr>
              <th>Workflow</th>
              <th>Repository</th>
              <th>Failure rate</th>
              <th>Last failed</th>
              <th>P50 duration</th>
            </tr>
          </thead>
          <tbody>
            {SAMPLE_FAILING_WORKFLOWS.map((wf) => (
              <tr key={`${wf.repository}/${wf.workflow}`}>
                <td className={styles.workflowName}>{wf.workflow}</td>
                <td>{wf.repository}</td>
                <td><Label variant={getFailureRateVariant(wf.failureRate)}>{wf.failureRate}%</Label></td>
                <td style={{ color: 'var(--fg-muted)' }}>{wf.lastFailed}</td>
                <td style={{ fontVariantNumeric: 'tabular-nums' }}>{wf.p50Duration}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div ref={reposRef} className={styles.sectionTitle}>Most active repositories — last 30 days</div>
      {!hasRealRepoData && (
        <SampleDataBanner message="Most active repositories display sample data. Commits, PRs merged, CFR, and MTTR require GitHub API integration." />
      )}
      <div className={styles.tableWrap} style={{ marginBottom: 20 }}>
        <table>
          <thead>
            <tr>
              <th>Repository</th>
              <th>Commits</th>
              <th>PRs merged</th>
              <th>Change failure rate</th>
              <th>MTTR</th>
              <th>Contributors</th>
            </tr>
          </thead>
          <tbody>
            {hasRealRepoData ? (
              realRepoNames.map((name) => (
                <tr
                  key={name}
                  className={styles.clickableRow}
                  role="button"
                  tabIndex={0}
                  aria-label={`View events for ${name}`}
                  onClick={() => navigate(`/events?repo=${encodeURIComponent(name)}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      navigate(`/events?repo=${encodeURIComponent(name)}`);
                    }
                  }}
                >
                  <td style={{ fontWeight: 500, color: 'var(--accent)', cursor: 'pointer' }}>{name}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>—</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>—</td>
                  <td>—</td>
                  <td>—</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>—</td>
                </tr>
              ))
            ) : SAMPLE_ACTIVE_REPOS.length > 0 ? (
              SAMPLE_ACTIVE_REPOS.map((r) => (
                <tr key={r.name}>
                  <td style={{ fontWeight: 500 }}>{r.name}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{r.commits.toLocaleString()}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{r.prsMerged}</td>
                  <td><Label variant={getCfrVariant(r.cfr)}>{r.cfr}%</Label></td>
                  <td>{r.mttr}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{r.contributors}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} style={{ color: 'var(--fg-muted)', textAlign: 'center' }}>
                  No repository activity data available
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {buckets.length === 0 && !isLoading && (
        <div style={{ color: 'var(--fg-muted)', padding: '16px 0' }}>No workflow run data for the selected period.</div>
      )}

      {/* Workflow Health from audit logs */}
      <WorkflowHealthSection workflows={workflowHealthData?.workflows ?? []} />

      {/* Branch Protection Changes */}
      <BranchProtectionSection branchProt={branchProtData} />

      <Modal open={doraModalOpen} onClose={() => setDoraModalOpen(false)} title="DORA Metrics — Elite Tier" width={520}>
        <p style={{ fontSize: 13, color: 'var(--fg-muted)', marginBottom: 16, lineHeight: 1.5 }}>
          DORA (DevOps Research and Assessment) metrics measure software delivery performance.
          Teams are classified into four tiers based on their performance across four key metrics.
        </p>
        <table className={styles.doraTable}>
          <thead>
            <tr><th>Metric</th><th>Elite threshold</th><th>Current</th></tr>
          </thead>
          <tbody>
            <tr>
              <td style={{ fontWeight: 500 }}>Deployment Frequency</td>
              <td>On-demand (multiple deploys/day)</td>
              <td>—</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 500 }}>Lead Time for Changes</td>
              <td>&lt; 1 hour</td>
              <td>—</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 500 }}>Change Failure Rate</td>
              <td>&lt; 5%</td>
              <td>{changeFailureRate != null ? `${changeFailureRate}%` : '—'}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 500 }}>Time to Restore Service</td>
              <td>&lt; 1 hour</td>
              <td>—</td>
            </tr>
          </tbody>
        </table>
        <p style={{ fontSize: 12, color: 'var(--fg-subtle)', marginTop: 12, lineHeight: 1.5 }}>
          Tier is currently set to Elite as a default. Full DORA calculation requires deployment and incident tracking integrations.
        </p>
      </Modal>

      <Modal
        open={failureBucket !== null}
        onClose={() => setFailureBucket(null)}
        title={`Workflow failures — ${failureBucket ? new Date(failureBucket.bucket).toLocaleDateString() : ''}`}
        width={560}
      >
        {failureBucket && (
          <div>
            <div className={styles.modalMetrics}>
              <div className={styles.modalMetric}>
                <div className={styles.modalMetricVal}>{failureBucket.workflow_runs_total}</div>
                <div className={styles.modalMetricLbl}>Total runs</div>
              </div>
              <div className={styles.modalMetric}>
                <div className={styles.modalMetricVal} style={{ color: 'var(--success)' }}>{failureBucket.workflow_runs_succeeded}</div>
                <div className={styles.modalMetricLbl}>Succeeded</div>
              </div>
              <div className={styles.modalMetric}>
                <div className={styles.modalMetricVal} style={{ color: 'var(--danger)' }}>{failureBucket.workflow_runs_failed}</div>
                <div className={styles.modalMetricLbl}>Failed</div>
              </div>
              <div className={styles.modalMetric}>
                <div className={styles.modalMetricVal}>{failureBucket.success_rate_pct != null ? `${Math.round(failureBucket.success_rate_pct)}%` : '—'}</div>
                <div className={styles.modalMetricLbl}>Success rate</div>
              </div>
            </div>
            <p style={{ fontSize: 13, color: 'var(--fg-muted)', marginTop: 16, lineHeight: 1.5 }}>
              Date bucket: <strong>{new Date(failureBucket.bucket).toLocaleDateString()}</strong><br />
              Unique workflows: <strong>{failureBucket.unique_workflows}</strong>
            </p>
            <p style={{ fontSize: 12, color: 'var(--fg-subtle)', marginTop: 12, lineHeight: 1.5 }}>
              Workflow-level failure details require GitHub Actions API integration for individual run data.
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
}
