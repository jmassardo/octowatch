import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import {
  getCrossOrgTimeline,
  getCrossOrgCorrelations,
  getActorCrossOrgDetail,
} from '../../api/crossOrg';
import type { CrossOrgCorrelation, CrossOrgTimelineEvent } from '../../api/crossOrg';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { PageHeader } from '../../components/common/PageHeader';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { MetricCard } from '../../components/primitives/MetricCard';
import { DataTable, type ColumnDef } from '../../components/primitives/DataTable';
import { formatRelativeShort } from '../../utils/dates';
import styles from './CrossOrg.module.css';

type Tab = 'correlations' | 'timeline';
type RiskTier = 'critical' | 'high' | 'medium' | 'low';

const HOURS_OPTIONS = [
  { label: '24 hours', value: 24 },
  { label: '3 days', value: 72 },
  { label: '7 days', value: 168 },
  { label: '30 days', value: 720 },
];

const SENSITIVE_ACTIONS = [
  'org.add_member',
  'repo.destroy',
  'team.remove_member',
  'org.remove_member',
  'org.update_member',
  'repo.transfer',
  'team.destroy',
];

const GUIDANCE_STORAGE_KEY = 'octowatch.crossorg.guidance_collapsed';

function getRiskTier(score: number): RiskTier {
  if (score >= 85) return 'critical';
  if (score >= 70) return 'high';
  if (score >= 40) return 'medium';
  return 'low';
}

function riskLabelVariant(tier: RiskTier): 'danger' | 'severe' | 'attention' | 'muted' {
  switch (tier) {
    case 'critical':
      return 'danger';
    case 'high':
      return 'severe';
    case 'medium':
      return 'attention';
    case 'low':
      return 'muted';
  }
}

function riskTierLabel(tier: RiskTier): string {
  switch (tier) {
    case 'critical':
      return 'Critical';
    case 'high':
      return 'High';
    case 'medium':
      return 'Medium';
    case 'low':
      return 'Low';
  }
}

function getRiskFactors(correlation: CrossOrgCorrelation): string[] {
  const factors: string[] = [];
  const orgCount = correlation.org_count ?? correlation.orgs.length;
  if (orgCount >= 4) {
    factors.push(`High org count (${orgCount} organizations)`);
  }
  if (correlation.event_count >= 50) {
    factors.push(`High event volume (${correlation.event_count} events)`);
  }
  if (correlation.distinct_actions >= 10) {
    factors.push(`Many distinct actions (${correlation.distinct_actions})`);
  }
  const lastSeenDate = new Date(correlation.last_seen);
  const twentyFourHoursAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
  if (lastSeenDate > twentyFourHoursAgo) {
    factors.push('Recent activity (within 24h)');
  }
  const topActions = correlation.top_actions ?? [];
  const sensitiveFound = topActions.filter((a) => SENSITIVE_ACTIONS.includes(a));
  if (sensitiveFound.length > 0) {
    factors.push(`Unusual action patterns (${sensitiveFound.join(', ')})`);
  }
  return factors;
}

function getInitialGuidanceCollapsed(): boolean {
  try {
    const stored = localStorage.getItem(GUIDANCE_STORAGE_KEY);
    if (stored === null) return true; // default collapsed
    return stored === 'true';
  } catch {
    return true;
  }
}

