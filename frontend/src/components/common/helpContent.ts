export interface HelpConcept {
  term: string;
  definition: string;
}

export interface HelpTask {
  title: string;
  steps: string[];
}

export interface HelpRelatedPage {
  title: string;
  path: string;
}

export interface HelpContent {
  title: string;
  description: string;
  concepts: HelpConcept[];
  tasks: HelpTask[];
  relatedPages: HelpRelatedPage[];
}

export const HELP_CONTENT_REGISTRY: Record<string, HelpContent> = {
  '/dashboard': {
    title: 'Dashboard',
    description:
      'Use the dashboard to monitor platform health, security activity, event volume, and workflow performance across your connected organizations.',
    concepts: [
      {
        term: 'Views',
        definition:
          'Switch between Operations, Executive, Security Engineering, and CI/CD views to focus on the metrics that matter to each audience.',
      },
      {
        term: 'Activity signals',
        definition:
          'Cards and charts summarize recent detections, raw events, and workflow activity pulled from synchronized GitHub telemetry.',
      },
    ],
    tasks: [
      {
        title: 'Check the latest sync state',
        steps: [
          'Review the subtitle under the page title for the last sync timestamp.',
          'Scan the summary cards for sudden drops or spikes in activity.',
          'Switch views if you need a security, executive, or CI/CD specific perspective.',
        ],
      },
      {
        title: 'Investigate a trend',
        steps: [
          'Use the cards or charts to identify the metric that changed.',
          'Open the related detail page from the dashboard navigation.',
          'Filter the detail view to isolate the affected organization, period, or severity.',
        ],
      },
    ],
    relatedPages: [
      { title: 'Threat Detections', path: '/threats' },
      { title: 'Events Explorer', path: '/events' },
      { title: 'Engineering Velocity', path: '/velocity' },
    ],
  },
  '/threats': {
    title: 'Threat Detections',
    description:
      'Threat Detections surfaces rule-based and ML-assisted findings generated from audit log activity so analysts can triage suspicious behavior quickly.',
    concepts: [
      {
        term: 'Detection severity',
        definition:
          'Severity reflects the rule impact and urgency. Critical and high findings usually deserve immediate review.',
      },
      {
        term: 'Status buckets',
        definition:
          'Open, acknowledged, and closed counts help you understand triage progress across the current filter set.',
      },
    ],
    tasks: [
      {
        title: 'Prioritize urgent detections',
        steps: [
          'Filter by severity to show only critical or high findings.',
          'Sort or scan the list for recent activity spikes.',
          'Open a detection record and capture remediation or acknowledgement details.',
        ],
      },
      {
        title: 'Review activity by organization',
        steps: [
          'Select an organization from the organization filter.',
          'Compare the detection totals and statuses for that tenant.',
          'Use related pages to pivot into raw events or posture context.',
        ],
      },
    ],
    relatedPages: [
      { title: 'Events Explorer', path: '/events' },
      { title: 'Security Posture', path: '/posture' },
      { title: 'Detection Rules', path: '/rules' },
    ],
  },
  '/events': {
    title: 'Events Explorer',
    description:
      'Events Explorer lets you search raw audit log events across organizations, actors, repositories, and actions for fast investigation workflows.',
    concepts: [
      {
        term: 'Search chips',
        definition:
          'Submitted search expressions become removable chips so you can build structured filters incrementally.',
      },
      {
        term: 'Estimated counts',
        definition:
          'Some result totals are approximate when the backend optimizes large queries for speed.',
      },
    ],
    tasks: [
      {
        title: 'Find suspicious activity',
        steps: [
          'Enter an action, actor, organization, or repository filter in the search bar.',
          'Submit the query to add it as a chip.',
          'Review matching rows and open an event for complete metadata.',
        ],
      },
      {
        title: 'Refine a noisy search',
        steps: [
          'Remove broad chips that return too many events.',
          'Add more specific action, actor, or namespace filters.',
          'Use the table columns to confirm IP, location, and organization details.',
        ],
      },
    ],
    relatedPages: [
      { title: 'Threat Detections', path: '/threats' },
      { title: 'Cross-Organization Correlation', path: '/crossorg' },
      { title: 'Dashboard', path: '/dashboard' },
    ],
  },
  '/posture': {
    title: 'Security Posture',
    description:
      'Security Posture rolls up enterprise, organization, and repository security checks so you can see where controls are passing or failing.',
    concepts: [
      {
        term: 'Score',
        definition:
          'The posture score summarizes configured checks and security signals into an easy-to-scan percentage.',
      },
      {
        term: 'Hierarchy',
        definition:
          'You can drill from enterprise to organization to repository views while keeping the same posture model.',
      },
    ],
    tasks: [
      {
        title: 'Find weak security areas',
        steps: [
          'Review the overall score and failing counts at the current hierarchy level.',
          'Filter by severity or status to focus on the riskiest checks.',
          'Open an organization or repository to inspect the failing control details.',
        ],
      },
      {
        title: 'Trace a failing check to detections',
        steps: [
          'Locate the failing check row in the current view.',
          'Open any linked detection when available.',
          'Use the linked detection to review the underlying events and response steps.',
        ],
      },
    ],
    relatedPages: [
      { title: 'Threat Detections', path: '/threats' },
      { title: 'Compliance Center', path: '/compliance' },
      { title: 'Settings', path: '/settings' },
    ],
  },
  '/workflows': {
    title: 'Workflow Security Scanner',
    description:
      'Workflow Security Scanner analyzes workflow activity and highlights automation behavior that could introduce operational or security risk.',
    concepts: [
      {
        term: 'Analysis queue',
        definition:
          'Manual analysis requests enqueue a scan. Results appear after backend processing completes.',
      },
      {
        term: 'Findings',
        definition:
          'Scanner results focus on risky workflow patterns, suspicious execution context, and related workflow health issues.',
      },
    ],
    tasks: [
      {
        title: 'Run a fresh analysis',
        steps: [
          'Click Analyze Events in the header actions.',
          'Wait for the queued confirmation message.',
          'Refresh or revisit the findings panes after ingestion completes.',
        ],
      },
      {
        title: 'Pivot to operational health',
        steps: [
          'Use the cross-link near the top of the page.',
          'Open Workflow Health for failure and throughput metrics.',
          'Compare security findings with workflow reliability issues.',
        ],
      },
    ],
    relatedPages: [
      { title: 'Workflow Health', path: '/workflows/health' },
      { title: 'Engineering Velocity', path: '/velocity' },
      { title: 'Reports', path: '/reports' },
    ],
  },
  '/crossorg': {
    title: 'Cross-Organization Correlation',
    description:
      'Cross-Organization Correlation helps you identify actors and activity patterns that span multiple organizations.',
    concepts: [
      {
        term: 'High-risk actors',
        definition:
          'Actors with elevated scores or broad organization access may indicate automation abuse, compromised credentials, or misuse.',
      },
      {
        term: 'Correlation window',
        definition:
          'Scores and summaries reflect a rolling time window so you can compare consistent slices of activity.',
      },
    ],
    tasks: [
      {
        title: 'Review cross-org actor behavior',
        steps: [
          'Locate actors with elevated risk or unusually broad organization reach.',
          'Open a row to inspect per-organization activity.',
          'Verify whether the activity is expected for that user or automation token.',
        ],
      },
      {
        title: 'Investigate anomalies',
        steps: [
          'Use the guidance box to understand what patterns matter most.',
          'Compare volume, organizations, and time windows across the actor summaries.',
          'Pivot into Events Explorer if you need full raw event detail.',
        ],
      },
    ],
    relatedPages: [
      { title: 'Events Explorer', path: '/events' },
      { title: 'Threat Detections', path: '/threats' },
      { title: 'Dashboard', path: '/dashboard' },
    ],
  },
  '/copilot': {
    title: 'Copilot Insights',
    description:
      'Copilot Insights tracks usage, adoption, blockers, and licensing trends for GitHub Copilot across your organization.',
    concepts: [
      {
        term: 'Active tab',
        definition:
          'Tabs break the experience into overview, adoption, models, teams, blockers, license, and ROI views.',
      },
      {
        term: 'Seat utilization',
        definition:
          'Seat trends help you understand whether paid access is being used effectively.',
      },
    ],
    tasks: [
      {
        title: 'Measure adoption',
        steps: [
          'Start with the Overview or Adoption tab.',
          'Compare seat allocation, active users, and recent changes.',
          'Review blockers or license detail if usage is lower than expected.',
        ],
      },
      {
        title: 'Investigate blocked users',
        steps: [
          'Switch to the Blockers tab.',
          'Review the users or teams affected by setup and policy issues.',
          'Coordinate changes through Settings or support processes as needed.',
        ],
      },
    ],
    relatedPages: [
      { title: 'Settings', path: '/settings' },
      { title: 'Reports', path: '/reports' },
      { title: 'Dashboard', path: '/dashboard' },
    ],
  },
  '/velocity': {
    title: 'Engineering Velocity',
    description:
      'Engineering Velocity summarizes CI/CD throughput, delivery speed, and leadership-focused development metrics.',
    concepts: [
      {
        term: 'Velocity views',
        definition:
          'Metric and Leadership tabs tailor the same data set for hands-on engineering teams or broader stakeholders.',
      },
      {
        term: 'Flow metrics',
        definition:
          'Lead time, throughput, and related measures show how efficiently work moves through the delivery pipeline.',
      },
    ],
    tasks: [
      {
        title: 'Monitor delivery throughput',
        steps: [
          'Stay on the Metrics tab to review current engineering indicators.',
          'Look for drops in deployment volume or rising cycle times.',
          'Use related pages to compare workflow failures or report trends.',
        ],
      },
      {
        title: 'Prepare a leadership snapshot',
        steps: [
          'Switch to the Leadership tab.',
          'Review trend summaries and high-level KPIs.',
          'Cross-check the same period in Reports if you need more detail.',
        ],
      },
    ],
    relatedPages: [
      { title: 'Workflow Health', path: '/workflows/health' },
      { title: 'Reports', path: '/reports' },
      { title: 'Dashboard', path: '/dashboard' },
    ],
  },
  '/reports': {
    title: 'Reports',
    description:
      'Reports combines built-in analytics and custom report building so teams can review activity over configurable windows.',
    concepts: [
      {
        term: 'Window selector',
        definition:
          'The header controls let you switch between common reporting periods without rebuilding the page.',
      },
      {
        term: 'Custom reports',
        definition:
          'Custom reports let you tailor charting and exports for the audience or workflow you need to support.',
      },
    ],
    tasks: [
      {
        title: 'Compare reporting windows',
        steps: [
          'Use the 30d, 60d, or 90d controls in the header.',
          'Watch the summary charts and tables refresh.',
          'Export data once you have the desired reporting period selected.',
        ],
      },
      {
        title: 'Build a custom report',
        steps: [
          'Click New Custom Report.',
          'Choose the metrics and filters needed for your audience.',
          'Save or export the result for recurring review.',
        ],
      },
    ],
    relatedPages: [
      { title: 'Dashboard', path: '/dashboard' },
      { title: 'Engineering Velocity', path: '/velocity' },
      { title: 'Compliance Center', path: '/compliance' },
    ],
  },
  '/compliance': {
    title: 'Compliance Center',
    description:
      'Compliance Center tracks alignment with supported security frameworks and highlights control areas needing attention.',
    concepts: [
      {
        term: 'Overall score',
        definition:
          'The overall score is a weighted rollup across enabled frameworks and the controls each framework evaluates.',
      },
      {
        term: 'Framework posture',
        definition:
          'Each framework view shows how well your current settings and detections align with its requirements.',
      },
    ],
    tasks: [
      {
        title: 'Review framework readiness',
        steps: [
          'Start with the summary strip at the top of the page.',
          'Inspect frameworks with lower scores or more failing controls.',
          'Open related posture or settings pages to address the underlying gaps.',
        ],
      },
      {
        title: 'Explain a compliance gap',
        steps: [
          'Locate the framework or control with the weakest score.',
          'Check the mapped evidence and recommended remediation.',
          'Validate the related control status in Posture or Settings.',
        ],
      },
    ],
    relatedPages: [
      { title: 'Security Posture', path: '/posture' },
      { title: 'Settings', path: '/settings' },
      { title: 'Reports', path: '/reports' },
    ],
  },
  '/rules': {
    title: 'Detection Rules',
    description:
      'Detection Rules is the control plane for creating, editing, syncing, and reviewing automated detection logic.',
    concepts: [
      {
        term: 'Rule library',
        definition:
          'The rule library helps you browse reusable patterns before promoting them into your active ruleset.',
      },
      {
        term: 'Version history',
        definition:
          'Version history lets you inspect prior rule revisions and understand how detection behavior changed over time.',
      },
    ],
    tasks: [
      {
        title: 'Create a new rule',
        steps: [
          'Open the create flow or wizard from the header actions.',
          'Define the match logic, severity, and metadata.',
          'Save the rule and watch for new detections once matching events arrive.',
        ],
      },
      {
        title: 'Sync or validate rule updates',
        steps: [
          'Use the sync action in the header.',
          'Confirm the success banner or follow-up state.',
          'Review recent detections to confirm the change behaves as expected.',
        ],
      },
    ],
    relatedPages: [
      { title: 'Threat Detections', path: '/threats' },
      { title: 'Events Explorer', path: '/events' },
      { title: 'Settings', path: '/settings' },
    ],
  },
  '/settings': {
    title: 'Settings',
    description:
      'Settings centralizes product configuration, integrations, feature controls, and audit visibility for OctoWatch administrators.',
    concepts: [
      {
        term: 'Tabs',
        definition:
          'Each settings tab focuses on a configuration area such as features, integrations, security controls, or audit history.',
      },
      {
        term: 'Audit trail',
        definition:
          'Changes made in settings can be reviewed later so administrators can verify who changed what and when.',
      },
    ],
    tasks: [
      {
        title: 'Update a configuration area',
        steps: [
          'Open the tab that matches the setting you want to manage.',
          'Review current values and validation hints before saving.',
          'Confirm any follow-up alerts, sync requirements, or audit entries.',
        ],
      },
      {
        title: 'Troubleshoot an integration or feature',
        steps: [
          'Open the relevant Features or Integrations tab.',
          'Check whether required credentials or toggles are configured.',
          'Use audit history or related pages to verify downstream impact.',
        ],
      },
    ],
    relatedPages: [
      { title: 'Compliance Center', path: '/compliance' },
      { title: 'Copilot Insights', path: '/copilot/overview' },
      { title: 'Dashboard', path: '/dashboard' },
    ],
  },
};

const HELP_ROUTE_KEYS = Object.keys(HELP_CONTENT_REGISTRY).sort((a, b) => b.length - a.length);

export function findHelpContent(pathname: string): HelpContent | null {
  const matchedRoute = HELP_ROUTE_KEYS.find(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  );

  return matchedRoute ? HELP_CONTENT_REGISTRY[matchedRoute] : null;
}
