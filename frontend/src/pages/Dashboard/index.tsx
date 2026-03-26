import { useQuery } from '@tanstack/react-query';
import { listDetections } from '../../api/detections';
import { listEvents } from '../../api/events';
import { ContributionCalendar } from '../../components/charts/ContributionCalendar';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
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

const FEED = [
  {
    type: 'security',
    body: (
      <>
        <strong>Impossible travel detected</strong> — <span className={styles.mention}>@mal-user99</span> authenticated from{' '}
        <Label variant="danger">US-East</Label> then <Label variant="danger">CN-Beijing</Label> within 4&nbsp;min
      </>
    ),
    time: '2 minutes ago · acme-corp',
  },
  {
    type: 'platform',
    body: (
      <>
        <span className={styles.mention}>@alice</span> merged PR <strong>#4821</strong> into <code>main</code> on{' '}
        <strong>acme/payments-api</strong> · 3&nbsp;workflows triggered
      </>
    ),
    time: '7 minutes ago · acme-corp',
  },
  {
    type: 'warning',
    body: (
      <>
        Workflow failure spike on <strong>acme/infra-deploy</strong> — 6/10 runs failed{' '}
        <Label variant="attention">degraded</Label>
      </>
    ),
    time: '14 minutes ago · acme-corp',
  },
  {
    type: 'security',
    body: (
      <>
        Repo visibility changed to <Label variant="danger">public</Label> —{' '}
        <strong>globex/internal-tools</strong> by <span className={styles.mention}>@bob</span>{' '}
        <Label variant="attention">review required</Label>
      </>
    ),
    time: '31 minutes ago · globex',
  },
  {
    type: 'platform',
    body: (
      <>
        Deploy to <Label variant="success">production</Label> — <strong>acme/checkout-service v2.14.1</strong> by{' '}
        <span className={styles.mention}>@carol</span>
      </>
    ),
    time: '45 minutes ago · acme-corp',
  },
  {
    type: 'security',
    body: (
      <>
        Branch protection rule deleted on <Label variant="danger">main</Label> —{' '}
        <strong>globex/auth-service</strong> by <span className={styles.mention}>@eremin</span>
      </>
    ),
    time: '2 hours ago · globex',
  },
];

export function DashboardPage() {
  const { data: detections, isLoading: loadingThreats, refetch: refetchThreats, isError: threatError } = useQuery({
    queryKey: ['detections', 'open'],
    queryFn: () => listDetections({ status: 'investigating', page_size: 100 }),
  });

  const { data: events } = useQuery({
    queryKey: ['events', 'recent'],
    queryFn: () => listEvents({ page_size: 5, sort: 'created_at_desc' }),
  });

  const openThreats = detections?.total ?? 0;

  const severityCounts = {
    critical: detections?.items.filter((d) => d.severity === 'critical').length ?? 0,
    high: detections?.items.filter((d) => d.severity === 'high').length ?? 0,
    medium: detections?.items.filter((d) => d.severity === 'medium').length ?? 0,
    low: detections?.items.filter((d) => d.severity === 'low').length ?? 0,
  };

  const eventCount = events?.total ?? 0;

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Dashboard</div>
      <div className={styles.pageSub}>
        Activity across your organizations · Updated just now
      </div>

      <div className={styles.pills}>
        <StatPill value={eventCount > 0 ? `${Math.round(eventCount / 1000)}K` : '847K'} label="events today" />
        <StatPill value={String(openThreats || 23)} label="open threats" variant="danger" />
        <StatPill value="94.2%" label="pipeline success" variant="success" />
        <StatPill value="312" label="active devs" variant="done" />
        <StatPill value="1.8M" label="API calls (24h)" variant="accent" />
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
        <ContributionCalendar />
      </Card>

      <div className={styles.grid}>
        <div className={styles.flex1}>
          <div className={styles.sectionTitle}>Activity feed</div>
          <div className={styles.timeline}>
            {FEED.map((item, i) => (
              <div key={i} className={styles.tlItem}>
                <div className={[styles.tlNode, styles[item.type as 'security' | 'platform' | 'warning' | 'info']].join(' ')} />
                <div className={styles.tlBody}>{item.body}</div>
                <div className={styles.tlTime}>{item.time}</div>
              </div>
            ))}
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
                  { sev: 'Critical', key: 'critical', color: 'var(--danger)', count: severityCounts.critical, w: '40%' },
                  { sev: 'High', key: 'high', color: 'var(--severe)', count: severityCounts.high, w: '30%' },
                  { sev: 'Medium', key: 'medium', color: 'var(--attention)', count: severityCounts.medium, w: '22%' },
                  { sev: 'Low', key: 'low', color: 'var(--success)', count: severityCounts.low, w: '18%' },
                ].map(({ sev, key, color, count, w }) => (
                  <div key={key} className={styles.sevRow}>
                    <div className={[styles.sevDot, styles[key as 'critical' | 'high' | 'medium' | 'low']].join(' ')} />
                    <span className={styles.sevLbl}>{sev}</span>
                    <div className={styles.sevTrack}>
                      <div style={{ height: '100%', background: color, borderRadius: 4, width: count > 0 ? w : '2px' }} />
                    </div>
                    <span className={styles.sevCount}>{count}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <CardHeader>Platform alerts</CardHeader>
            <div className={styles.alerts}>
              <div className={styles.alertRow}>
                <span className={styles.alertIcon} style={{ color: 'var(--danger)' }}>↑</span>
                <div>Workflow failure rate <strong>+12%</strong> vs last week — <strong>infra-deploy</strong></div>
              </div>
              <div className={[styles.alertRow, styles.alertBorder].join(' ')}>
                <span className={styles.alertIcon} style={{ color: 'var(--attention)' }}>⚡</span>
                <div>PR cycle time for <strong>platform-team</strong> up to <strong>4.1h avg</strong></div>
              </div>
              <div className={[styles.alertRow, styles.alertBorder].join(' ')}>
                <span className={styles.alertIcon} style={{ color: 'var(--success)' }}>↑</span>
                <div>Deploy frequency <strong>+28%</strong> this sprint — checkout-service</div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
