/** Static / placeholder data for Copilot Insights sub-tabs. */

/* ---- Seat costs & utilization ---- */
export const COST_PER_SEAT = 19;
export const TOTAL_SEATS = 186;
export const ACTIVE_SEATS = 124;
export const INACTIVE_SEATS = 38;
export const NEVER_USED_SEATS = 24;
export const WASTED_SEATS = INACTIVE_SEATS + NEVER_USED_SEATS;
export const MONTHLY_WASTE = WASTED_SEATS * COST_PER_SEAT;

/* ---- Acceptance rate chart (7-day rolling) ---- */
export const ACCEPTANCE_RATE_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export const ACCEPTANCE_RATE_VALUES = [24, 26, 27, 25, 28, 31, 29];
export const ACCEPTANCE_THRESHOLD = 25;
export const ACCEPTANCE_THRESHOLD_LINE = Array.from(
  { length: ACCEPTANCE_RATE_DAYS.length },
  () => ACCEPTANCE_THRESHOLD,
);

/* ---- Seat utilization trend (7-day) ---- */
export const SEAT_TREND_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export const SEAT_TREND_ACTIVE = [112, 115, 118, 114, 120, 108, 116];
export const SEAT_TREND_INACTIVE = [34, 36, 38, 38, 35, 40, 38];
export const SEAT_TREND_NEVER = [22, 23, 24, 24, 24, 24, 24];

/* ---- Acceptance rate by language ---- */
export const LANGUAGES = [
  { lang: 'TypeScript', pct: 38, color: '#3fb950' },
  { lang: 'Python', pct: 34, color: '#3fb950' },
  { lang: 'Go', pct: 29, color: '#26a641' },
  { lang: 'Java', pct: 21, color: '#d29922' },
  { lang: 'C++', pct: 14, color: '#f85149' },
  { lang: 'Rust', pct: 11, color: '#f85149' },
];

/* ---- Adoption tiers ---- */
export const ADOPTION_TIERS = [
  { id: 'power', label: 'Power Users', count: 34, color: '#3fb950', desc: 'Active every day' },
  { id: 'regular', label: 'Regular', count: 68, color: '#58a6ff', desc: '3-4 days/week' },
  { id: 'minimal', label: 'Minimal', count: 22, color: '#d29922', desc: '1-2 uses in 30d' },
  { id: 'inactive', label: 'Inactive', count: 38, color: '#f85149', desc: 'Cold 30d+ (was active)' },
  { id: 'never', label: 'Never Used', count: 24, color: '#8b949e', desc: 'Seat assigned, zero activity' },
] as const;

export const TOTAL_ADOPTION = ADOPTION_TIERS.reduce((s, t) => s + t.count, 0);

/* ---- Power users table ---- */
export const POWER_USERS = [
  { user: 'sarah.chen', team: 'Platform', streak: 45, acceptRate: 42 },
  { user: 'mike.ross', team: 'Backend', streak: 38, acceptRate: 39 },
  { user: 'ana.silva', team: 'Frontend', streak: 32, acceptRate: 36 },
  { user: 'james.wu', team: 'ML/AI', streak: 29, acceptRate: 44 },
  { user: 'priya.patel', team: 'DevOps', streak: 27, acceptRate: 31 },
];

/* ---- Feature adoption ---- */
export const FEATURE_ADOPTION = [
  { feature: 'IDE completions', pct: 87, color: '#3fb950' },
  { feature: 'IDE chat', pct: 62, color: '#58a6ff' },
  { feature: 'PR summaries', pct: 41, color: '#d29922' },
  { feature: 'CLI', pct: 23, color: '#f85149' },
  { feature: 'Knowledge bases', pct: 12, color: '#8b949e' },
];

/* ---- Minimal users table ---- */
export const MINIMAL_USERS = [
  { user: 'tom.jones', team: 'QA', uses: 2, accepted: 1, lastFeature: 'IDE chat' },
  { user: 'lisa.park', team: 'Design', uses: 1, accepted: 0, lastFeature: 'Completions' },
  { user: 'raj.kumar', team: 'Backend', uses: 2, accepted: 1, lastFeature: 'PR summary' },
];

/* ---- Model usage ---- */
export const MODEL_USAGE = [
  { model: 'GPT-4o', pct: 42, color: '#58a6ff' },
  { model: 'Claude 3.7', pct: 31, color: '#bc8cff' },
  { model: 'o3-mini', pct: 15, color: '#3fb950' },
  { model: 'Custom', pct: 8, color: '#d29922' },
  { model: 'GPT-4o-mini', pct: 4, color: '#8b949e' },
];

/* ---- Feature usage (by count) ---- */
export const FEATURE_USAGE = [
  { feature: 'IDE completions', count: 142, color: '#58a6ff' },
  { feature: 'IDE chat', count: 98, color: '#bc8cff' },
  { feature: 'github.com chat', count: 61, color: '#3fb950' },
  { feature: 'PR summaries', count: 44, color: '#d29922' },
  { feature: 'CLI', count: 18, color: '#f85149' },
  { feature: 'Knowledge bases', count: 12, color: '#8b949e' },
];

/* ---- Editor breakdown ---- */
export const EDITORS = [
  { name: 'VS Code', count: 112, pct: 79 },
  { name: 'JetBrains', count: 38, pct: 27 },
  { name: 'Neovim', count: 8, pct: 6 },
  { name: 'Xcode', count: 3, pct: 2 },
  { name: 'Other', count: 2, pct: 1 },
];

/* ---- Anomalies ---- */
export const ANOMALIES = [
  {
    id: 1,
    severity: 'high' as const,
    title: 'Sudden drop in acceptance rate',
    description:
      'Acceptance rate dropped 15% in Backend team over the last 48 hours. This correlates with a new linting config deployment.',
    timestamp: '2 hours ago',
    team: 'Backend',
  },
  {
    id: 2,
    severity: 'medium' as const,
    title: 'Unusual seat churn detected',
    description:
      '12 seats were revoked and re-assigned within 24 hours in the Platform org. This may indicate a provisioning script issue.',
    timestamp: '6 hours ago',
    team: 'Platform',
  },
  {
    id: 3,
    severity: 'low' as const,
    title: 'Knowledge base usage spike',
    description:
      'Knowledge base queries increased 340% in ML/AI team. Likely related to onboarding of 5 new team members.',
    timestamp: '1 day ago',
    team: 'ML/AI',
  },
];
