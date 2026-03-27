import { useQuery } from '@tanstack/react-query';
import { listDetections } from '../../api/detections';
import { listEvents } from '../../api/events';
import { getActionsVolumeReport } from '../../api/reports';
import { ContributionCalendar } from '../../components/charts/ContributionCalendar';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import type { EventResponse } from '../../types/events';
import type { ActionsVolumeBucket } from '../../types/reports';
import styles from './Dashboard.module.css';
function StatPill({
  value,
  label,
  variant,
}: {
  value: string;
  label: string;
  variant?: 'danger' | 'success' | 'accent' | 'done';
}) {
  return (
    <div className={[styles.pill, variant && styles[variant]].filter(Boolean).join(' ')}>
      <span className={styles.pillVal}>{value}</span>&nbsp;{label}
    </div>
  );
}

function eventTypeClass(action: string): 'security' | 'platform' | 'warning' | 'info' {
  const a = action.toLowerCase();
  if (a.includes('delete') || a.includes('destroy') || a.includes('visibility') ||
      a.includes('branch_protection') || a.includes('pat') || a.includes('deploy_key') ||
      a.includes('outside_collaborator')) return 'security';
  if (a.includes('workflow') || a.includes('push') || a.includes('deploy')) return 'platform';
  if (a.includes('failed') || a.includes('error')) return 'warning';
  return 'info';
}

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  return `${Math.floor(hours / 24)} days ago`;
}

