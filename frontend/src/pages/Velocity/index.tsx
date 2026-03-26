import { useQuery } from '@tanstack/react-query';
import { getActionsVolumeReport } from '../../api/reports';
import { ContributionCalendar } from '../../components/charts/ContributionCalendar';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Velocity.module.css';

const METRICS = [
  { value: '1,247', label: 'PRs merged (30d)', delta: '↑ 8% vs prev period', dir: 'up' as const },
  { value: '18h', label: 'Lead time for changes', delta: 'idea → production', dir: 'neutral' as const, accent: true },
  { value: '3.2h', label: 'PR cycle time (median)', delta: '↑ 0.4h slower', dir: 'down' as const },
  { value: '4.1%', label: 'Change failure rate', delta: '↓ 0.8pp vs last week', dir: 'up' as const },
  { value: '847', label: 'Deployments (30d)', delta: '↑ 28% vs prev period', dir: 'up' as const },
  { value: '94.2%', label: 'Workflow success', delta: '↓ 1.2% vs last week', dir: 'down' as const },
  { value: '23', label: 'WIP (items in flight)', delta: '↑ 4 vs last week', dir: 'down' as const },
  { value: '68%', label: 'Planned work ratio', delta: '32% unplanned', dir: 'neutral' as const },
];

const FAILING_WORKFLOWS = [
  { name: 'deploy-production.yml', repo: 'acme/infra-deploy', rate: '60%', rateVariant: 'danger', lastFailed: '14 min ago', p50: '4m 22s' },
  { name: 'e2e-tests.yml', repo: 'acme/checkout-service', rate: '28%', rateVariant: 'attention', lastFailed: '2h ago', p50: '12m 08s' },
  { name: 'integration-tests.yml', repo: 'globex/auth-service', rate: '15%', rateVariant: 'attention', lastFailed: '5h ago', p50: '8m 41s' },
];

const ACTIVE_REPOS = [
  { repo: 'acme/payments-api', commits: 847, prs: 214, cfr: '2.1%', cfrVariant: 'success', mttr: '38m', contrib: 28 },
  { repo: 'acme/checkout-service', commits: 623, prs: 187, cfr: '1.8%', cfrVariant: 'success', mttr: '22m', contrib: 19 },
  { repo: 'acme/infra-deploy', commits: 412, prs: 98, cfr: '14.3%', cfrVariant: 'danger', mttr: '1h 12m', contrib: 12 },
  { repo: 'globex/auth-service', commits: 318, prs: 76, cfr: '6.2%', cfrVariant: 'attention', mttr: '45m', contrib: 9 },
  { repo: 'globex/api-gateway', commits: 275, prs: 61, cfr: '0%', cfrVariant: 'success', mttr: '—', contrib: 8 },
];

