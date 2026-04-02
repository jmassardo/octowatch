/** Static / sample data for Health sub-tabs. */

/* ---- License Health ---- */

export const COST_PER_SEAT_DEFAULT = 19;

/* ---- WAF Insights ---- */

export type WafPillar = 'governance' | 'appsec' | 'architecture' | 'collaboration' | 'productivity';

export const PILLAR_META: Record<
  WafPillar,
  { emoji: string; label: string; description: string; url: string }
> = {
  governance: {
    emoji: '📜',
    label: 'Governance',
    description: 'Platform structure, policy enforcement, token hygiene',
    url: 'https://wellarchitected.github.com/library/governance/',
  },
  appsec: {
    emoji: '🔒',
    label: 'App Security',
    description: 'Signing, CODEOWNERS, ruleset bypass, supply chain',
    url: 'https://wellarchitected.github.com/library/application-security/',
  },
  architecture: {
    emoji: '📐',
    label: 'Architecture',
    description: 'Repo structure, reusability, runner topology',
    url: 'https://wellarchitected.github.com/library/architecture/',
  },
  collaboration: {
    emoji: '👥',
    label: 'Collaboration',
    description: 'Code review velocity, feedback cycles, PR hygiene',
    url: 'https://wellarchitected.github.com/library/collaboration/',
  },
  productivity: {
    emoji: '⚙️',
    label: 'Productivity',
    description: 'Automation, Copilot adoption, engineering metrics',
    url: 'https://wellarchitected.github.com/library/productivity/',
  },
};