function EventFeedItem({ event }: { event: EventResponse }) {
  const typeClass = eventTypeClass(event.action);
  const context = event.org ? ` · ${event.org}` : '';
  return (
    <div className={styles.tlItem}>
      <div className={[styles.tlNode, styles[typeClass]].join(' ')} />
      <div className={styles.tlBody}>
        {event.actor && <span className={styles.mention}>@{event.actor}</span>}{event.actor ? ' · ' : ''}
        <strong>{event.action}</strong>
        {event.repo && <> on <strong>{event.repo}</strong></>}
      </div>
      <div className={styles.tlTime}>{formatRelative(event.created_at)}{context}</div>
    </div>
  );
}

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function DashboardPage() {
  const { data: detections, isLoading: loadingThreats, refetch: refetchThreats, isError: threatError } = useQuery({
    queryKey: ['detections', 'open'],
    queryFn: () => listDetections({ status: 'investigating', page_size: 100 }),
  });

  const { data: events, isLoading: loadingEvents } = useQuery({
    queryKey: ['events', 'recent'],
    queryFn: () => listEvents({ page_size: 10, sort: 'created_at_desc' }),
  });

  // Fetch a larger page of events for the heatmap (up to 500 most recent)
  const { data: calendarEvents } = useQuery({
    queryKey: ['events', 'calendar'],
    queryFn: () => listEvents({ page_size: 500, sort: 'created_at_desc' }),
  });

  // Fetch actions volume data for workflow success metrics
  const { data: actionsReport } = useQuery({
    queryKey: ['reports', 'actions-volume-dashboard'],
    queryFn: () => getActionsVolumeReport({ window_days: 7, granularity: 'daily' }),
  });

  // Derive workflow metrics from actions volume data
  const actionsBuckets = (actionsReport?.data ?? []) as unknown as ActionsVolumeBucket[];
  const totalWorkflowRuns = actionsBuckets.reduce((sum, b) => sum + (b.workflow_runs_total ?? 0), 0);
  const succeededWorkflowRuns = actionsBuckets.reduce((sum, b) => sum + (b.workflow_runs_succeeded ?? 0), 0);
  const failedWorkflowRuns = actionsBuckets.reduce((sum, b) => sum + (b.workflow_runs_failed ?? 0), 0);
  const workflowSuccessRate = totalWorkflowRuns > 0
    ? ((succeededWorkflowRuns / totalWorkflowRuns) * 100).toFixed(1)
    : null;

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

  const severityCounts = {
    critical: detections?.items.filter((d) => d.severity === 'critical').length ?? 0,
    high: detections?.items.filter((d) => d.severity === 'high').length ?? 0,
    medium: detections?.items.filter((d) => d.severity === 'medium').length ?? 0,
    low: detections?.items.filter((d) => d.severity === 'low').length ?? 0,
  };

  const eventTotal = events?.total ?? 0;
  const eventCountLabel = eventTotal >= 1000 ? `${(eventTotal / 1000).toFixed(0)}K` : String(eventTotal);

  const uniqueActors = new Set(
    (events?.items ?? []).map((e) => e.actor).filter(Boolean)
  ).size;

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Dashboard</div>
      <div className={styles.pageSub}>
        Activity across your organizations · Updated just now
      </div>

      <div className={styles.pills}>
        <StatPill value={eventCountLabel || '—'} label="events today" />
        <StatPill value={String(openThreats)} label="open threats" variant={openThreats > 0 ? 'danger' : undefined} />
        <StatPill
          value={workflowSuccessRate != null ? `${workflowSuccessRate}%` : '—'}
          label="pipeline success"
          variant={workflowSuccessRate != null && parseFloat(workflowSuccessRate) >= 90 ? 'success' : undefined}
        />
        <StatPill value={String(uniqueActors || '—')} label="active devs" variant="done" />
        <StatPill value={formatCount(calendarEvents?.total ?? 0)} label="total events" variant="accent" />
      </div>

      {threatError && <ErrorBanner message="Could not load threat data" onRetry={refetchThreats} />}

      <Card className={styles.calCard}>
        <CardHeader
          actions={
            <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ width: 10, height: 10, background: 'rgba(248,81,73,0.8)', borderRadius: 2, display: 'inline-block' }} />
              Security&nbsp;
              <span style={{ width: 10, height: 10, background: '#39d353', borderRadius: 2, display: 'inline-block' }} />
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
              <div style={{ color: 'var(--fg-muted)', padding: '12px 0' }}>No recent events</div>
            )}
          </div>
        </div>

        <div className={styles.sidebar}>
          <Card>
            <CardHeader>Open threats by severity</CardHeader>
            {loadingThreats ? (
              <Spinner />
            ) : (
              <div className={styles.sevBars}>
                {[
                  { sev: 'Critical', key: 'critical', color: 'var(--danger)', count: severityCounts.critical },
                  { sev: 'High', key: 'high', color: 'var(--severe)', count: severityCounts.high },
                  { sev: 'Medium', key: 'medium', color: 'var(--attention)', count: severityCounts.medium },
                  { sev: 'Low', key: 'low', color: 'var(--success)', count: severityCounts.low },
                ].map(({ sev, key, color, count }) => {
                  const maxCount = Math.max(severityCounts.critical, severityCounts.high, severityCounts.medium, severityCounts.low, 1);
                  const w = count > 0 ? `${Math.max(8, Math.round((count / maxCount) * 100))}%` : '2px';
                  return (
                    <div key={key} className={styles.sevRow}>
                      <div className={[styles.sevDot, styles[key as 'critical' | 'high' | 'medium' | 'low']].join(' ')} />
                      <span className={styles.sevLbl}>{sev}</span>
                      <div className={styles.sevTrack}>
                        <div style={{ height: '100%', background: color, borderRadius: 4, width: w }} />
                      </div>
                      <span className={styles.sevCount}>{count}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          <Card>
            <CardHeader>Platform alerts</CardHeader>
            <div className={styles.alerts}>
              <div className={styles.alertRow}>
                <span className={styles.alertIcon} style={{ color: failedWorkflowRuns > 0 ? 'var(--danger)' : 'var(--success)' }}>
                  {failedWorkflowRuns > 0 ? '⚠' : '✓'}
                </span>
                <div>
                  Workflow runs: <strong>{succeededWorkflowRuns} succeeded</strong>, <strong>{failedWorkflowRuns} failed</strong>
                  {totalWorkflowRuns > 0 ? ` (${workflowSuccessRate}% success)` : ''}
                </div>
              </div>
              <div className={`${styles.alertRow} ${styles.alertBorder}`}>
                <span className={styles.alertIcon} style={{ color: 'var(--attention)' }}>⚡</span>
                <div>Events volume: <strong>{formatCount(calendarEvents?.total ?? 0)} events</strong> tracked</div>
              </div>
              <div className={`${styles.alertRow} ${styles.alertBorder}`}>
                <span className={styles.alertIcon} style={{ color: openThreats > 0 ? 'var(--attention)' : 'var(--success)' }}>
                  {openThreats > 0 ? '⚠' : '✓'}
                </span>
                <div>Active detections: <strong>{openThreats} investigating</strong></div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}