export function VelocityPage() {
  const { isLoading, isError, refetch } = useQuery({
    queryKey: ['reports', 'actions-volume'],
    queryFn: () => getActionsVolumeReport({ window: '30d', granularity: 'daily' }),
  });

  return (
    <div className={styles.page}>
      <div className={styles.titleRow}>
        <div className={styles.pageTitle}>Engineering Velocity</div>
        <div className={styles.doraBadge}>
          ★ Elite
        </div>
      </div>
      <div className={styles.pageSub}>
        Flow metrics, DORA indicators, and delivery throughput — use as conversation starters, not scorecards
      </div>

      <div className={styles.contextCard}>
        <svg width="14" height="14" fill="var(--accent)" viewBox="0 0 16 16" style={{ flexShrink: 0, marginTop: 1 }}>
          <path d="M0 8a8 8 0 1116 0A8 8 0 010 8zm8-6.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM6.5 7.75A.75.75 0 017.25 7h1a.75.75 0 01.75.75v2.75h.25a.75.75 0 010 1.5h-2a.75.75 0 010-1.5h.25v-2h-.25a.75.75 0 01-.75-.75zM8 6a1 1 0 110-2 1 1 0 010 2z" />
        </svg>
        <span>
          Metrics here measure <strong>system behavior</strong>, not individual performance. A metric moving in an
          unexpected direction is a question to investigate, not a judgment to make.
        </span>
      </div>

      {isError && <ErrorBanner message="Failed to load metrics" onRetry={refetch} />}

      <div className={styles.metricStrip}>
        {METRICS.map((m, i) => (
          <MetricCard key={i} value={m.value} label={m.label} delta={m.delta} deltaDir={m.dir} accent={m.accent} />
        ))}
      </div>

      {isLoading && <Spinner />}

      <Card style={{ marginBottom: 20 }}>
        <CardHeader actions={<span style={{ fontWeight: 400 }}>commit + PR + deploy activity</span>}>
          Team contribution calendar — last 13 weeks
        </CardHeader>
        <ContributionCalendar />
      </Card>

      <div className={styles.chartsGrid}>
        <div className={styles.chartWrap}>
          <div className={styles.chartTitle}>Lead time for changes — 14 days <span className={styles.chartSub}>(median + P90)</span></div>
          <svg width="100%" height="110" viewBox="0 0 400 90" preserveAspectRatio="none">
            <defs><linearGradient id="gr-lead" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#58a6ff" stopOpacity=".15"/><stop offset="100%" stopColor="#58a6ff" stopOpacity="0"/></linearGradient></defs>
            <polyline points="0,42 28,38 56,35 84,50 112,30 140,25 168,36 196,28 224,44 252,20 280,16 308,38 336,30 364,42 400,26" fill="none" stroke="#58a6ff" strokeWidth="1.5" strokeDasharray="4,3" opacity=".5"/>
            <polygon points="0,58 28,54 56,48 84,64 112,42 140,35 168,50 196,44 224,58 252,35 280,28 308,52 336,44 364,56 400,40 400,90 0,90" fill="url(#gr-lead)"/>
            <polyline points="0,58 28,54 56,48 84,64 112,42 140,35 168,50 196,44 224,58 252,35 280,28 308,52 336,44 364,56 400,40" fill="none" stroke="#58a6ff" strokeWidth="2"/>
            <text x="2" y="88" fontSize="9" fill="#6e7681">Jan 1</text><text x="355" y="88" fontSize="9" fill="#6e7681">Jan 14</text>
          </svg>
        </div>
        <div className={styles.chartWrap}>
          <div className={styles.chartTitle}>Change failure rate — 14 days</div>
          <svg width="100%" height="110" viewBox="0 0 400 90" preserveAspectRatio="none">
            <defs><linearGradient id="gr-cfr" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f85149" stopOpacity=".2"/><stop offset="100%" stopColor="#f85149" stopOpacity="0"/></linearGradient></defs>
            <polygon points="0,75 28,72 56,70 84,78 112,65 140,60 168,72 196,68 224,75 252,58 280,55 308,70 336,66 364,74 400,62 400,90 0,90" fill="url(#gr-cfr)"/>
            <polyline points="0,75 28,72 56,70 84,78 112,65 140,60 168,72 196,68 224,75 252,58 280,55 308,70 336,66 364,74 400,62" fill="none" stroke="#f85149" strokeWidth="2"/>
            <line x1="0" y1="54" x2="400" y2="54" stroke="#d29922" strokeWidth="1" strokeDasharray="6,3" opacity=".6"/>
            <text x="2" y="52" fontSize="9" fill="#d29922">5% threshold</text>
            <text x="2" y="88" fontSize="9" fill="#6e7681">Jan 1</text><text x="355" y="88" fontSize="9" fill="#6e7681">Jan 14</text>
          </svg>
        </div>
      </div>

      <div className={styles.sectionTitle}>Top failing workflows</div>
      <div className={styles.tableWrap} style={{ marginBottom: 20 }}>
        <table>
          <thead><tr><th>Workflow</th><th>Repository</th><th>Failure rate</th><th>Last failed</th><th>P50 duration</th></tr></thead>
          <tbody>
            {FAILING_WORKFLOWS.map((w) => (
              <tr key={w.name}>
                <td>{w.name}</td>
                <td>{w.repo}</td>
                <td><Label variant={w.rateVariant as 'danger' | 'attention'}>{w.rate}</Label></td>
                <td style={{ color: 'var(--fg-muted)' }}>{w.lastFailed}</td>
                <td style={{ fontVariantNumeric: 'tabular-nums' }}>{w.p50}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={styles.sectionTitle}>Most active repositories — last 30 days</div>
      <div className={styles.tableWrap}>
        <table>
          <thead><tr><th>Repository</th><th>Commits</th><th>PRs merged</th><th>Change failure rate</th><th>MTTR</th><th>Contributors</th></tr></thead>
          <tbody>
            {ACTIVE_REPOS.map((r) => (
              <tr key={r.repo}>
                <td>{r.repo}</td>
                <td style={{ fontVariantNumeric: 'tabular-nums' }}>{r.commits.toLocaleString()}</td>
                <td>{r.prs}</td>
                <td><Label variant={r.cfrVariant as 'success' | 'danger' | 'attention'}>{r.cfr}</Label></td>
                <td>{r.mttr}</td>
                <td>{r.contrib}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
