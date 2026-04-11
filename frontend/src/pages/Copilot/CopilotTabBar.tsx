import styles from './Copilot.module.css';

export type CopilotTab = 'overview' | 'adoption' | 'models' | 'license' | 'anomalies' | 'governance';

interface CopilotTabBarProps {
  activeTab: CopilotTab;
  onTabChange: (tab: CopilotTab) => void;
  anomalyCount?: number;
}

const TABS: { id: CopilotTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'adoption', label: 'Adoption' },
  { id: 'models', label: 'Models & Features' },
  { id: 'license', label: 'License Optimization' },
  { id: 'anomalies', label: 'Anomalies' },
  { id: 'governance', label: 'Governance' },
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
