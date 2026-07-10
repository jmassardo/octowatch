import { PageHeader } from '../../components/common/PageHeader';
import { FeedsTab } from './FeedsTab';
import { IndicatorsTab } from './IndicatorsTab';
import { MatchesTab } from './MatchesTab';
import { AnalyticsTab } from './AnalyticsTab';
import { CampaignsTab } from './CampaignsTab';
import { useTabParam } from '../../hooks/useTabParam';
import styles from './ThreatIntel.module.css';

type TabId = 'campaigns' | 'feeds' | 'indicators' | 'matches' | 'analytics';

const TAB_KEYS = ['campaigns', 'feeds', 'indicators', 'matches', 'analytics'] as const;

const TABS: { id: TabId; label: string }[] = [
  { id: 'campaigns', label: 'Campaigns' },
  { id: 'feeds', label: 'Feeds' },
  { id: 'indicators', label: 'Indicators' },
  { id: 'matches', label: 'Matches' },
  { id: 'analytics', label: 'Analytics' },
];

export function ThreatIntelPage() {
  const [activeTab, setActiveTab] = useTabParam('/threat-intel', TAB_KEYS, 'campaigns');

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
        {activeTab === 'campaigns' && <CampaignsTab />}
        {activeTab === 'feeds' && <FeedsTab />}
        {activeTab === 'indicators' && <IndicatorsTab />}
        {activeTab === 'matches' && <MatchesTab />}
        {activeTab === 'analytics' && <AnalyticsTab />}
      </div>
    </div>
  );
}
