import { Card } from '../../components/primitives/Card';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { WAF_FINDINGS, PILLAR_META, type WafPillar } from './healthData';
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

interface PillarSummary {
  total: number;
  critical: number;
  warning: number;
  summaryText: string;
}

function computePillarSummaries(): Record<WafPillar, PillarSummary> {
  const summaries = {} as Record<WafPillar, PillarSummary>;
  for (const pillar of PILLAR_ORDER) {
    const evaluated = WAF_FINDINGS.filter((f) => f.pillar === pillar && f.evaluated);
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

export function WafInsightsPane() {
  const pillarSummaries = computePillarSummaries();
  const evaluatedFindings = WAF_FINDINGS.filter((f) => f.evaluated);
  const unevaluatedFindings = WAF_FINDINGS.filter((f) => !f.evaluated);

  // Group evaluated findings by pillar
  const findingsByPillar: Record<WafPillar, typeof evaluatedFindings> = {
    governance: [],
    appsec: [],
    architecture: [],
    collaboration: [],
    productivity: [],
  };
  for (const f of evaluatedFindings) {
    findingsByPillar[f.pillar].push(f);
  }

  return (
    <>
      <SampleDataBanner message="WAF alignment signals are derived from audit log events and baseline imports. Some signals require active API polling and cannot be evaluated — see gaps below." />

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
            only surfaces what is detectable from audit log events or a baseline import. Findings
            marked{' '}
            <span className={styles.wafNa}>API only</span> cannot be evaluated without active
            polling and are shown as informational gaps.
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
              className={styles.pillarCard}
              style={{ borderColor: PILLAR_BORDER_COLOR[pillar] }}
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
        if (findings.length === 0 && pillar !== 'productivity') return null;
        const meta = PILLAR_META[pillar];

        return (
          <div key={pillar}>
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

            {pillar === 'productivity' && findings.length === 0 && (
              <div className={styles.productivityOk}>
                <strong style={{ color: 'var(--success)' }}>✓ No productivity anti-patterns detected</strong>
                {' — '}Copilot adoption is active (see Copilot Insights), CI pipelines are running,
                and automated deployment is in place.
              </div>
            )}

            {findings.map((f) => {
              const isCritical = f.severity === 'critical';
              const findingClass = isCritical
                ? styles.wafFindingCritical
                : styles.wafFindingWarning;

              return (
                <div key={f.id} className={`${styles.wafFinding} ${findingClass}`}>
                  <div className={styles.wafFindingHeader}>
                    <div
                      className={`${styles.sevDot} ${isCritical ? styles.sevDotCritical : styles.sevDotWarning}`}
                    />
                    <div className={styles.wafFindingTitle}>{f.finding}</div>
                    <PillarTag pillar={f.pillar} />
                  </div>
                  {f.detail && <div className={styles.wafFindingBody}>{f.detail}</div>}
                  <div className={styles.wafFindingMeta}>
                    {f.evidence.split(',').map((src) => {
                      const trimmed = src.trim();
                      // Distinguish between event sources and descriptive text
                      if (trimmed.includes('—') || trimmed.includes('absence') || trimmed.includes('missing')) {
                        return (
                          <span key={trimmed} style={{ color: 'var(--fg-subtle)', fontSize: 11 }}>
                            {trimmed}
                          </span>
                        );
                      }
                      return (
                        <span key={trimmed} className={styles.wafSource}>
                          {trimmed}
                        </span>
                      );
                    })}
                    <a
                      href={f.wafRef.url}
                      target="_blank"
                      rel="noopener"
                      className={styles.wafRef}
                    >
                      {f.wafRef.label} ↗
                    </a>
                  </div>
                </div>
              );
            })}
          </div>
        );
      })}

      {/* Unevaluated signals */}
      {unevaluatedFindings.length > 0 && (
        <div className={styles.unevaluatedSection}>
          <div className={styles.unevaluatedTitle}>
            <span style={{ color: 'var(--fg-subtle)' }}>▢</span>
            <span>Signals that require active API polling (not evaluated)</span>
          </div>
          <div className={styles.tableWrap} style={{ marginBottom: 8 }}>
            <table>
              <thead>
                <tr>
                  <th>Signal</th>
                  <th>Pillar</th>
                  <th>Why not available</th>
                  <th>WAF Reference</th>
                </tr>
              </thead>
              <tbody>
                {unevaluatedFindings.map((f) => (
                  <tr key={f.id}>
                    <td>{f.finding}</td>
                    <td>
                      <PillarTag pillar={f.pillar} />
                    </td>
                    <td style={{ color: 'var(--fg-muted)', fontSize: 12 }}>{f.evidence}</td>
                    <td>
                      <a
                        href={f.wafRef.url}
                        target="_blank"
                        rel="noopener"
                        className={styles.wafRef}
                        style={{ fontSize: 12 }}
                      >
                        {f.wafRef.label} ↗
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className={styles.wafBaselineNote}>
            ℹ To evaluate these signals, perform a one-time baseline import from{' '}
            <strong>Settings → Integrations → Baseline Import</strong>. Continuous polling of
            GitHub APIs is not supported by design.
          </div>
        </div>
      )}
    </>
  );
}
