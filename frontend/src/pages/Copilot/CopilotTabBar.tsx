import styles from './Copilot.module.css';

export type CopilotTab =
  | 'overview'
  | 'activity'
  | 'adoption'
  | 'teams'
  | 'chat'
  | 'languages'
  | 'models'
  | 'license'
  | 'billing'
  | 'roi'
  | 'prs'
  | 'agent'
  | 'blockers'
  | 'policy'
  | 'governance'
  | 'anomalies';

interface CopilotTabBarProps {
  activeTab: CopilotTab;
  onTabChange: (tab: CopilotTab) => void;
  anomalyCount?: number;
}

const TABS: { id: CopilotTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'activity', label: 'Activity' },
  { id: 'adoption', label: 'Adoption' },
  { id: 'teams', label: 'Teams' },
  { id: 'chat', label: 'Chat' },
  { id: 'languages', label: 'Languages' },
  { id: 'models', label: 'Models & Features' },
  { id: 'prs', label: 'Pull Requests' },
  { id: 'agent', label: 'Agent' },
  { id: 'license', label: 'License Optimization' },
  { id: 'billing', label: 'Billing & UBB' },
  { id: 'roi', label: 'ROI' },
  { id: 'blockers', label: 'Blockers' },
  { id: 'policy', label: 'Policy' },
  { id: 'governance', label: 'Governance' },
  { id: 'anomalies', label: 'Anomalies' },
];

export function CopilotTabBar({ activeTab, onTabChange, anomalyCount }: CopilotTabBarProps) {
  return (
    <div className={styles.copilotTabs} role="tablist">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={activeTab === tab.id}
          className={[styles.copilotTab, activeTab === tab.id && styles.copilotTabActive]
            .filter(Boolean)
            .join(' ')}
          onClick={() => onTabChange(tab.id)}
        >
          {tab.label}
          {tab.id === 'anomalies' && anomalyCount != null && anomalyCount > 0 && (
            <span className={styles.tabBadge}>{anomalyCount}</span>
          )}
        </button>
      ))}
    </div>
  );
}
