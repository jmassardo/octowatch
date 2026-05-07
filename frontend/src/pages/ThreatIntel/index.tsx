import { useState } from 'react';
import { PageHeader } from '../../components/common/PageHeader';
import { FeedsTab } from './FeedsTab';
import { IndicatorsTab } from './IndicatorsTab';
import { MatchesTab } from './MatchesTab';
import { AnalyticsTab } from './AnalyticsTab';
import styles from './ThreatIntel.module.css';

type TabId = 'feeds' | 'indicators' | 'matches' | 'analytics';

const TABS: { id: TabId; label: string }[] = [
  { id: 'feeds', label: 'Feeds' },
  { id: 'indicators', label: 'Indicators' },
  { id: 'matches', label: 'Matches' },
  { id: 'analytics', label: 'Analytics' },
];

export function ThreatIntelPage() {
  const [activeTab, setActiveTab] = useState<TabId>('feeds');

  return (
    <div className={styles.page}>
      <PageHeader
        title="Threat Intelligence"
        description="Manage threat intelligence feeds, indicators, and view detection matches"
      />

      <div className={styles.tabStrip} role="tablist" aria-label="Threat intelligence tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            className={[styles.tab, activeTab === tab.id && styles.active]
              .filter(Boolean)
              .join(' ')}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" aria-label={`${activeTab} tab content`}>
        {activeTab === 'feeds' && <FeedsTab />}
        {activeTab === 'indicators' && <IndicatorsTab />}
        {activeTab === 'matches' && <MatchesTab />}
        {activeTab === 'analytics' && <AnalyticsTab />}
      </div>
    </div>
  );
}
