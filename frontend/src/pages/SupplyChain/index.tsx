import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import {
  getSupplyChainPosture,
  getSupplyChainRisks,
  getSupplyChainRules,
  analyzeWorkflow,
} from '../../api/supplyChain';
import type {
  SupplyChainPosture,
  RiskSummary,
  RulesListResponse,
  AnalyzeWorkflowResponse,
  WorkflowFinding,
} from '../../api/supplyChain';
import styles from './SupplyChain.module.css';

type TabKey = 'risks' | 'rules' | 'workflow';

/* ── Severity badge ─────────────────────────────────────────────────────── */

function SeverityBadge({ severity }: { severity: string }) {
  const key = severity.toLowerCase();
  const cls =
    key === 'critical'
      ? styles.critical
      : key === 'high'
        ? styles.high
        : key === 'medium'
          ? styles.medium
          : key === 'low'
            ? styles.low
            : styles.none;
  return <span className={`${styles.badge} ${cls}`}>{severity}</span>;
}

/* ── Risks tab ──────────────────────────────────────────────────────────── */

function RisksTab({
  posture,
  risks,
}: {
  posture: SupplyChainPosture | undefined;
  risks: RiskSummary | undefined;
}) {
  const recentRisks = posture?.recent_risks ?? [];
  const topRepos = risks?.top_repos ?? [];

  return (
    <div>
      {recentRisks.length === 0 ? (
        <div className={styles.emptyState}>No supply chain risks detected yet.</div>
      ) : (
        <>
          <div className={styles.sectionTitle}>Recent detections</div>
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Title</th>
                  <th scope="col">Severity</th>
                  <th scope="col">Status</th>
                  <th scope="col">Repo</th>
                  <th scope="col">Type</th>
                  <th scope="col">Detected</th>
                </tr>
              </thead>
              <tbody>
                {recentRisks.map((risk) => (
                  <tr key={risk.id}>
                    <td>{risk.title}</td>
                    <td>
                      <SeverityBadge severity={risk.severity} />
                    </td>
                    <td>{risk.status}</td>
                    <td>{risk.repo ?? '—'}</td>
                    <td>{risk.rule_slug}</td>
                    <td>
                      {risk.triggered_at ? new Date(risk.triggered_at).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {topRepos.length > 0 && (
        <>
          <div className={styles.sectionTitle} style={{ marginTop: 24 }}>
            Top repos by risk count
          </div>
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Repository</th>
                  <th scope="col">Risks</th>
                </tr>
              </thead>
              <tbody>
                {topRepos.map((r) => (
                  <tr key={r.repo}>
                    <td>{r.repo}</td>
                    <td>{r.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

/* ── Rules tab ──────────────────────────────────────────────────────────── */

function RulesTab({ data }: { data: RulesListResponse | undefined }) {
  const rules = data?.rules ?? [];
  if (rules.length === 0) {
    return <div className={styles.emptyState}>No supply chain rules configured.</div>;
  }

  return (
    <div className={styles.tableWrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Rule</th>
            <th scope="col">Severity</th>
            <th scope="col">Confidence</th>
            <th scope="col">Type</th>
            <th scope="col">Detections</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => (
            <tr key={rule.id}>
              <td>
                <strong>{rule.name}</strong>
                {rule.description && (
                  <div style={{ fontSize: 11, color: 'var(--fg-muted)' }}>{rule.description}</div>
                )}
              </td>
              <td>
                <SeverityBadge severity={rule.severity} />
              </td>
              <td>{rule.confidence}</td>
              <td>{rule.logic_type}</td>
              <td>{rule.detection_count}</td>
              <td>
                <span className={`${styles.badge} ${rule.enabled ? styles.low : styles.none}`}>
                  {rule.enabled ? 'Active' : 'Disabled'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Workflow audit tab ─────────────────────────────────────────────────── */

function WorkflowAuditTab() {
  const [content, setContent] = useState('');
  const mutation = useMutation({
    mutationFn: (yaml: string) => analyzeWorkflow(yaml),
  });

  const handleAnalyze = () => {
    if (content.trim()) {
      mutation.mutate(content);
    }
  };

  const result: AnalyzeWorkflowResponse | undefined = mutation.data;

  return (
    <div>
      <div className={styles.sectionTitle}>Analyse workflow file</div>
      <div className={styles.sectionSub}>
        Paste a GitHub Actions workflow YAML to scan for supply chain risks.
      </div>
      <textarea
        className={styles.workflowInput}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Paste your workflow YAML here..."
        aria-label="Workflow YAML content"
      />
      <button
        className={styles.analyzeBtn}
        onClick={handleAnalyze}
        disabled={!content.trim() || mutation.isPending}
      >
        {mutation.isPending ? 'Analysing…' : 'Analyse Workflow'}
      </button>

      {mutation.isError && (
        <ErrorBanner message="Failed to analyse workflow" onRetry={handleAnalyze} />
      )}

      {result && (
        <div style={{ marginTop: 16 }}>
          <div className={styles.sectionTitle}>
            Results — <SeverityBadge severity={result.risk_level} /> ({result.total_findings}{' '}
            {result.total_findings === 1 ? 'finding' : 'findings'})
          </div>
          {result.findings.length === 0 ? (
            <div className={styles.emptyState}>No supply chain risks found. Looking good!</div>
          ) : (
            result.findings.map((f: WorkflowFinding, i: number) => (
              <div key={i} className={styles.findingCard}>
                <div className={styles.findingHeader}>
                  <SeverityBadge severity={f.severity} />
                  <strong>{f.title}</strong>
                  {f.line != null && <span style={{ fontSize: 11 }}>Line {f.line}</span>}
                </div>
                <div className={styles.findingDetail}>{f.detail}</div>
                <div className={styles.findingRecommendation}>💡 {f.recommendation}</div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

/* ── Main page ──────────────────────────────────────────────────────────── */

export function SupplyChainPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('risks');

  const postureQuery = useQuery({
    queryKey: ['supply-chain', 'posture'],
    queryFn: getSupplyChainPosture,
    staleTime: 60_000,
  });

  const risksQuery = useQuery({
    queryKey: ['supply-chain', 'risks'],
    queryFn: getSupplyChainRisks,
    staleTime: 60_000,
  });

  const rulesQuery = useQuery({
    queryKey: ['supply-chain', 'rules'],
    queryFn: getSupplyChainRules,
    staleTime: 60_000,
  });

  const isLoading = postureQuery.isLoading || risksQuery.isLoading || rulesQuery.isLoading;
  const isError = postureQuery.isError || risksQuery.isError || rulesQuery.isError;

  if (isLoading) {
    return (
      <div className={styles.centered}>
        <Spinner size={28} />
      </div>
    );
  }

  if (isError) {
    const retryAll = () => {
      void postureQuery.refetch();
      void risksQuery.refetch();
      void rulesQuery.refetch();
    };
    return <ErrorBanner message="Failed to load supply chain data" onRetry={retryAll} />;
  }

  const posture = postureQuery.data;

  return (
    <div className={styles.page}>
      <h2>Supply Chain Security</h2>

      {/* ── Summary strip ────────────────────────────────────────────── */}
      <div className={styles.metricGrid}>
        <MetricCard
          value={String(posture?.score ?? 0)}
          label="Supply Chain Score"
          accent={posture != null && posture.score < 70}
          helpText="Overall supply chain health score (0-100). Deductions for unpinned actions, risky workflows, and detections."
        />
        <MetricCard
          value={String(posture?.unpinned_actions ?? 0)}
          label="Unpinned Actions"
          accent={posture != null && posture.unpinned_actions > 0}
          helpText="GitHub Actions referenced by tag/branch instead of commit SHA, making them vulnerable to tag-rewriting attacks."
        />
        <MetricCard
          value={String(posture?.dependency_alerts ?? 0)}
          label="Dependency Alerts"
          helpText="Dependabot-related events across monitored organisations."
        />
        <MetricCard
          value={String(posture?.risky_workflows ?? 0)}
          label="Risky Workflows"
          accent={posture != null && posture.risky_workflows > 0}
          helpText="Workflows using pull_request_target without proper restrictions."
        />
        <MetricCard
          value={String(posture?.rules_active ?? 0)}
          label="Rules Active"
          helpText="Number of enabled supply chain detection rules."
        />
      </div>

      {/* ── Tabs ─────────────────────────────────────────────────────── */}
      <div className={styles.tabs} role="tablist">
        {(['risks', 'rules', 'workflow'] as const).map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={activeTab === tab}
            className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === 'risks' ? 'Risks' : tab === 'rules' ? 'Rules' : 'Workflow Audit'}
          </button>
        ))}
      </div>

      {/* ── Tab content ──────────────────────────────────────────────── */}
      {activeTab === 'risks' && <RisksTab posture={posture} risks={risksQuery.data} />}
      {activeTab === 'rules' && <RulesTab data={rulesQuery.data} />}
      {activeTab === 'workflow' && <WorkflowAuditTab />}
    </div>
  );
}