const correlationColumns: ColumnDef<CrossOrgCorrelation>[] = [
  {
    key: 'risk_score',
    header: 'Risk',
    sortable: true,
    filterable: false,
    helpText: 'Composite risk score based on activity volume, org spread, and action sensitivity',
    width: '90px',
    render: (row) => {
      const tier = getRiskTier(row.risk_score);
      return (
        <Label variant={riskLabelVariant(tier)}>
          {riskTierLabel(tier)} ({row.risk_score})
        </Label>
      );
    },
    sortValue: (row) => row.risk_score,
  },
  {
    key: 'actor',
    header: 'Actor',
    sortable: true,
    filterable: true,
    helpText: 'The user performing cross-org activity',
    render: (row) => <span className={styles.actorName}>{row.actor}</span>,
    sortValue: (row) => row.actor,
    filterValue: (row) => row.actor,
  },
  {
    key: 'orgs',
    header: 'Organizations',
    sortable: true,
    filterable: true,
    helpText: 'Organizations this actor has accessed',
    render: (row) => {
      const orgs = row.orgs;
      const shown = orgs.slice(0, 3);
      const remaining = orgs.length - 3;
      return (
        <span className={styles.orgTags}>
          {shown.map((org) => (
            <span key={org} className={styles.orgTag}>
              {org}
            </span>
          ))}
          {remaining > 0 && <span className={styles.muted}>+{remaining} more</span>}
        </span>
      );
    },
    sortValue: (row) => row.org_count ?? row.orgs.length,
    filterValue: (row) => row.orgs.join(' '),
  },
  {
    key: 'event_count',
    header: 'Events',
    sortable: true,
    filterable: false,
    helpText: 'Total audit log events generated by this actor',
    width: '80px',
    render: (row) => <>{row.event_count}</>,
    sortValue: (row) => row.event_count,
  },
  {
    key: 'distinct_actions',
    header: 'Actions',
    sortable: true,
    filterable: false,
    helpText: 'Number of unique action types performed',
    width: '80px',
    render: (row) => <>{row.distinct_actions}</>,
    sortValue: (row) => row.distinct_actions,
  },
  {
    key: 'last_seen',
    header: 'Last Seen',
    sortable: true,
    filterable: false,
    helpText: 'Most recent activity timestamp',
    width: '110px',
    render: (row) => <>{formatRelativeShort(row.last_seen)}</>,
    sortValue: (row) => new Date(row.last_seen),
  },
];

const timelineColumns: ColumnDef<CrossOrgTimelineEvent>[] = [
  {
    key: 'created_at',
    header: 'Time',
    sortable: true,
    filterable: true,
    helpText: 'When the event occurred',
    render: (event) => <>{formatRelativeShort(event.created_at)}</>,
    sortValue: (event) => new Date(event.created_at),
    filterValue: (event) => formatRelativeShort(event.created_at),
  },
  {
    key: 'action',
    header: 'Action',
    sortable: true,
    filterable: true,
    helpText: 'The audit log action that was performed',
    render: (event) => <>{event.action}</>,
    sortValue: (event) => event.action,
    filterValue: (event) => event.action,
  },
  {
    key: 'actor',
    header: 'Actor',
    sortable: true,
    filterable: true,
    helpText: 'The user that performed the action',
    render: (event) => <>{event.actor}</>,
    sortValue: (event) => event.actor,
    filterValue: (event) => event.actor,
  },
  {
    key: 'org',
    header: 'Org',
    sortable: true,
    filterable: true,
    helpText: 'The organization where the event occurred',
    render: (event) => <>{event.org}</>,
    sortValue: (event) => event.org,
    filterValue: (event) => event.org,
  },
  {
    key: 'ip_location',
    header: 'IP / Location',
    sortable: true,
    filterable: true,
    helpText: 'Source IP address and country of origin',
    render: (event) => (
      <>
        {event.source_ip && <code>{event.source_ip}</code>}
        {event.country && <span className={styles.country}>{event.country}</span>}
      </>
    ),
    sortValue: (event) => event.source_ip ?? '',
    filterValue: (event) => [event.source_ip ?? '', event.country ?? ''].join(' ').trim(),
  },
];

function isBot(actor: string): boolean {
  return actor.endsWith('[bot]') || actor.startsWith('github-actions');
}

