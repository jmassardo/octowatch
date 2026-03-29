import { useQuery } from '@tanstack/react-query';
import { useState, useCallback } from 'react';
import { Card } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { getWafFindings } from '../../api/healthSignals';
import type { WafFindingResponse } from '../../api/healthSignals';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { PILLAR_META, type WafPillar } from './healthData';
import styles from './WafInsightsPane.module.css';

/** Pillar style class map. */
const PILLAR_CLASS: Record<WafPillar, string> = {
  governance: styles.pillarGovernance,
  appsec: styles.pillarAppsec,
  architecture: styles.pillarArchitecture,
  collaboration: styles.pillarCollaboration,
  productivity: styles.pillarProductivity,
};

/** Pillar color for card borders. */
const PILLAR_BORDER_COLOR: Record<WafPillar, string> = {
  governance: 'rgba(210, 153, 34, 0.4)',
  appsec: 'rgba(248, 81, 73, 0.4)',
  architecture: 'rgba(219, 109, 40, 0.4)',
  collaboration: 'rgba(188, 140, 255, 0.35)',
  productivity: 'transparent',
};

/** Pillar count color. */
const PILLAR_COUNT_COLOR: Record<WafPillar, string> = {
  governance: 'var(--attention)',
  appsec: 'var(--danger)',
  architecture: 'var(--severe)',
  collaboration: 'var(--done)',
  productivity: 'var(--fg-muted)',
};

const PILLAR_ORDER: WafPillar[] = ['governance', 'appsec', 'architecture', 'collaboration', 'productivity'];

/** Catalog of all WAF checks evaluated by OctoWatch. */
const WAF_CHECKS: { id: string; pillar: WafPillar; name: string; description: string; lookback: string }[] = [
  { id: 'waf-audit-streaming', pillar: 'governance', name: 'Audit log streaming', description: 'Checks for audit log streaming configuration events, indicating real-time event forwarding is active.', lookback: '30 days' },
  { id: 'waf-branch-protection', pillar: 'governance', name: 'Branch protection coverage', description: 'Compares branch protection creations vs. removals/overrides to detect weakening of code review requirements.', lookback: '90 days' },
  { id: 'waf-sso-status', pillar: 'governance', name: 'SAML / SSO enforcement', description: 'Monitors for SSO disable events and tracks whether SAML/SSO is actively configured across organizations.', lookback: '90 days' },
  { id: 'waf-ip-allowlist', pillar: 'governance', name: 'IP allowlist configuration', description: 'Detects IP allowlist management events to verify network-level access restrictions are in place.', lookback: '90 days' },
  { id: 'waf-webhook-health', pillar: 'governance', name: 'Webhook lifecycle management', description: 'Tracks webhook creation vs. destruction to identify integration instability or orphaned hooks.', lookback: '90 days' },
  { id: 'waf-push-protection-bypass', pillar: 'governance', name: 'Push protection bypasses', description: 'Counts instances where developers bypassed secret scanning push protection, overriding security controls.', lookback: '90 days' },
  { id: 'waf-workflow-permissions', pillar: 'governance', name: 'Workflow permissions changes', description: 'Detects changes to default workflow permissions that may loosen security controls.', lookback: '90 days' },
  { id: 'waf-self-approve-pr', pillar: 'governance', name: 'Workflow self-approval of PRs', description: 'Monitors for changes to workflow PR self-approval settings that could weaken code review enforcement.', lookback: '90 days' },
  { id: 'waf-deploy-key-policy', pillar: 'governance', name: 'Deploy key policy status', description: 'Checks for deploy key policy disable events that may allow uncontrolled repository access.', lookback: '90 days' },
  { id: 'waf-environment-protection', pillar: 'governance', name: 'Environment protection rules', description: 'Tracks environment protection rule additions to verify deployment approval gates are in place.', lookback: '90 days' },
  { id: 'waf-admin-escalation', pillar: 'governance', name: 'Admin privilege escalation', description: 'Detects admin promotions that should be rare and approved through proper channels.', lookback: '90 days' },
  { id: 'waf-secret-scanning', pillar: 'appsec', name: 'Secret scanning enablement', description: 'Tracks repositories enabling or disabling secret scanning to identify coverage gaps.', lookback: '90 days' },
  { id: 'waf-dependabot', pillar: 'appsec', name: 'Dependabot alert coverage', description: 'Monitors Dependabot alert enablement/disablement across repositories for supply chain security.', lookback: '90 days' },
  { id: 'waf-code-scanning', pillar: 'appsec', name: 'Code scanning activity', description: 'Checks for CodeQL or third-party SAST tool activity to verify static analysis is running.', lookback: '90 days' },
  { id: 'waf-direct-push', pillar: 'appsec', name: 'Direct pushes to default branch', description: 'Counts direct pushes to main/master branches that bypass the pull request review workflow.', lookback: '90 days' },
  { id: 'waf-actions-secrets', pillar: 'appsec', name: 'Actions secrets created', description: 'Reports on Actions secret creation events to track credential management activity.', lookback: '90 days' },
  { id: 'waf-vuln-alert-dismissed', pillar: 'appsec', name: 'Vulnerability alerts dismissed', description: 'Detects dismissed or withdrawn vulnerability alerts that may represent unaddressed security risks.', lookback: '90 days' },
  { id: 'waf-clone-anomaly', pillar: 'appsec', name: 'Clone activity anomaly detection', description: 'Identifies actors with clone counts exceeding 3× the average, which may indicate data exfiltration.', lookback: '30 days' },
  { id: 'waf-pr-merge-ratio', pillar: 'collaboration', name: 'Pull request merge ratio', description: 'Compares PR merge count to creation count to detect anomalies in the review workflow.', lookback: '90 days' },
  { id: 'waf-workflow-failure-rate', pillar: 'productivity', name: 'Workflow failure rate', description: 'Measures the percentage of failed workflow runs to identify CI/CD reliability issues.', lookback: '30 days' },
  { id: 'waf-workflow-rerun-rate', pillar: 'productivity', name: 'Workflow rerun rate', description: 'Tracks the ratio of workflow reruns to total runs, indicating flaky or unreliable workflows.', lookback: '30 days' },
];

