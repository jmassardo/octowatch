import styles from './Copilot.module.css';

export type CopilotTab =
  | 'overview'
  | 'adoption'
  | 'models'
  | 'license'
  | 'anomalies'
  | 'governance'
  | 'teams'
  | 'blockers'
  | 'policy'
  | 'roi';

interface CopilotTabBarProps {
  activeTab: CopilotTab;
  onTabChange: (tab: CopilotTab) => void;
  anomalyCount?: number;
  blockerCount?: number;
}

const TABS: { id: CopilotTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'adoption', label: 'Adoption' },
  { id: 'models', label: 'Models & Features' },
  { id: 'teams', label: 'Teams' },
  { id: 'blockers', label: 'Blockers' },
  { id: 'license', label: 'License Optimization' },
  { id: 'roi', label: 'ROI' },
  { id: 'anomalies', label: 'Anomalies' },
  { id: 'policy', label: 'Policy Timeline' },
  { id: 'governance', label: 'Governance' },
];

export function CopilotTabBar({
  activeTab,
  onTabChange,
  anomalyCount,
  blockerCount,
}: CopilotTabBarProps) {
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
          {tab.id === 'blockers' && blockerCount != null && blockerCount > 0 && (
            <span className={styles.tabBadge}>{blockerCount}</span>
          )}
        </button>
      ))}
    </div>
  );
}
