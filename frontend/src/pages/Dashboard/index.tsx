import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { listDetections } from '../../api/detections';
import { listEvents } from '../../api/events';
import { getActionsVolumeReport } from '../../api/reports';
import { getSystemHealth, getRepoHealth, getPatHealth } from '../../api/healthSignals';
import { ContributionCalendar } from '../../components/charts/ContributionCalendar';
import { Card, CardHeader } from '../../components/primitives/Card';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Spinner } from '../../components/primitives/Spinner';
import { ExecutiveView } from './ExecutiveView';
import { SecurityView } from './SecurityView';
import { CiCdView } from './CiCdView';
import { useOrg } from '../../hooks/useOrg';
import type { EventResponse } from '../../types/events';
import type { ActionsVolumeBucket } from '../../types/reports';
import { formatRelative } from '../../utils/dates';
import styles from './Dashboard.module.css';

type DashboardView = 'operations' | 'executive' | 'security' | 'cicd';

function ClickableValue({
  children,
  onClick,
  label,
}: {
  children: React.ReactNode;
  onClick: () => void;
  label: string;
}) {
  return (
    <span
      role="button"
      tabIndex={0}
      aria-label={label}
      className={styles.clickableValue}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
    >
      {children}
    </span>
  );
}
function StatPill({
  value,
  label,
  variant,
  onClick,
  helpText,
}: {
  value: string;
  label: string;
  variant?: 'danger' | 'success' | 'accent' | 'done';
  onClick?: () => void;
  helpText?: string;
}) {
  return (
    <div
      className={[styles.pill, variant && styles[variant], onClick && styles.pillClickable]
        .filter(Boolean)
        .join(' ')}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      aria-label={onClick ? `${value} ${label}` : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      <span className={styles.pillVal}>{value}</span>&nbsp;{label}
      {helpText && (
        <span className={styles.helpIcon} title={helpText} aria-label={`Help: ${label}`}>
          ⓘ
        </span>
      )}
      {onClick && (
        <span className={styles.pillArrow} aria-hidden="true">
          →
        </span>
      )}
    </div>
  );
}

function eventTypeClass(action: string): 'security' | 'platform' | 'warning' | 'info' {
  const a = action.toLowerCase();
  if (
    a.includes('delete') ||
    a.includes('destroy') ||
    a.includes('visibility') ||
    a.includes('branch_protection') ||
    a.includes('pat') ||
    a.includes('deploy_key') ||
    a.includes('outside_collaborator')
  )
    return 'security';
  if (a.includes('workflow') || a.includes('push') || a.includes('deploy')) return 'platform';
  if (a.includes('failed') || a.includes('error')) return 'warning';
  return 'info';
}

function EventFeedItem({ event }: { event: EventResponse }) {
  const typeClass = eventTypeClass(event.action);
  const context = event.org ? ` · ${event.org}` : '';
  return (
    <div className={styles.tlItem}>
      <div className={[styles.tlNode, styles[typeClass]].join(' ')} />
      <div className={styles.tlBody}>
        {event.actor && (
          <a href={`/actors/${encodeURIComponent(event.actor)}`} className={styles.mention}>
            @{event.actor}
          </a>
        )}
        {event.actor ? ' · ' : ''}
        <strong>{event.action}</strong>
        {event.repo && (
          <>
            {' '}
            on <strong>{event.repo}</strong>
          </>
        )}
      </div>
      <div className={styles.tlTime}>
        {formatRelative(event.created_at)}
        {context}
      </div>
    </div>
  );
}

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { selectedOrg } = useOrg();
  const [searchParams, setSearchParams] = useSearchParams();

  const VALID_VIEWS: DashboardView[] = ['operations', 'executive', 'security', 'cicd'];
  const rawView = searchParams.get('view') ?? 'operations';
  const view: DashboardView = VALID_VIEWS.includes(rawView as DashboardView)
    ? (rawView as DashboardView)
    : 'operations';

  function setView(v: DashboardView) {
    setSearchParams(v === 'operations' ? {} : { view: v }, { replace: true });
  }

  const orgLabel = !selectedOrg || selectedOrg === 'all' ? 'All organizations' : selectedOrg;

  const orgParam = selectedOrg && selectedOrg !== 'all' ? selectedOrg : undefined;

  const {
    data: detections,
  } = useQuery({
    queryKey: ['detections', 'open', selectedOrg],
    queryFn: () => listDetections({ status: 'open', org: orgParam, page_size: 100 }),
    staleTime: 5 * 60 * 1000,
  });

  const { data: events, isLoading: loadingEvents } = useQuery({
    queryKey: ['events', 'recent', selectedOrg],
    queryFn: () => listEvents({ page_size: 10, sort: 'created_at_desc', org: orgParam }),
    staleTime: 5 * 60 * 1000,
  });

  // Fetch a larger page of events for the heatmap (up to 500 most recent)
  const { data: calendarEvents } = useQuery({
    queryKey: ['events', 'calendar', selectedOrg],
    queryFn: () => listEvents({ page_size: 500, sort: 'created_at_desc', org: orgParam }),
    staleTime: 5 * 60 * 1000,
  });

  // Fetch actions volume data for workflow success metrics
  const { data: actionsReport } = useQuery({
    queryKey: ['reports', 'actions-volume-dashboard', selectedOrg],
    queryFn: () => getActionsVolumeReport({ window_days: 7, granularity: 'daily', org: orgParam }),
    staleTime: 5 * 60 * 1000,
  });

  // Fetch repo health for ops summary
  const { data: repoHealth } = useQuery({
    queryKey: ['health-signals', 'repo-health-ops'],
    queryFn: () => getRepoHealth(),
    staleTime: 5 * 60 * 1000,
  });

  // Fetch PAT health for ops summary
  const { data: patHealth } = useQuery({
    queryKey: ['health-signals', 'pat-health-ops'],
    queryFn: () => getPatHealth(),
    staleTime: 5 * 60 * 1000,
  });

  // Fetch system health for ingestion banner
  const { data: systemHealth } = useQuery({
    queryKey: ['health-signals', 'system-dashboard'],
    queryFn: getSystemHealth,
    staleTime: 5 * 60 * 1000,
  });

  // Derive workflow metrics from actions volume data
  const actionsBuckets = (actionsReport?.data ?? []) as unknown as ActionsVolumeBucket[];
  const totalWorkflowRuns = actionsBuckets.reduce(
    (sum, b) => sum + (b.workflow_runs_total ?? 0),
    0,
  );
  const succeededWorkflowRuns = actionsBuckets.reduce(
    (sum, b) => sum + (b.workflow_runs_succeeded ?? 0),
    0,
  );
  const failedWorkflowRuns = actionsBuckets.reduce(
    (sum, b) => sum + (b.workflow_runs_failed ?? 0),
    0,
  );
  const workflowSuccessRate =
    totalWorkflowRuns > 0 ? ((succeededWorkflowRuns / totalWorkflowRuns) * 100).toFixed(1) : null;

  // Bucket calendar events by day
  const calendarData = (() => {
    if (!calendarEvents?.items.length) return undefined;
    const dayMap = new Map<string, { count: number; hasAlert: boolean }>();
    for (const e of calendarEvents.items) {
      const day = e.created_at.slice(0, 10);
      const existing = dayMap.get(day) ?? { count: 0, hasAlert: false };
      dayMap.set(day, {
        count: existing.count + 1,
        hasAlert: existing.hasAlert || eventTypeClass(e.action) === 'security',
      });
    }
    const maxCount = Math.max(...[...dayMap.values()].map((v) => v.count), 1);
    return [...dayMap.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, { count, hasAlert }]) => ({
        date,
        level: Math.min(4, Math.ceil((count / maxCount) * 4)) as 0 | 1 | 2 | 3 | 4,
        alert: hasAlert,
      }));
  })();

  const openThreats = detections?.total ?? 0;

  const eventTotal = events?.total ?? 0;
  const eventCountLabel = formatCount(eventTotal);

  const uniqueActors = new Set((calendarEvents?.items ?? []).map((e) => e.actor).filter(Boolean))
    .size;

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Dashboard · {orgLabel}</div>
      <div className={styles.pageSub}>
        {systemHealth?.last_event_at
          ? `Last synced: ${formatRelative(systemHealth.last_event_at)}`
          : 'Activity across your organizations'}
      </div>

      <div className={styles.viewToggle}>
        <button
          className={[styles.viewBtn, view === 'operations' && styles.viewActive]
            .filter(Boolean)
            .join(' ')}
          onClick={() => setView('operations')}
        >
          Operations
        </button>
        <button
          className={[styles.viewBtn, view === 'executive' && styles.viewActive]
            .filter(Boolean)
            .join(' ')}
          onClick={() => setView('executive')}
        >
          Executive
        </button>
        <button
          className={[styles.viewBtn, view === 'security' && styles.viewActive]
            .filter(Boolean)
            .join(' ')}
          onClick={() => setView('security')}
        >
          Security Engineering
        </button>
        <button
          className={[styles.viewBtn, view === 'cicd' && styles.viewActive]
            .filter(Boolean)
            .join(' ')}
          onClick={() => setView('cicd')}
        >
          CI/CD
        </button>
      </div>

      {view === 'executive' ? (
        <ExecutiveView />
      ) : view === 'security' ? (
        <SecurityView />
      ) : view === 'cicd' ? (
        <CiCdView />
      ) : (
        <>
          {systemHealth != null && (
            <div
              className={[styles.systemHealthBar, systemHealth.gap_detected && styles.healthWarning]
                .filter(Boolean)
                .join(' ')}
            >
              <span
                className={[
                  styles.systemHealthDot,
                  systemHealth.gap_detected ? styles.warn : styles.ok,
                ].join(' ')}
              />
              {systemHealth.gap_detected ? (
                <span>
                  Ingestion gap detected
                  {systemHealth.gap_duration_minutes != null && (
                    <> — {systemHealth.gap_duration_minutes}m of missing data</>
                  )}
                </span>
              ) : (
                <span>
                  System healthy
                  {systemHealth.last_event_at && (
                    <> · Last event: {formatRelative(systemHealth.last_event_at)}</>
                  )}
                </span>
              )}
            </div>
          )}

          <div className={styles.pills}>
            <StatPill
              value={eventCountLabel || '—'}
              label="total events"
              helpText="Total audit log events stored across all orgs. Source: events table."
              onClick={() => navigate('/events')}
            />
            <StatPill
              value={workflowSuccessRate != null ? `${workflowSuccessRate}%` : '—'}
              label="pipeline success"
              helpText="7-day Actions workflow success rate. Calculated from workflow_run.completed events."
              variant={
                workflowSuccessRate != null && parseFloat(workflowSuccessRate) >= 90
                  ? 'success'
                  : undefined
              }
              onClick={() => navigate('/velocity')}
            />
            <StatPill
              value={String(uniqueActors || '—')}
              label="active devs"
              variant="done"
              helpText="Unique human actors (non-bot) seen in audit log events over the last 30 days."
              onClick={() => navigate('/devactivity')}
            />
            <StatPill
              value="—"
              label="API calls (24h)"
              helpText="GitHub API usage from usage reports. Not yet available."
              onClick={() => navigate('/reports')}
            />
          </div>

          {systemHealth != null && systemHealth.gap_detected && (
            <div className={styles.ingestionBanner}>
              <span className={styles.ingestionIcon}>⚠</span>
              <span>
                Data ingestion gap detected
                {systemHealth.gap_duration_minutes != null && (
                  <> — {systemHealth.gap_duration_minutes} minutes of missing data</>
                )}
                . Some health signals may be incomplete.
              </span>
            </div>
          )}

          {/* Operations Summary row */}
          <div className={styles.cardGrid}>
            <MetricCard
              value={String(repoHealth?.stale.length ?? '—')}
              label="Stale repos"
              helpText="Repositories with no activity in the last 90 days."
              to="/health"
            />
            <MetricCard
              value={String(patHealth?.summary.stale_90d_count ?? '—')}
              label="Stale PATs"
              helpText="Personal access tokens with no use in the last 90 days."
              to="/health"
            />
            <MetricCard
              value={String(patHealth?.summary.no_expiry_count ?? '—')}
              label="PATs without expiry"
              helpText="Personal access tokens with no expiration date set."
              accent={(patHealth?.summary.no_expiry_count ?? 0) > 0}
              to="/health"
            />
            <MetricCard
              value={String(uniqueActors || '—')}
              label="Active devs"
              helpText="Unique human actors seen in audit log events over the last 30 days."
              to="/devactivity"
            />
          </div>

          <Card className={styles.calCard}>
            <CardHeader
              actions={
                <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span
                    style={{
                      width: 10,
                      height: 10,
                      background: 'rgba(248,81,73,0.8)',
                      borderRadius: 2,
                      display: 'inline-block',
                    }}
                  />
                  Security&nbsp;
                  <span
                    style={{
                      width: 10,
                      height: 10,
                      background: '#39d353',
                      borderRadius: 2,
                      display: 'inline-block',
                    }}
                  />
                  Platform
                </span>
              }
            >
              Activity heatmap — last 13 weeks
            </CardHeader>
            <ContributionCalendar data={calendarData} />
          </Card>

          <div className={styles.grid}>
            <div className={styles.flex1}>
              <div className={styles.sectionTitle}>Activity feed</div>
              <div className={styles.timeline}>
                {loadingEvents && <Spinner />}
                {(events?.items ?? []).map((event) => (
                  <EventFeedItem key={event.id} event={event} />
                ))}
                {!loadingEvents && (events?.items ?? []).length === 0 && (
                  <div style={{ color: 'var(--fg-muted)', padding: '12px 0' }}>
                    No recent events
                  </div>
                )}
              </div>
            </div>

            <div className={styles.sidebar}>
              <Card>
                <CardHeader>Platform alerts</CardHeader>
                <div className={styles.alerts}>
                  <div className={styles.alertRow}>
                    <span
                      className={styles.alertIcon}
                      style={{ color: failedWorkflowRuns > 0 ? 'var(--danger)' : 'var(--success)' }}
                    >
                      {failedWorkflowRuns > 0 ? '⚠' : '✓'}
                    </span>
                    <div>
                      Workflow runs:{' '}
                      <ClickableValue
                        onClick={() => navigate('/velocity')}
                        label={`${succeededWorkflowRuns} succeeded — view velocity`}
                      >
                        <strong>{succeededWorkflowRuns} succeeded</strong>
                      </ClickableValue>
                      ,{' '}
                      <ClickableValue
                        onClick={() => navigate('/velocity')}
                        label={`${failedWorkflowRuns} failed — view velocity`}
                      >
                        <strong>{failedWorkflowRuns} failed</strong>
                      </ClickableValue>
                      {totalWorkflowRuns > 0 ? ` (${workflowSuccessRate}% success)` : ''}
                    </div>
                  </div>
                  <div className={`${styles.alertRow} ${styles.alertBorder}`}>
                    <span className={styles.alertIcon} style={{ color: 'var(--attention)' }}>
                      ⚡
                    </span>
                    <div>
                      Events volume:{' '}
                      <ClickableValue
                        onClick={() => navigate('/events')}
                        label={`${formatCount(calendarEvents?.total ?? 0)} events — view all events`}
                      >
                        <strong>{formatCount(calendarEvents?.total ?? 0)} events</strong>
                      </ClickableValue>{' '}
                      tracked
                    </div>
                  </div>
                  <div className={`${styles.alertRow} ${styles.alertBorder}`}>
                    <span
                      className={styles.alertIcon}
                      style={{ color: openThreats > 0 ? 'var(--attention)' : 'var(--success)' }}
                    >
                      {openThreats > 0 ? '⚠' : '✓'}
                    </span>
                    <div>
                      Active detections:{' '}
                      <ClickableValue
                        onClick={() => navigate('/threats')}
                        label={`${openThreats} investigating — view threats`}
                      >
                        <strong>{openThreats} investigating</strong>
                      </ClickableValue>
                    </div>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
