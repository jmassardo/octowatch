import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCrossOrgTimeline, getCrossOrgCorrelations } from '../../api/crossOrg';
import type { CrossOrgCorrelation, CrossOrgTimelineEvent } from '../../api/crossOrg';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { Button } from '../../components/primitives/Button';
import { formatRelativeShort } from '../../utils/dates';
import styles from './CrossOrg.module.css';

type Tab = 'correlations' | 'timeline';

function riskClass(score: number): string {
  if (score >= 70) return styles.riskHigh;
  if (score >= 40) return styles.riskMedium;
  return styles.riskLow;
}

function riskLabel(score: number): string {
  if (score >= 70) return 'High';
  if (score >= 40) return 'Medium';
  return 'Low';
}

function CorrelationCard({ correlation }: { correlation: CrossOrgCorrelation }) {
  return (
    <div className={styles.correlationCard}>
      <div className={styles.cardHeader}>
        <span className={styles.actorName}>{correlation.actor}</span>
        <span className={`${styles.riskBadge} ${riskClass(correlation.risk_score)}`}>
          {riskLabel(correlation.risk_score)} ({correlation.risk_score})
        </span>
      </div>
      <div className={styles.cardMeta}>
        <span>{correlation.event_count} events</span>
        <span>{correlation.distinct_actions} actions</span>
        <span>Last seen {formatRelativeShort(correlation.last_seen)}</span>
      </div>
      <div className={styles.orgTags}>
        {correlation.orgs.map((org) => (
          <span key={org} className={styles.orgTag}>
            {org}
          </span>
        ))}
      </div>
    </div>
  );
}

function TimelineRow({ event }: { event: CrossOrgTimelineEvent }) {
  return (
    <div className={styles.timelineItem}>
      <span className={styles.timelineTime}>{formatRelativeShort(event.created_at)}</span>
      <span className={styles.timelineAction}>{event.action}</span>
      <span className={styles.timelineActor}>{event.actor}</span>
      <span className={styles.timelineOrg}>{event.org}</span>
    </div>
  );
}

export function CrossOrgPage() {
  const [tab, setTab] = useState<Tab>('correlations');
  const [actor, setActor] = useState('');
  const [searchInput, setSearchInput] = useState('');

  const {
    data: correlationData,
    isLoading: loadingCorrelations,
    isError: correlationError,
    refetch: refetchCorrelations,
  } = useQuery({
    queryKey: ['cross-org', 'correlations'],
    queryFn: () => getCrossOrgCorrelations({ min_orgs: 2, hours: 168 }),
  });

  const {
    data: timelineData,
    isLoading: loadingTimeline,
    isError: timelineError,
    refetch: refetchTimeline,
  } = useQuery({
    queryKey: ['cross-org', 'timeline', actor],
    queryFn: () => getCrossOrgTimeline({ actor: actor || undefined, hours: 168 }),
    enabled: tab === 'timeline',
  });

  const handleSearch = () => {
    setActor(searchInput.trim());
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Cross-Organization Correlation</div>
      <div className={styles.pageSub}>
        Identify actors operating across multiple organizations and detect coordinated activity
      </div>

      <div className={styles.searchBar}>
        <input
          className={styles.searchInput}
          placeholder="Filter by actor username…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSearch();
          }}
        />
        <Button size="sm" onClick={handleSearch}>
          Search
        </Button>
      </div>

      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${tab === 'correlations' ? styles.tabActive : ''}`}
          onClick={() => setTab('correlations')}
        >
          Correlations
        </button>
        <button
          className={`${styles.tab} ${tab === 'timeline' ? styles.tabActive : ''}`}
          onClick={() => setTab('timeline')}
        >
          Timeline
        </button>
      </div>

      {tab === 'correlations' && (
        <div className={styles.section}>
          {loadingCorrelations && <Spinner />}
          {correlationError && (
            <ErrorBanner message="Failed to load correlations" onRetry={() => void refetchCorrelations()} />
          )}
          {correlationData && correlationData.correlations.length === 0 && (
            <div className={styles.emptyState}>
              No cross-org correlations found in the last 7 days
            </div>
          )}
          {correlationData && correlationData.correlations.length > 0 && (
            <>
              <div className={styles.sectionTitle}>
                {correlationData.total} actors across multiple orgs
              </div>
              <div className={styles.correlationGrid}>
                {correlationData.correlations.map((c) => (
                  <CorrelationCard key={c.actor} correlation={c} />
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {tab === 'timeline' && (
        <div className={styles.section}>
          {loadingTimeline && <Spinner />}
          {timelineError && (
            <ErrorBanner message="Failed to load timeline" onRetry={() => void refetchTimeline()} />
          )}
          {timelineData && timelineData.events.length === 0 && (
            <div className={styles.emptyState}>
              {actor ? `No events found for ${actor}` : 'No cross-org events found'}
            </div>
          )}
          {timelineData && timelineData.events.length > 0 && (
            <>
              <div className={styles.sectionTitle}>{timelineData.total} events</div>
              <div className={styles.timelineList}>
                {timelineData.events.map((event) => (
                  <TimelineRow key={event.id} event={event} />
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