function csvExport(correlations: CrossOrgCorrelation[]): void {
  const headers = [
    'Actor',
    'Type',
    'Risk Score',
    'Risk Tier',
    'Orgs',
    'Events',
    'Actions',
    'First Seen',
    'Last Seen',
  ];
  const rows = correlations.map((c) => [
    c.actor,
    isBot(c.actor) ? 'Bot' : 'Human',
    c.risk_score,
    riskTierLabel(getRiskTier(c.risk_score)),
    c.orgs.join('; '),
    c.event_count,
    c.distinct_actions,
    c.first_seen,
    c.last_seen,
  ]);
  const csv = [headers, ...rows]
    .map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','))
    .join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `cross-org-actors-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

type ActorType = 'all' | 'human' | 'bot';

export function CrossOrgPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('correlations');
  const [actor, setActor] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [hours, setHours] = useState(168);
  const [selectedActor, setSelectedActor] = useState<string | null>(null);
  const [timelinePage, setTimelinePage] = useState(1);
  const [riskFilter, setRiskFilter] = useState<RiskTier | null>(null);
  const [guidanceCollapsed, setGuidanceCollapsed] = useState(getInitialGuidanceCollapsed);
  const [orgFilter, setOrgFilter] = useState<string>('');
  const [minOrgs, setMinOrgs] = useState(2);
  const [actorType, setActorType] = useState<ActorType>('all');

  const {
    data: correlationData,
    isLoading: loadingCorrelations,
    isError: correlationError,
    refetch: refetchCorrelations,
  } = useQuery({
    queryKey: ['cross-org', 'correlations', hours, minOrgs],
    queryFn: () => getCrossOrgCorrelations({ min_orgs: minOrgs, hours }),
  });

  const {
    data: timelineData,
    isLoading: loadingTimeline,
    isError: timelineError,
    refetch: refetchTimeline,
  } = useQuery({
    queryKey: ['cross-org', 'timeline', actor, hours, timelinePage],
    queryFn: () =>
      getCrossOrgTimeline({ actor: actor || undefined, hours, page: timelinePage, page_size: 50 }),
    enabled: tab === 'timeline',
  });

  const { data: actorDetail, isLoading: loadingDetail } = useQuery({
    queryKey: ['cross-org', 'actor-detail', selectedActor, hours],
    queryFn: () => getActorCrossOrgDetail(selectedActor!, Math.ceil(hours / 24)),
    enabled: !!selectedActor,
  });

  const handleSearch = () => {
    setActor(searchInput.trim());
    setTimelinePage(1);
  };

  const toggleGuidance = () => {
    const newVal = !guidanceCollapsed;
    setGuidanceCollapsed(newVal);
    try {
      localStorage.setItem(GUIDANCE_STORAGE_KEY, String(newVal));
    } catch {
      /* storage unavailable */
    }
  };

  // Compute risk tier counts
  const riskCounts = useMemo(() => {
    const correlations = correlationData?.correlations ?? [];
    const counts = { critical: 0, high: 0, medium: 0, low: 0 };
    for (const c of correlations) {
      counts[getRiskTier(c.risk_score)]++;
    }
    return counts;
  }, [correlationData]);

  // Collect all unique orgs for org filter dropdown
  const allOrgs = useMemo(() => {
    const orgSet = new Set<string>();
    for (const c of correlationData?.correlations ?? []) {
      for (const org of c.orgs) orgSet.add(org);
    }
    return [...orgSet].sort();
  }, [correlationData]);

  // Filter correlations by risk tier, org, and actor type
  const filteredCorrelations = useMemo(() => {
    let correlations = correlationData?.correlations ?? [];
    if (riskFilter) {
      correlations = correlations.filter((c) => getRiskTier(c.risk_score) === riskFilter);
    }
    if (orgFilter) {
      correlations = correlations.filter((c) => c.orgs.includes(orgFilter));
    }
    if (actorType === 'bot') {
      correlations = correlations.filter((c) => isBot(c.actor));
    } else if (actorType === 'human') {
      correlations = correlations.filter((c) => !isBot(c.actor));
    }
    return correlations;
  }, [correlationData, riskFilter, orgFilter, actorType]);

  // The DataTable handles sorting internally via column headers,
  // so we pass data sorted by risk_score desc as default order
  const sortedCorrelations = useMemo(() => {
    return [...filteredCorrelations].sort((a, b) => b.risk_score - a.risk_score);
  }, [filteredCorrelations]);

  const timelineTotal = timelineData?.total ?? 0;
  const timelinePages = Math.ceil(timelineTotal / 50);

  // Find the selected correlation for the detail panel risk factors
  const selectedCorrelation = useMemo(() => {
    if (!selectedActor || !correlationData) return null;
    return correlationData.correlations.find((c) => c.actor === selectedActor) ?? null;
  }, [selectedActor, correlationData]);

  // Quick Actions column needs state setters, so we define it here
  const correlationColumnsWithActions: ColumnDef<CrossOrgCorrelation>[] = useMemo(
    () => [
      ...correlationColumns,
      {
        key: 'actions',
        header: 'Quick Actions',
        sortable: false,
        filterable: false,
        helpText: 'Investigate this actor',
        width: '120px',
        render: (row) => (
          <Button
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              setSelectedActor(row.actor);
              setActor(row.actor);
              setSearchInput(row.actor);
            }}
          >
            Investigate
          </Button>
        ),
      },
    ],
    [],
  );

  return (
    <div className={styles.splitLayout}>
      <div className={styles.splitMain}>
        <PageHeader
          title="Cross-Organization Correlation"
          description="Correlate events across organizations for threat detection"
          showHelp
        />

        {/* AC-6: Collapsible guidance box */}
        <div className={styles.guidanceBox}>
          <button
            className={styles.guidanceToggle}
            onClick={toggleGuidance}
            aria-expanded={!guidanceCollapsed}
          >
            <span className={styles.guidanceChevron} data-collapsed={guidanceCollapsed}>
              ▶
            </span>
            What is cross-org monitoring?
          </button>
          {!guidanceCollapsed && (
            <ul className={styles.guidanceList}>
              <li>
                <strong>Review high-risk actors</strong> — Users with high scores are active across
                many orgs with high event volume. Click a row to see their activity by org.
              </li>
              <li>
                <strong>Check for anomalies</strong> — Look for unusual IP addresses, actions
                outside normal patterns, or activity in orgs where the user shouldn&apos;t be.
              </li>
              <li>
                <strong>Take action</strong> — From the detail panel you can investigate threats,
                view timeline, or check the actor on GitHub.
              </li>
              <li>
                <strong>Timeline tab</strong> — Switch to Timeline for a chronological view of all
                cross-org activity, filterable by actor.
              </li>
            </ul>
          )}
        </div>

        {/* AC-1: Risk Summary Header */}
        {correlationData && (
          <div className={styles.riskSummary}>
            <MetricCard
              value={String(correlationData.total)}
              label="Total Cross-Org Actors"
              helpText="Total number of actors detected with activity across multiple organizations"
            />
            <MetricCard
              value={String(riskCounts.critical)}
              label="Critical"
              style={{ borderColor: 'var(--danger)' }}
              accent={riskFilter === 'critical'}
              onClick={() => setRiskFilter(riskFilter === 'critical' ? null : 'critical')}
              helpText="Actors with risk score ≥ 85"
            />
            <MetricCard
              value={String(riskCounts.high)}
              label="High"
              style={{ borderColor: 'var(--danger)' }}
              accent={riskFilter === 'high'}
              onClick={() => setRiskFilter(riskFilter === 'high' ? null : 'high')}
              helpText="Actors with risk score ≥ 70"
            />
            <MetricCard
              value={String(riskCounts.medium)}
              label="Medium"
              style={{ borderColor: 'var(--severe)' }}
              accent={riskFilter === 'medium'}
              onClick={() => setRiskFilter(riskFilter === 'medium' ? null : 'medium')}
              helpText="Actors with risk score ≥ 40"
            />
            <MetricCard
              value={String(riskCounts.low)}
              label="Low"
              style={{ borderColor: 'var(--success)' }}
              accent={riskFilter === 'low'}
              onClick={() => setRiskFilter(riskFilter === 'low' ? null : 'low')}
              helpText="Actors with risk score < 40"
            />
          </div>
        )}

        {/* AC-3: Active filter indicator */}
        {(riskFilter || orgFilter || actorType !== 'all') && (
          <div className={styles.filterIndicator}>
            <span>
              Filtered by: {riskFilter && <strong>{riskTierLabel(riskFilter)} risk</strong>}
              {orgFilter && (
                <>
                  {riskFilter ? ', ' : ''}
                  <strong>{orgFilter}</strong>
                </>
              )}
              {actorType !== 'all' && (
                <>
                  {riskFilter || orgFilter ? ', ' : ''}
                  <strong>{actorType === 'bot' ? 'Bots' : 'Humans'}</strong>
                </>
              )}
            </span>
            <Button
              size="sm"
              onClick={() => {
                setRiskFilter(null);
                setOrgFilter('');
                setActorType('all');
              }}
            >
              Clear all filters
            </Button>
          </div>
        )}

        <div className={styles.controlBar}>
          <div className={styles.controlLeft}>
            <select
              className={styles.filterSelect}
              value={hours}
              onChange={(e) => {
                setHours(Number(e.target.value));
                setSelectedActor(null);
                setRiskFilter(null);
                setOrgFilter('');
                setActorType('all');
                setTimelinePage(1);
              }}
            >
              {HOURS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <select
              className={styles.filterSelect}
              value={minOrgs}
              onChange={(e) => setMinOrgs(Number(e.target.value))}
              aria-label="Minimum organizations"
            >
              <option value={2}>≥ 2 orgs</option>
              <option value={3}>≥ 3 orgs</option>
              <option value={4}>≥ 4 orgs</option>
              <option value={5}>≥ 5 orgs</option>
            </select>
            {allOrgs.length > 0 && (
              <select
                className={styles.filterSelect}
                value={orgFilter}
                onChange={(e) => setOrgFilter(e.target.value)}
                aria-label="Filter by organization"
              >
                <option value="">All orgs</option>
                {allOrgs.map((org) => (
                  <option key={org} value={org}>
                    {org}
                  </option>
                ))}
              </select>
            )}
            <select
              className={styles.filterSelect}
              value={actorType}
              onChange={(e) => setActorType(e.target.value as ActorType)}
              aria-label="Actor type"
            >
              <option value="all">All actors</option>
              <option value="human">Humans only</option>
              <option value="bot">Bots only</option>
            </select>
            {tab === 'timeline' && (
              <div className={styles.timelineSearch}>
                <input
                  className={styles.searchInput}
                  placeholder="Filter by actor…"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSearch();
                  }}
                />
                <Button size="sm" onClick={handleSearch}>
                  Filter
                </Button>
                {actor && (
                  <Button
                    size="sm"
                    onClick={() => {
                      setActor('');
                      setSearchInput('');
                      setTimelinePage(1);
                    }}
                  >
                    Clear
                  </Button>
                )}
              </div>
            )}
          </div>
          <div className={styles.controlRight}>
            {tab === 'correlations' && sortedCorrelations.length > 0 && (
              <Button size="sm" onClick={() => csvExport(sortedCorrelations)}>
                Export CSV
              </Button>
            )}
          </div>
        </div>

        <div className={styles.tabs}>
          <button
            className={`${styles.tab} ${tab === 'correlations' ? styles.tabActive : ''}`}
            onClick={() => setTab('correlations')}
          >
            Correlations
            {correlationData && <span className={styles.tabBadge}>{correlationData.total}</span>}
          </button>
          <button
            className={`${styles.tab} ${tab === 'timeline' ? styles.tabActive : ''}`}
            onClick={() => setTab('timeline')}
          >
            Timeline
          </button>
        </div>

        {/* AC-2: Risk-ranked DataTable for correlations */}
        {tab === 'correlations' && (
          <div className={styles.section}>
            {loadingCorrelations && <Spinner />}
            {correlationError && (
              <ErrorBanner
                message="Failed to load correlations"
                onRetry={() => void refetchCorrelations()}
              />
            )}
            {/* AC-5: Improved empty state */}
            {correlationData &&
              sortedCorrelations.length === 0 &&
              !riskFilter &&
              !orgFilter &&
              actorType === 'all' && (
                <div className={styles.emptyStateSuccess}>
                  <span className={styles.emptyIcon} aria-hidden="true">
                    🛡️
                  </span>
                  <p className={styles.emptyTitle}>All clear</p>
                  <p className={styles.emptyMessage}>
                    No suspicious cross-org activity detected in the selected time window. Cross-org
                    monitoring is working normally.
                  </p>
                </div>
              )}
            {correlationData &&
              sortedCorrelations.length === 0 &&
              (riskFilter || orgFilter || actorType !== 'all') && (
                <div className={styles.emptyState}>
                  No actors found matching the current filters
                </div>
              )}
            {sortedCorrelations.length > 0 && (
              <DataTable<CrossOrgCorrelation>
                columns={correlationColumnsWithActions}
                data={sortedCorrelations}
                rowKey={(row) => row.actor}
                onRowClick={(row) => {
                  if (selectedActor === row.actor) {
                    setSelectedActor(null);
                    setActor('');
                    setSearchInput('');
                  } else {
                    setSelectedActor(row.actor);
                    setActor(row.actor);
                    setSearchInput(row.actor);
                  }
                }}
                emptyMessage="No cross-org correlations found"
              />
            )}
          </div>
        )}

        {tab === 'timeline' && (
          <div className={styles.section}>
            {loadingTimeline && <Spinner />}
            {timelineError && (
              <ErrorBanner
                message="Failed to load timeline"
                onRetry={() => void refetchTimeline()}
              />
            )}
            {timelineData && timelineData.events.length === 0 && (
              <div className={styles.emptyState}>
                {actor ? `No events found for ${actor}` : 'No cross-org events found'}
              </div>
            )}
            {timelineData && timelineData.events.length > 0 && (
              <>
                <DataTable<CrossOrgTimelineEvent>
                  columns={timelineColumns}
                  data={timelineData.events}
                  rowKey={(event) => event.id}
                  emptyMessage="No cross-org events found"
                />
                {timelinePages > 1 && (
                  <div className={styles.pagination}>
                    <Button
                      size="sm"
                      disabled={timelinePage <= 1}
                      onClick={() => setTimelinePage((p) => p - 1)}
                    >
                      ← Prev
                    </Button>
                    <span className={styles.pageInfo}>
                      Page {timelinePage} of {timelinePages}
                    </span>
                    <Button
                      size="sm"
                      disabled={timelinePage >= timelinePages}
                      onClick={() => setTimelinePage((p) => p + 1)}
                    >
                      Next →
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* AC-4: Enhanced detail slide-out panel */}
      <div
        className={[styles.splitPanel, selectedActor && styles.splitPanelOpen]
          .filter(Boolean)
          .join(' ')}
      >
        {selectedActor && (
          <>
            <div className={styles.panelHeader}>
              <div className={styles.panelTitle}>{selectedActor}</div>
              <button className={styles.panelClose} onClick={() => setSelectedActor(null)}>
                &#215;
              </button>
            </div>

            {/* Risk score badge at top */}
            {selectedCorrelation && (
              <div className={styles.panelRiskScore}>
                <Label variant={riskLabelVariant(getRiskTier(selectedCorrelation.risk_score))}>
                  {riskTierLabel(getRiskTier(selectedCorrelation.risk_score))} Risk (
                  {selectedCorrelation.risk_score})
                </Label>
              </div>
            )}

            {loadingDetail && <Spinner />}

            {actorDetail && (
              <>
                <div className={styles.panelSummary}>
                  <Label variant="accent" title="Number of organizations this actor has accessed">
                    {actorDetail.org_count} orgs
                  </Label>
                  <Label variant="muted" title="Total events across all organizations">
                    {actorDetail.total_events} events
                  </Label>
                  <Label variant="muted" title="Time window for the activity summary">
                    Last {actorDetail.days} days
                  </Label>
                </div>

                {/* AC-4: Risk Factors section */}
                {selectedCorrelation && (
                  <div className={styles.panelSection}>
                    <div className={styles.panelSectionTitle}>Risk Factors</div>
                    {getRiskFactors(selectedCorrelation).length > 0 ? (
                      <ul className={styles.riskFactorList}>
                        {getRiskFactors(selectedCorrelation).map((factor) => (
                          <li key={factor} className={styles.riskFactorItem}>
                            {factor}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className={styles.muted}>No elevated risk factors detected</p>
                    )}
                  </div>
                )}

                <div className={styles.panelSection}>
                  <div className={styles.panelSectionTitle}>Activity by Organization</div>
                  {actorDetail.organizations.map((org) => {
                    const events = actorDetail.timeline_by_org[org] ?? [];
                    const ips = [...new Set(events.map((e) => e.source_ip).filter(Boolean))];
                    const countries = [
                      ...new Set(events.map((e) => e.geo_country_code).filter(Boolean)),
                    ];
                    const actions = [...new Set(events.map((e) => e.action))];
                    return (
                      <div key={org} className={styles.orgSection}>
                        <div className={styles.orgSectionHeader}>
                          <span className={styles.orgName}>{org}</span>
                          <span className={styles.orgEventCount}>{events.length} events</span>
                        </div>
                        <div className={styles.orgDetails}>
                          {ips.length > 0 && (
                            <div className={styles.orgDetailRow}>
                              <span className={styles.orgDetailLabel}>IPs</span>
                              <span>{ips.join(', ')}</span>
                            </div>
                          )}
                          {countries.length > 0 && (
                            <div className={styles.orgDetailRow}>
                              <span className={styles.orgDetailLabel}>Countries</span>
                              <span>{countries.join(', ')}</span>
                            </div>
                          )}
                          <div className={styles.orgDetailRow}>
                            <span className={styles.orgDetailLabel}>Actions</span>
                            <span className={styles.actionList}>
                              {actions.slice(0, 5).map((a) => (
                                <code
                                  key={a}
                                  className={`${styles.actionCode} ${SENSITIVE_ACTIONS.includes(a) ? styles.sensitiveAction : ''}`}
                                >
                                  {a}
                                </code>
                              ))}
                              {actions.length > 5 && (
                                <span className={styles.muted}>+{actions.length - 5} more</span>
                              )}
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* AC-4: Guided Actions section */}
                <div className={styles.panelSection}>
                  <div className={styles.panelSectionTitle}>Guided Actions</div>
                  <div className={styles.panelActions}>
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() =>
                        navigate(`/threats/open?actor=${encodeURIComponent(selectedActor)}`)
                      }
                    >
                      Investigate in Threats
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => {
                        setTab('timeline');
                        setSearchInput(selectedActor);
                        setActor(selectedActor);
                        setTimelinePage(1);
                      }}
                    >
                      View Timeline
                    </Button>
                    <a
                      href={`https://github.com/${encodeURIComponent(selectedActor)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={styles.externalLink}
                    >
                      <Button size="sm">View on GitHub ↗</Button>
                    </a>
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
