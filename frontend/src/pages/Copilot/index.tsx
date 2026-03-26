import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import { getSeatUtilizationReport } from '../../api/reports';
import { MetricCard } from '../../components/primitives/MetricCard';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Copilot.module.css';

interface InactiveSeat {
  user: string;
  assigned: string;
  lastActivity: string;
  daysInactive: number;
}

const DEMO_INACTIVE: InactiveSeat[] = [
  { user: 'contractor-exit1', assigned: 'Sep 12, 2025', lastActivity: 'Nov 3, 2025', daysInactive: 128 },
  { user: 'former-intern', assigned: 'Jun 1, 2025', lastActivity: 'Aug 31, 2025', daysInactive: 191 },
  { user: 'rarely-uses', assigned: 'Jan 15, 2025', lastActivity: 'Feb 8, 2026', daysInactive: 30 },
];

const LANGUAGES = [
  { lang: 'TypeScript', pct: 38, color: '#3fb950' },
  { lang: 'Python', pct: 34, color: '#3fb950' },
  { lang: 'Go', pct: 29, color: '#26a641' },
  { lang: 'Java', pct: 21, color: '#d29922' },
  { lang: 'C++', pct: 14, color: '#f85149' },
];

export function CopilotPage() {
  const qc = useQueryClient();
  const { isLoading, isError, refetch } = useQuery({
    queryKey: ['reports', 'seat-util'],
    queryFn: () => getSeatUtilizationReport({ window: '30d' }),
  });

  const revokeMutation = useMutation({
    mutationFn: (user: string) => api.delete<void>(`/admin/copilot/seats/${encodeURIComponent(user)}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['reports'] }); },
  });

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>Copilot Insights</div>
      <div className={styles.pageSub}>
        GitHub Copilot adoption, seat utilization, and correlation with delivery outcomes
      </div>

      {/* Seat waste alert */}
      <div className={styles.wasteAlert}>
        <svg width="16" height="16" fill="var(--danger)" viewBox="0 0 16 16" style={{ flexShrink: 0, marginTop: 2 }}>
          <path d="M6.457 1.047c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0114.082 15H1.918a1.75 1.75 0 01-1.543-2.575zm1.763.707a.25.25 0 00-.44 0L1.698 13.132a.25.25 0 00.22.368h12.164a.25.25 0 00.22-.368zM9 11a1 1 0 11-2 0 1 1 0 012 0zM8 5.25a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0V6A.75.75 0 018 5.25z" />
        </svg>
        <div className={styles.wasteBody}>
          <div className={styles.wasteTitle}>Seat waste detected — $1,178/month in unused licenses</div>
          <div className={styles.wasteDesc}>
            <strong>38 inactive seats</strong> (30+ days no activity) + <strong>24 never-used seats</strong> ={' '}
            <strong style={{ color: 'var(--danger)' }}>62 of 200 seats</strong> producing no value.
            At $19/seat/month: <strong style={{ color: 'var(--danger)' }}>$1,178/month ($14,136/year)</strong>.
          </div>
        </div>
        <Button size="sm" variant="danger" style={{ flexShrink: 0 }}>Export inactive list</Button>
      </div>

      {isError && <ErrorBanner message="Failed to load Copilot data" onRetry={refetch} />}
      {isLoading && <Spinner />}

      <div className={styles.metricStrip}>
        <MetricCard value="28.5%" label="Acceptance rate (7d avg)" delta="↑ 1.2pp vs prev 7d" deltaDir="up" />
        <MetricCard value="142 / 200" label="Active / total seats" delta="71% utilization" deltaDir="neutral" />
        <MetricCard value="62" label="Inactive + never used" delta="$1,178/mo cost" deltaDir="down" accent />
        <MetricCard value="4,821" label="Lines accepted (today)" delta="↑ 12% vs 7d avg" deltaDir="up" />
        <MetricCard value="312" label="Chat turns (today)" delta="— steady" deltaDir="neutral" />
      </div>

      <div className={styles.grid2}>
        <div className={styles.chartWrap}>
          <div className={styles.chartTitle}>
            Acceptance rate — 7-day rolling avg{' '}
            <span className={styles.chartSub}>(smooths weekends &amp; holidays)</span>
          </div>
          <svg width="100%" height="110" viewBox="0 0 400 90" preserveAspectRatio="none">
            <defs><linearGradient id="gr-acc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#bc8cff" stopOpacity=".25"/><stop offset="100%" stopColor="#bc8cff" stopOpacity="0"/></linearGradient></defs>
            <polygon points="0,65 28,60 56,55 84,62 112,50 140,42 168,46 196,40 224,52 252,36 280,32 308,44 336,38 364,42 400,36 400,90 0,90" fill="url(#gr-acc)"/>
            <polyline points="0,65 28,60 56,55 84,62 112,50 140,42 168,46 196,40 224,52 252,36 280,32 308,44 336,38 364,42 400,36" fill="none" stroke="#bc8cff" strokeWidth="2"/>
            <line x1="0" y1="45" x2="400" y2="45" stroke="#3fb950" strokeWidth="1" strokeDasharray="6,3" opacity=".5"/>
            <text x="2" y="43" fontSize="9" fill="#3fb950">25% good</text>
            <text x="2" y="88" fontSize="9" fill="#6e7681">Jan 1</text><text x="355" y="88" fontSize="9" fill="#6e7681">Mar 10</text>
          </svg>
        </div>
        <div className={styles.chartWrap}>
          <div className={styles.chartTitle}>Seat utilization — active / inactive / never used</div>
          <svg width="100%" height="110" viewBox="0 0 400 90" preserveAspectRatio="none">
            <polyline points="0,50 50,48 100,44 150,40 200,36 250,30 300,26 350,22 400,20" fill="none" stroke="#58a6ff" strokeWidth="2"/>
            <polyline points="0,28 50,30 100,33 150,36 200,42 250,46 300,50 350,52 400,54" fill="none" stroke="#d29922" strokeWidth="1.5"/>
            <polyline points="0,60 50,62 100,62 150,64 200,66 250,64 300,62 350,60 400,58" fill="none" stroke="#f85149" strokeWidth="1.5"/>
            <text x="5" y="88" fontSize="9" fill="#6e7681">Oct</text>
            <text x="185" y="88" fontSize="9" fill="#6e7681">Jan</text>
            <text x="370" y="88" fontSize="9" fill="#6e7681">Mar</text>
          </svg>
          <div className={styles.legend}>
            <span><span style={{ color: '#58a6ff' }}>━</span> Active</span>
            <span><span style={{ color: '#d29922' }}>━</span> Inactive 30d+</span>
            <span><span style={{ color: '#f85149' }}>━</span> Never used</span>
          </div>
        </div>
      </div>

      <div className={styles.grid2}>
        <Card>
          <CardHeader>Acceptance rate by language</CardHeader>
          <div className={styles.langBars}>
            {LANGUAGES.map((l) => (
              <div key={l.lang} className={styles.langRow}>
                <span className={styles.langName}>{l.lang}</span>
                <div className={styles.langTrack}>
                  <div style={{ width: `${l.pct}%`, height: '100%', background: l.color, borderRadius: 4 }} />
                </div>
                <span className={styles.langPct}>{l.pct}%</span>
              </div>
            ))}
          </div>
          <div className={styles.langNote}>Low C++ acceptance rate may reflect model quality gaps</div>
        </Card>
        <Card>
          <CardHeader>Correlation insight</CardHeader>
          <div className={styles.insightNote}>Copilot adoption vs. delivery outcomes — correlation, not causation</div>
          <div className={styles.insights}>
            <div className={styles.insightSuccess}>
              <span>↑</span>
              <div>
                <div className={styles.insightTitle} style={{ color: 'var(--success)' }}>Acceptance rate ↑ + PR cycle time ↓</div>
                <div className={styles.insightBody}>As 7d acceptance rate rose from 18% → 28%, median PR cycle time dropped from 4.8h → 3.2h.</div>
              </div>
            </div>
            <div className={styles.insightWarn}>
              <span>→</span>
              <div>
                <div className={styles.insightTitle} style={{ color: 'var(--attention)' }}>Acceptance rate ↑ but issue quality flat</div>
                <div className={styles.insightBody}>Issue lifespan and stale count unchanged.</div>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <div className={styles.sectionTitle}>Inactive seats — action required (30+ days)</div>
      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>User</th>
              <th>Seat assigned</th>
              <th>Last activity</th>
              <th>Days inactive</th>
              <th>Monthly cost</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {DEMO_INACTIVE.map((s) => (
              <tr key={s.user}>
                <td><span style={{ color: 'var(--done)', fontWeight: 500 }}>@{s.user}</span></td>
                <td style={{ color: 'var(--fg-muted)' }}>{s.assigned}</td>
                <td style={{ color: 'var(--fg-muted)' }}>{s.lastActivity}</td>
                <td><Label variant={s.daysInactive > 90 ? 'danger' : 'attention'}>{s.daysInactive} days</Label></td>
                <td style={{ color: 'var(--danger)', fontVariantNumeric: 'tabular-nums' }}>$19</td>
                <td>
                  <Button size="sm" onClick={() => revokeMutation.mutate(s.user)}>
                    {s.daysInactive < 60 ? 'Review' : 'Revoke'}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
