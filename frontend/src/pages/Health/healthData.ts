/** Static / sample data for Health sub-tabs. */

/* ---- License Health ---- */

export const COST_PER_SEAT_DEFAULT = 19;

export const LICENSE_SAMPLE = {
  totalSeats: 247,
  seatLimit: 300,
  utilizationPct: 82,
  ghostCount: 12,
  ghostMonthlyCost: 228,
  growthForecastDays: 74,
  growthRate: 3.2,
} as const;

export interface GhostMember {
  readonly member: string;
  readonly org: string;
  readonly role: string;
  readonly lastSeen: string;
  readonly daysInactive: number;
  readonly licensesHeld: string;
  readonly status: 'dormant' | 'stale & dormant';
}

export const GHOST_MEMBERS: readonly GhostMember[] = [
  { member: 'legacy-bot-1', org: 'acme-corp', role: 'member', lastSeen: 'Dec 14, 2025', daysInactive: 102, licensesHeld: 'GitHub', status: 'dormant' },
  { member: 'contractor-old', org: 'acme-corp', role: 'member', lastSeen: 'Nov 2, 2025', daysInactive: 144, licensesHeld: 'GitHub + Copilot', status: 'dormant' },
  { member: 'ex-intern-3', org: 'globex', role: 'member', lastSeen: 'Oct 18, 2025', daysInactive: 159, licensesHeld: 'GitHub', status: 'dormant' },
  { member: 'svc-old-deploy', org: 'acme-corp', role: 'member', lastSeen: 'Sep 1, 2025', daysInactive: 206, licensesHeld: 'GitHub', status: 'stale & dormant' },
];

export const COPILOT_CROSS_REF = {
  totalSeats: 200,
  inactiveSeats: 62,
} as const;

/* ---- Maintenance Signals ---- */

export interface StalePr {
  readonly repo: string;
  readonly number: number;
  readonly title: string;
  readonly daysOpen: number;
}

export const STALE_PRS: readonly StalePr[] = [
  { repo: 'acme/legacy-payments', number: 48, title: 'Update billing logic', daysOpen: 127 },
  { repo: 'globex/api-v1', number: 91, title: 'Migrate to v2 endpoints', daysOpen: 84 },
  { repo: 'acme/tools-old', number: 12, title: 'Dependency upgrades', daysOpen: 62 },
];

export interface UnhealthyWebhook {
  readonly name: string;
  readonly detail: string;
  readonly severity: 'danger' | 'attention' | 'muted';
}

export const UNHEALTHY_WEBHOOKS: readonly UnhealthyWebhook[] = [
  { name: 'Webhook → api.external-partner.io', detail: 'Non-org endpoint · returning 4xx for 14 days', severity: 'danger' },
  { name: 'GitHub App: "old-ci-bot"', detail: 'Scopes: admin:org, write:packages · last used 194 days ago', severity: 'attention' },
  { name: 'OAuth App: "legacy-deploy-tool"', detail: 'Broad repo scope · last activity 88 days ago', severity: 'muted' },
];

export interface SkippedWorkflow {
  readonly workflow: string;
  readonly repository: string;
  readonly status: 'disabled' | 'skipped';
  readonly lastRun: string;
  readonly consecutiveSkips: number | null;
}

export const SKIPPED_WORKFLOWS: readonly SkippedWorkflow[] = [
  { workflow: 'security-scan.yml', repository: 'acme/legacy-payments', status: 'disabled', lastRun: 'Feb 2, 2026', consecutiveSkips: null },
  { workflow: 'dependency-review.yml', repository: 'acme/tools-old', status: 'skipped', lastRun: 'Mar 1, 2026', consecutiveSkips: 18 },
  { workflow: 'codeql-analysis.yml', repository: 'globex/api-v1', status: 'skipped', lastRun: 'Feb 14, 2026', consecutiveSkips: 41 },
];

/* ---- WAF Insights ---- */

export type WafPillar = 'governance' | 'appsec' | 'architecture' | 'collaboration' | 'productivity';

export interface WafFinding {
  readonly id: string;
  readonly finding: string;
  readonly pillar: WafPillar;
  readonly pillarLabel: string;
  readonly pillarEmoji: string;
  readonly evaluated: boolean;
  readonly severity: 'critical' | 'warning' | 'info';
  readonly status?: 'pass' | 'fail' | 'warning';
  readonly evidence: string;
  readonly wafRef: { readonly label: string; readonly url: string };
  readonly detail?: string;
}

