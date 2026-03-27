import { Card, CardHeader } from '../../components/primitives/Card';
import { Button } from '../../components/primitives/Button';
import {
  ADOPTION_TIERS,
  TOTAL_ADOPTION,
  POWER_USERS,
  FEATURE_ADOPTION,
  MINIMAL_USERS,
} from './copilotData';
import styles from './Copilot.module.css';

export function AdoptionPane() {
  return (
    <>
      {/* Adoption tier cards */}
      <div className={styles.sectionTitle}>Adoption tiers</div>
      <div className={styles.tierGrid}>
        {ADOPTION_TIERS.map((tier) => (
          <div
            key={tier.id}
            className={styles.tierCard}
            style={{ borderTopColor: tier.color }}
          >
            <div className={styles.tierCount} style={{ color: tier.color }}>
              {tier.count}
            </div>
            <div className={styles.tierLabel}>{tier.label}</div>
            <div className={styles.tierDesc}>{tier.desc}</div>
          </div>
        ))}
      </div>

      {/* Stacked progress bar */}
      <div className={styles.stackedBarContainer}>
        <div className={styles.stackedBar}>
          {ADOPTION_TIERS.map((tier) => (
            <div
              key={tier.id}
              className={styles.stackedSegment}
              style={{
                width: `${(tier.count / TOTAL_ADOPTION) * 100}%`,
                background: tier.color,
              }}
              title={`${tier.label}: ${tier.count} (${Math.round((tier.count / TOTAL_ADOPTION) * 100)}%)`}
            />
          ))}
        </div>
        <div className={styles.stackedLegend}>
          {ADOPTION_TIERS.map((tier) => (
            <div key={tier.id} className={styles.stackedLegendItem}>
              <span
                className={styles.stackedLegendDot}
                style={{ background: tier.color }}
              />
              {tier.label} ({Math.round((tier.count / TOTAL_ADOPTION) * 100)}%)
            </div>
          ))}
        </div>
      </div>

      {/* Daily power users table */}
      <Card style={{ marginBottom: 20 }}>
        <CardHeader>Daily power users</CardHeader>
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Team</th>
                <th>Streak (days)</th>
                <th>Accept rate</th>
              </tr>
            </thead>
            <tbody>
              {POWER_USERS.map((u) => (
                <tr key={u.user}>
                  <td style={{ fontWeight: 500 }}>{u.user}</td>
                  <td style={{ color: 'var(--fg-muted)' }}>{u.team}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{u.streak}d</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--success)' }}>
                    {u.acceptRate}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className={styles.grid2}>
        {/* Feature adoption gaps */}
        <Card>
          <CardHeader>Feature adoption gaps</CardHeader>
          <div className={styles.langBars}>
            {FEATURE_ADOPTION.map((f) => (
              <div key={f.feature} className={styles.langRow}>
                <span className={styles.langName} style={{ width: 120 }}>
                  {f.feature}
                </span>
                <div className={styles.langTrack}>
                  <div
                    style={{
                      width: `${f.pct}%`,
                      height: '100%',
                      background: f.color,
                      borderRadius: 4,
                    }}
                  />
                </div>
                <span className={styles.langPct}>{f.pct}%</span>
              </div>
            ))}
          </div>
        </Card>

        {/* CCR impact comparison */}
        <Card>
          <CardHeader>Copilot impact on cycle time</CardHeader>
          <div className={styles.ccrGrid}>
            <div className={styles.ccrBox}>
              <div className={styles.ccrLabel}>With Copilot</div>
              <div className={styles.ccrValue} style={{ color: 'var(--success)' }}>
                2.8h
              </div>
              <div className={styles.ccrSub}>avg cycle time</div>
            </div>
            <div className={styles.ccrDivider}>
              <div className={styles.ccrDelta}>↓ 41% faster</div>
            </div>
            <div className={styles.ccrBox}>
              <div className={styles.ccrLabel}>Without Copilot</div>
              <div className={styles.ccrValue} style={{ color: 'var(--fg-muted)' }}>
                4.7h
              </div>
              <div className={styles.ccrSub}>avg cycle time</div>
            </div>
          </div>
        </Card>
      </div>

      {/* Minimal users — onboarding candidates */}
      <Card style={{ marginBottom: 20 }}>
        <CardHeader>Minimal users — onboarding candidates</CardHeader>
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Team</th>
                <th>Uses (30d)</th>
                <th>Accepted</th>
                <th>Last feature</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {MINIMAL_USERS.map((u) => (
                <tr key={u.user}>
                  <td style={{ fontWeight: 500 }}>{u.user}</td>
                  <td style={{ color: 'var(--fg-muted)' }}>{u.team}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{u.uses}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{u.accepted}</td>
                  <td style={{ color: 'var(--fg-muted)' }}>{u.lastFeature}</td>
                  <td>
                    <Button size="sm">Schedule onboarding</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
