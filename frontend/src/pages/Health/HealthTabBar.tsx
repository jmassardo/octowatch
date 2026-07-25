import { Link } from 'react-router';
import styles from './Health.module.css';

export type HealthTab =
  | 'repo-health'
  | 'access-identity'
  | 'license'
  | 'maintenance'
  | 'waf'
  | 'security-posture'
  | 'app-governance'
  | 'operations'
  | 'api-abuse'
  | 'dormant-users'
  | 'platform-security'
  | 'maintenance-signals';

interface HealthTabBarProps {
  activeTab: HealthTab;
  onTabChange: (tab: HealthTab) => void;
  findingsCount?: number;
}

const TABS: { id: HealthTab; label: string }[] = [
  { id: 'repo-health', label: 'Repository Health' },
  { id: 'access-identity', label: 'Access & Identity' },
  { id: 'security-posture', label: 'Security Posture' },
  { id: 'app-governance', label: 'App Governance' },
  { id: 'operations', label: 'Operations' },
  { id: 'license', label: 'License Health' },
  { id: 'maintenance', label: 'Maintenance Signals' },
  { id: 'waf', label: 'WAF Insights' },
  { id: 'api-abuse', label: 'API & Abuse' },
  { id: 'dormant-users', label: 'Users' },
  { id: 'platform-security', label: 'Security' },
  { id: 'maintenance-signals', label: 'Maintenance' },
];

export function HealthTabBar({ activeTab, onTabChange, findingsCount }: HealthTabBarProps) {
  return (
    <div
      className={styles.healthTabsWrapper}
      style={{ display: 'flex', alignItems: 'center', gap: 8 }}
    >
      <div className={styles.healthTabs} role="tablist" style={{ flex: 1 }}>
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
      <Link
        to="/health/settings"
        title="Health Settings"
        aria-label="Health Settings"
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '4px 8px',
          color: 'var(--fg-muted)',
          textDecoration: 'none',
          borderRadius: 4,
          flexShrink: 0,
        }}
      >
        ⚙
      </Link>
    </div>
  );
}