export const PILLAR_META: Record<WafPillar, { emoji: string; label: string; description: string; url: string }> = {
  governance: { emoji: '📜', label: 'Governance', description: 'Platform structure, policy enforcement, token hygiene', url: 'https://wellarchitected.github.com/library/governance/' },
  appsec: { emoji: '🔒', label: 'App Security', description: 'Signing, CODEOWNERS, ruleset bypass, supply chain', url: 'https://wellarchitected.github.com/library/application-security/' },
  architecture: { emoji: '📐', label: 'Architecture', description: 'Repo structure, reusability, runner topology', url: 'https://wellarchitected.github.com/library/architecture/' },
  collaboration: { emoji: '👥', label: 'Collaboration', description: 'Code review velocity, feedback cycles, PR hygiene', url: 'https://wellarchitected.github.com/library/collaboration/' },
  productivity: { emoji: '⚙️', label: 'Productivity', description: 'Automation, Copilot adoption, engineering metrics', url: 'https://wellarchitected.github.com/library/productivity/' },
};

export const WAF_FINDINGS: readonly WafFinding[] = [
  // Governance
  {
    id: 'gov-org-structure',
    finding: 'Fragmented organization structure — 2 orgs currently managed',
    pillar: 'governance',
    pillarLabel: 'Governance',
    pillarEmoji: '📜',
    evaluated: true,
    severity: 'critical',
    status: 'pass',
    evidence: 'org.delete + baseline import (org count)',
    detail: 'OctoWatch is monitoring 2 orgs (acme-corp, globex). The WAF flags enterprises with >10 orgs as fragmented.',
    wafRef: { label: 'WAF: Fragmented Org Structure', url: 'https://wellarchitected.github.com/library/scenarios/anti-patterns/#fragmented-organization-structure' },
  },
  {
    id: 'gov-push-bypass',
    finding: 'Push protection bypasses recorded — 4 events in last 90 days',
    pillar: 'governance',
    pillarLabel: 'Governance',
    pillarEmoji: '📜',
    evaluated: true,
    severity: 'critical',
    status: 'fail',
    evidence: 'secret_scanning.push_protection.bypass',
    detail: 'Secret push protection was bypassed 4 times in the last 90 days. The WAF recommends restricting bypass capability to specific roles/teams only.',
    wafRef: { label: 'WAF: Governance Policies', url: 'https://wellarchitected.github.com/library/governance/recommendations/governance-policies-best-practices/' },
  },
  {
    id: 'gov-webhooks-no-secret',
    finding: 'Webhooks without secrets — 3 webhooks configured without a secret token',
    pillar: 'governance',
    pillarLabel: 'Governance',
    pillarEmoji: '📜',
    evaluated: true,
    severity: 'warning',
    status: 'warning',
    evidence: 'hook.create, hook.config_changed — secret field absent in event payload',
    detail: 'Webhooks should always be configured with a secret. Not using a secret will mislead the receiving entity on the authenticity of the payload received.',
    wafRef: { label: 'WAF: Governance Policies', url: 'https://wellarchitected.github.com/library/governance/recommendations/governance-policies-best-practices/' },
  },
  {
    id: 'gov-classic-pat',
    finding: 'Classic PAT proliferation — no fine-grained PAT approval policy detected',
    pillar: 'governance',
    pillarLabel: 'Governance',
    pillarEmoji: '📜',
    evaluated: true,
    severity: 'warning',
    status: 'warning',
    evidence: 'personal_access_token.create, personal_access_token.access_denied',
    detail: 'OctoWatch has seen 47 classic PAT creation events this quarter with no corresponding fine-grained PAT approval events.',
    wafRef: { label: 'WAF: Governance Policies', url: 'https://wellarchitected.github.com/library/governance/recommendations/governance-policies-best-practices/' },
  },

  // App Security
  {
    id: 'sec-direct-push',
    finding: 'Direct pushes to default branch without a pull request — 14 events',
    pillar: 'appsec',
    pillarLabel: 'App Security',
    pillarEmoji: '🔒',
    evaluated: true,
    severity: 'critical',
    status: 'fail',
    evidence: 'git.push — push to default branch with no linked pull_request.merged event',
    detail: 'The WAF classifies "working directly on the main branch" as a Development Anti-Pattern. 14 direct pushes to main/master were detected by non-bot actors.',
    wafRef: { label: 'WAF: Branching Strategy', url: 'https://wellarchitected.github.com/library/scenarios/anti-patterns/#inconsistent-branching-strategy' },
  },
  {
    id: 'sec-codeowners',
    finding: 'CODEOWNERS file missing from 8 repositories',
    pillar: 'appsec',
    pillarLabel: 'App Security',
    pillarEmoji: '🔒',
    evaluated: true,
    severity: 'critical',
    status: 'fail',
    evidence: 'baseline import — absence of CODEOWNERS file in default branch at time of import',
    detail: 'Without CODEOWNERS, there is no automatic assignment of reviewers and no ownership accountability for critical code paths.',
    wafRef: { label: 'WAF: Governance Policies', url: 'https://wellarchitected.github.com/library/governance/recommendations/governance-policies-best-practices/' },
  },
  {
    id: 'sec-commit-signing',
    finding: 'Commit signing not required on 12 repositories',
    pillar: 'appsec',
    pillarLabel: 'App Security',
    pillarEmoji: '🔒',
    evaluated: true,
    severity: 'warning',
    status: 'warning',
    evidence: 'protected_branch.create — missing required_signatures constraint',
    detail: 'Initiate and impose commit signing whenever possible — this deters malicious actors from creating commits with malicious code.',
    wafRef: { label: 'WAF: App Security', url: 'https://wellarchitected.github.com/library/application-security/recommendations/actions-security/' },
  },

  // Architecture
  {
    id: 'arch-reusable-workflows',
    finding: 'No reusable workflow patterns detected — every repo duplicates CI definitions',
    pillar: 'architecture',
    pillarLabel: 'Architecture',
    pillarEmoji: '📐',
    evaluated: true,
    severity: 'warning',
    status: 'warning',
    evidence: 'workflow_run — no workflow_call trigger type observed in any workflow_run event',
    detail: 'OctoWatch detected 0 workflow_call trigger events across all repos in the last 90 days — all repos are running fully self-contained CI pipelines.',
    wafRef: { label: 'WAF: Actions Reusability', url: 'https://wellarchitected.github.com/library/collaboration/recommendations/scaling-actions-reusability/' },
  },

  // Collaboration
  {
    id: 'collab-unreviewed-prs',
    finding: 'PRs merged without code review — 6 events (bypassing code review anti-pattern)',
    pillar: 'collaboration',
    pillarLabel: 'Collaboration',
    pillarEmoji: '👥',
    evaluated: true,
    severity: 'warning',
    status: 'warning',
    evidence: 'pull_request.closed, pull_request_review.submitted — merged with no preceding review event',
    detail: 'OctoWatch detected 6 pull_request.closed (merged) events where no pull_request_review event was recorded before merge. Average open-to-merge time: 4 minutes.',
    wafRef: { label: 'WAF: Bypassing Code Reviews', url: 'https://wellarchitected.github.com/library/scenarios/anti-patterns/#bypassing-code-reviews' },
  },

  // Not-evaluated signals
  {
    id: 'gap-workflow-token',
    finding: 'Default workflow token permission = read-only',
    pillar: 'governance',
    pillarLabel: 'Governance',
    pillarEmoji: '📜',
    evaluated: false,
    severity: 'info',
    evidence: 'Org/enterprise policy state — not emitted as an audit event',
    wafRef: { label: 'Governance Policies', url: 'https://wellarchitected.github.com/library/governance/recommendations/governance-policies-best-practices/' },
  },
  {
    id: 'gap-actions-restricted',
    finding: 'Actions restricted to verified creators only',
    pillar: 'governance',
    pillarLabel: 'Governance',
    pillarEmoji: '📜',
    evaluated: false,
    severity: 'info',
    evidence: 'Actions allowed-list policy — requires API check of org settings',
    wafRef: { label: 'Governance Policies', url: 'https://wellarchitected.github.com/library/governance/recommendations/governance-policies-best-practices/' },
  },
  {
    id: 'gap-forking-disabled',
    finding: 'Forking disabled for private repos',
    pillar: 'governance',
    pillarLabel: 'Governance',
    pillarEmoji: '📜',
    evaluated: false,
    severity: 'info',
    evidence: 'Fork policy state — fork events visible but policy enforcement status requires API',
    wafRef: { label: 'Governance Policies', url: 'https://wellarchitected.github.com/library/governance/recommendations/governance-policies-best-practices/' },
  },
  {
    id: 'gap-runner-groups',
    finding: 'Runner groups scoped (not all-repos)',
    pillar: 'architecture',
    pillarLabel: 'Architecture',
    pillarEmoji: '📐',
    evaluated: false,
    severity: 'info',
    evidence: 'Runner group configuration — requires REST API access to runner group settings',
    wafRef: { label: 'Runner Controller', url: 'https://wellarchitected.github.com/library/architecture/recommendations/deploying-actions-runner-controller/' },
  },
  {
    id: 'gap-audit-streaming',
    finding: 'Audit log streaming fully enabled',
    pillar: 'governance',
    pillarLabel: 'Governance',
    pillarEmoji: '📜',
    evaluated: false,
    severity: 'info',
    evidence: 'Streaming is active (OctoWatch receives events), but completeness and gap detection require API verification',
    wafRef: { label: 'Governance Policies', url: 'https://wellarchitected.github.com/library/governance/recommendations/governance-policies-best-practices/' },
  },
];