function WafChecksCatalog() {
  const [open, setOpen] = useState(false);
  const byPillar = PILLAR_ORDER.reduce<Record<WafPillar, typeof WAF_CHECKS>>((acc, p) => {
    acc[p] = WAF_CHECKS.filter((c) => c.pillar === p);
    return acc;
  }, {} as Record<WafPillar, typeof WAF_CHECKS>);

  return (
    <div className={styles.catalogWrapper}>
      <button
        className={styles.catalogToggle}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="currentColor"
          style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.15s' }}
        >
          <path d="M4.5 2L9 6 4.5 10V2z" />
        </svg>
        <span>What we check</span>
        <span className={styles.catalogCount}>{WAF_CHECKS.length} signals</span>
      </button>
      {open && (
        <div className={styles.catalogBody}>
          {PILLAR_ORDER.map((pillar) => {
            const checks = byPillar[pillar];
            if (checks.length === 0) return null;
            const meta = PILLAR_META[pillar];
            return (
              <div key={pillar} className={styles.catalogPillar}>
                <div className={styles.catalogPillarLabel}>{meta.emoji} {meta.label}</div>
                {checks.map((c) => (
                  <div key={c.id} className={styles.catalogCheck}>
                    <div className={styles.catalogCheckName}>{c.name}</div>
                    <div className={styles.catalogCheckDesc}>{c.description}</div>
                    <span className={styles.catalogLookback}>Lookback: {c.lookback}</span>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Map backend pillar names to WafPillar type. */
function toPillar(raw: string): WafPillar {
  const mapping: Record<string, WafPillar> = {
    governance: 'governance',
    appsec: 'appsec',
    security: 'appsec',
    architecture: 'architecture',
    collaboration: 'collaboration',
    productivity: 'productivity',
  };
  return mapping[raw] ?? 'governance';
}

interface PillarSummary {
  total: number;
  critical: number;
  warning: number;
  summaryText: string;
}

function computePillarSummaries(findings: WafFindingResponse[]): Record<WafPillar, PillarSummary> {
  const summaries = {} as Record<WafPillar, PillarSummary>;
  for (const pillar of PILLAR_ORDER) {
    const evaluated = findings.filter((f) => toPillar(f.pillar) === pillar && f.evaluated);
    const critical = evaluated.filter((f) => f.severity === 'critical').length;
    const warning = evaluated.filter((f) => f.severity === 'warning').length;
    const total = critical + warning;
    let summaryText: string;
    if (total === 0) {
      summaryText = 'no issues detected';
    } else {
      const parts: string[] = [];
      if (critical > 0) parts.push(`${critical} critical`);
      if (warning > 0) parts.push(`${warning} warn`);
      summaryText = parts.join(' · ');
    }
    summaries[pillar] = { total, critical, warning, summaryText };
  }
  return summaries;
}

function PillarTag({ pillar }: { pillar: WafPillar }) {
  const meta = PILLAR_META[pillar];
  return (
    <span className={`${styles.pillarTag} ${PILLAR_CLASS[pillar]}`}>
      {meta.emoji} {meta.label}
    </span>
  );
}

/** Render a table of evidence items for an expanded finding. */
function EvidenceTable({ evidence }: { evidence: Record<string, unknown>[] }) {
  if (evidence.length === 0) return null;
  const columns = Object.keys(evidence[0]);
  return (
    <div className={styles.evidenceTable}>
      <table>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col}>{col.replace(/_/g, ' ')}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {evidence.map((row, i) => (
            <tr key={i}>
              {columns.map((col) => (
                <td key={col}>{String(row[col] ?? '—')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function WafInsightsPane() {
  const {
    data: wafData,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['health', 'waf-findings'],
    queryFn: getWafFindings,
    staleTime: 60_000,
  });

  const [expandedFindings, setExpandedFindings] = useState<Set<string>>(new Set());

  const toggleFinding = useCallback((id: string) => {
    setExpandedFindings((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const scrollToPillar = useCallback((pillar: WafPillar) => {
    const el = document.getElementById(`pillar-${pillar}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, []);

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spinner size={28} />
      </div>
    );
  }

  if (isError) {
    return <ErrorBanner message="Failed to load WAF findings" onRetry={() => void refetch()} />;
  }

  const allFindings = wafData?.findings ?? [];
  const isSampleData = allFindings.length === 0;
  const pillarSummaries = computePillarSummaries(allFindings);
  const evaluatedFindings = allFindings.filter((f) => f.evaluated);

  // Group evaluated findings by pillar
  const findingsByPillar: Record<WafPillar, WafFindingResponse[]> = {
    governance: [],
    appsec: [],
    architecture: [],
    collaboration: [],
    productivity: [],
  };
  for (const f of evaluatedFindings) {
    findingsByPillar[toPillar(f.pillar)].push(f);
  }

  return (
    <>
      {isSampleData && (
        <SampleDataBanner message="This data is illustrative. Connect your GitHub organization to see real WAF insights." />
      )}
      {/* Header with WAF note */}
      <div className={styles.wafHeader}>
        <div className={`${styles.dataSourceNote} ${styles.wafHeaderNote}`} style={{ marginBottom: 0 }}>
          <svg
            width="14"
            height="14"
            fill="var(--accent)"
            viewBox="0 0 16 16"
            aria-hidden="true"
            style={{ flexShrink: 0, marginTop: 1 }}
          >
            <path d="M0 8a8 8 0 1116 0A8 8 0 010 8zm8-6.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM6.5 7.75A.75.75 0 017.25 7h1a.75.75 0 01.75.75v2.75h.25a.75.75 0 010 1.5h-2a.75.75 0 010-1.5h.25v-2h-.25a.75.75 0 01-.75-.75zM8 6a1 1 0 110-2 1 1 0 010 2z" />
          </svg>
          <span>
            Signals are aligned to the{' '}
            <strong>GitHub Well-Architected Framework</strong> (5 pillars: Governance, Application
            Security, Architecture, Collaboration, Productivity). Coverage is partial — OctoWatch
            evaluates signals detectable from audit log events.
          </span>
        </div>
        <a
          href="https://wellarchitected.github.com/library/scenarios/anti-patterns/"
          target="_blank"
          rel="noopener"
          className={styles.wafRef}
          style={{ flexShrink: 0, whiteSpace: 'nowrap', padding: '6px 12px' }}
        >
          WAF Library ↗
        </a>
      </div>

      {/* Pillar summary strip */}
      <div className={styles.pillarGrid}>
        {PILLAR_ORDER.map((pillar) => {
          const meta = PILLAR_META[pillar];
          const summary = pillarSummaries[pillar];
          return (
            <Card
              key={pillar}
              className={`${styles.pillarCard} ${styles.pillarCardClickable}`}
              style={{ borderColor: PILLAR_BORDER_COLOR[pillar] }}
              onClick={() => scrollToPillar(pillar)}
            >
              <div className={styles.pillarLabel} style={{ color: PILLAR_COUNT_COLOR[pillar] }}>
                {meta.emoji} {meta.label}
              </div>
              <div className={styles.pillarCount} style={{ color: summary.total > 0 ? PILLAR_COUNT_COLOR[pillar] : 'var(--fg-muted)' }}>
                {summary.total}
              </div>
              <div className={styles.pillarSummary}>{summary.summaryText}</div>
            </Card>
          );
        })}
      </div>

      {/* Evaluated findings grouped by pillar */}
      {PILLAR_ORDER.map((pillar) => {
        const findings = findingsByPillar[pillar];
        const meta = PILLAR_META[pillar];

        return (
          <div key={pillar} id={`pillar-${pillar}`}>
            <div className={styles.pillarSectionTitle}>
              <PillarTag pillar={pillar} />
              <span className={styles.pillarSectionDesc}>{meta.description}</span>
              <a
                href={meta.url}
                target="_blank"
                rel="noopener"
                className={styles.wafRef}
              >
                View pillar ↗
              </a>
            </div>

            {findings.length === 0 && (
              <div className={styles.productivityOk}>
                <strong style={{ color: 'var(--success)' }}>✓ No {meta.label.toLowerCase()} anti-patterns detected</strong>
              </div>
            )}

            {findings.map((f) => {
              const isCritical = f.severity === 'critical';
              const isInfo = f.severity === 'info';
              const findingClass = isCritical
                ? styles.wafFindingCritical
                : isInfo
                  ? styles.wafFindingInfo ?? ''
                  : styles.wafFindingWarning;
              const isExpanded = expandedFindings.has(f.id);
              const hasEvidence = f.evidence && f.evidence.length > 0;

              return (
                <div
                  key={f.id}
                  className={`${styles.wafFinding} ${findingClass} ${styles.findingClickable} ${isExpanded ? styles.findingExpanded : styles.findingCollapsed}`}
                  onClick={() => toggleFinding(f.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleFinding(f.id); } }}
                >
                  <div className={styles.wafFindingHeader}>
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 12 12"
                      fill="currentColor"
                      className={`${styles.expandChevron} ${isExpanded ? styles.expandChevronOpen : ''}`}
                      aria-hidden="true"
                    >
                      <path d="M4.5 2L9 6 4.5 10V2z" />
                    </svg>
                    <div
                      className={`${styles.sevDot} ${
                        isCritical
                          ? styles.sevDotCritical
                          : isInfo
                            ? styles.sevDotInfo ?? styles.sevDotPass ?? ''
                            : styles.sevDotWarning
                      }`}
                    />
                    <div className={styles.wafFindingTitle}>{f.finding}</div>
                    <PillarTag pillar={toPillar(f.pillar)} />
                    {isInfo && (
                      <span style={{ color: 'var(--success)', fontSize: 11, fontWeight: 600, marginLeft: 'auto' }}>
                        ✓ PASS
                      </span>
                    )}
                  </div>
                  {isExpanded && (
                    <>
                      {f.detail && <div className={styles.wafFindingBody}>{f.detail}</div>}
                      {hasEvidence && <EvidenceTable evidence={f.evidence!} />}
                      <div className={styles.wafFindingMeta}>
                        <span style={{ color: 'var(--fg-subtle)', fontSize: 11 }}>
                          {f.evidence_count} event{f.evidence_count !== 1 ? 's' : ''} evaluated
                        </span>
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}

      {allFindings.length === 0 && (
        <div style={{ color: 'var(--fg-muted)', fontSize: 13, padding: 24, textAlign: 'center' }}>
          No WAF findings available. Ensure audit log events are being ingested.
        </div>
      )}

      {/* Catalog moved to bottom */}
      <WafChecksCatalog />
    </>
  );
}
