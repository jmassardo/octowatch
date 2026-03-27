import styles from './Health.module.css';

export type HealthTab = 'repo-health' | 'access-identity' | 'license' | 'maintenance' | 'waf';

interface HealthTabBarProps {
  activeTab: HealthTab;
  onTabChange: (tab: HealthTab) => void;
  findingsCount?: number;
}

const TABS: { id: HealthTab; label: string }[] = [
  { id: 'repo-health', label: 'Repository Health' },
  { id: 'access-identity', label: 'Access & Identity' },
  { id: 'license', label: 'License Health' },
  { id: 'maintenance', label: 'Maintenance Signals' },
  { id: 'waf', label: 'WAF Insights' },
];

export function HealthTabBar({ activeTab, onTabChange, findingsCount }: HealthTabBarProps) {
  return (
    <div className={styles.healthTabs} role="tablist">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={activeTab === tab.id}
          className={[styles.healthTab, activeTab === tab.id && styles.healthTabActive]
            .filter(Boolean)
            .join(' ')}
          onClick={() => onTabChange(tab.id)}
        >
          {tab.label}
          {tab.id === 'waf' && findingsCount != null && findingsCount > 0 && (
            <span className={styles.tabBadge}>{findingsCount}</span>
          )}
        </button>
      ))}
    </div>
  );
}
