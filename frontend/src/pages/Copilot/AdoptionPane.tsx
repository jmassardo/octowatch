import { useState } from 'react';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Button } from '../../components/primitives/Button';
import { Modal } from '../../components/primitives/Modal';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import {
  ADOPTION_TIERS,
  TOTAL_ADOPTION,
  POWER_USERS,
  FEATURE_ADOPTION,
  MINIMAL_USERS,
} from './copilotData';
import styles from './Copilot.module.css';

type AdoptionModal = 'tier' | 'feature' | 'cycle-time' | 'minimal-user' | null;

export function AdoptionPane() {
  const [scheduledUsers, setScheduledUsers] = useState<Record<string, boolean>>({});
  const [adoptionModal, setAdoptionModal] = useState<AdoptionModal>(null);
  const [selectedTierId, setSelectedTierId] = useState<string | null>(null);
  const [selectedFeature, setSelectedFeature] = useState<string | null>(null);
  const [selectedMinimalUser, setSelectedMinimalUser] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  function openTierModal(tierId: string) {
    setSelectedTierId(tierId);
    setAdoptionModal('tier');
  }

  function openFeatureModal(feature: string) {
    setSelectedFeature(feature);
    setAdoptionModal('feature');
  }

  function openMinimalUserModal(user: string) {
    setSelectedMinimalUser(user);
    setAdoptionModal('minimal-user');
  }

  function showToast(user: string) {
    setToastMessage(`View @${user}'s Copilot activity`);
    setTimeout(() => setToastMessage(null), 2500);
  }

  const selectedTier = ADOPTION_TIERS.find((t) => t.id === selectedTierId);
  const selectedFeatureData = FEATURE_ADOPTION.find((f) => f.feature === selectedFeature);
  const selectedMinimalUserData = MINIMAL_USERS.find((u) => u.user === selectedMinimalUser);

  return (
    <>
      <SampleDataBanner message="Adoption data below is illustrative. Requires Copilot Metrics API integration for live data." />

      {/* Adoption tier cards */}
      <div className={styles.sectionTitle}>Adoption tiers</div>
      <div className={styles.tierGrid}>
        {ADOPTION_TIERS.map((tier) => (
          <div
            key={tier.id}
            className={`${styles.tierCard} ${styles.tierCardClickable}`}
            style={{ borderTopColor: tier.color }}
            role="button"
            tabIndex={0}
            onClick={() => openTierModal(tier.id)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openTierModal(tier.id); } }}
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
              className={`${styles.stackedSegment} ${styles.stackedSegmentClickable}`}
              style={{
                width: `${(tier.count / TOTAL_ADOPTION) * 100}%`,
                background: tier.color,
              }}
              title={`${tier.label}: ${tier.count} (${Math.round((tier.count / TOTAL_ADOPTION) * 100)}%)`}
              role="button"
              tabIndex={0}
              onClick={() => openTierModal(tier.id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openTierModal(tier.id); } }}
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
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                    <span
                      className={styles.clickableStat}
                      role="button"
                      tabIndex={0}
                      onClick={() => showToast(u.user)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showToast(u.user); } }}
                    >
                      {u.streak}d
                    </span>
                  </td>
                  <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--success)' }}>
                    <span
                      className={styles.clickableStat}
                      role="button"
                      tabIndex={0}
                      onClick={() => showToast(u.user)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showToast(u.user); } }}
                    >
                      {u.acceptRate}%
                    </span>
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
              <div
                key={f.feature}
                className={`${styles.langRow} ${styles.langRowClickable}`}
                role="button"
                tabIndex={0}
                onClick={() => openFeatureModal(f.feature)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openFeatureModal(f.feature); } }}
              >
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
          <div
            className={`${styles.ccrGrid} ${styles.ccrClickable}`}
            role="button"
            tabIndex={0}
            onClick={() => setAdoptionModal('cycle-time')}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setAdoptionModal('cycle-time'); } }}
          >
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
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                    <span
                      className={styles.clickableStat}
                      role="button"
                      tabIndex={0}
                      onClick={() => openMinimalUserModal(u.user)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openMinimalUserModal(u.user); } }}
                    >
                      {u.uses}
                    </span>
                  </td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                    <span
                      className={styles.clickableStat}
                      role="button"
                      tabIndex={0}
                      onClick={() => openMinimalUserModal(u.user)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openMinimalUserModal(u.user); } }}
                    >
                      {u.accepted}
                    </span>
                  </td>
                  <td style={{ color: 'var(--fg-muted)' }}>{u.lastFeature}</td>
                  <td>
                    <Button
                      size="sm"
                      onClick={() => {
                        const confirmed = window.prompt(`Schedule onboarding for @${u.user}?`);
                        if (confirmed !== null) {
                          setScheduledUsers((prev) => ({ ...prev, [u.user]: true }));
                          setTimeout(() => {
                            setScheduledUsers((prev) => {
                              const next = { ...prev };
                              delete next[u.user];
                              return next;
                            });
                          }, 3000);
                        }
                      }}
                    >
                      {scheduledUsers[u.user] ? 'Scheduled ✓' : 'Schedule onboarding'}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Tier detail modal */}
      <Modal open={adoptionModal === 'tier'} onClose={() => setAdoptionModal(null)} title={selectedTier ? `${selectedTier.label} — ${selectedTier.count} users` : 'Tier details'} width={640}>
        <div className={styles.sampleDataNote}>
          ℹ️ This data is illustrative. Connect the Copilot Metrics API for live per-user data.
        </div>
        {selectedTier && selectedTierId === 'power' && (
          <div style={{ overflowX: 'auto' }}>
            <p style={{ fontSize: 13, color: 'var(--fg-muted)', margin: '0 0 12px' }}>
              {selectedTier.desc} — showing top power users by streak.
            </p>
            <table className={styles.modalTable}>
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
                    <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--success)' }}>{u.acceptRate}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {selectedTier && selectedTierId === 'minimal' && (
          <div style={{ overflowX: 'auto' }}>
            <p style={{ fontSize: 13, color: 'var(--fg-muted)', margin: '0 0 12px' }}>
              {selectedTier.desc} — showing minimal users who may benefit from onboarding.
            </p>
            <table className={styles.modalTable}>
              <thead>
                <tr>
                  <th>User</th>
                  <th>Team</th>
                  <th>Uses (30d)</th>
                  <th>Accepted</th>
                  <th>Last feature</th>
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {selectedTier && selectedTierId !== 'power' && selectedTierId !== 'minimal' && (
          <div>
            <p style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.6, margin: '0 0 12px' }}>
              <strong>{selectedTier.label}</strong>: {selectedTier.desc}
            </p>
            <p style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.6, margin: 0 }}>
              <strong>{selectedTier.count} users</strong> ({Math.round((selectedTier.count / TOTAL_ADOPTION) * 100)}% of total).
              Individual user lists for this tier require the Copilot Metrics API integration.
            </p>
          </div>
        )}
      </Modal>

      {/* Feature adoption detail modal */}
      <Modal open={adoptionModal === 'feature'} onClose={() => setAdoptionModal(null)} title={selectedFeatureData ? `${selectedFeatureData.feature} — adoption details` : 'Feature details'} width={520}>
        <div className={styles.sampleDataNote}>
          ℹ️ This data is illustrative. Connect the Copilot Metrics API for live per-user data.
        </div>
        {selectedFeatureData && (
          <div>
            <p style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.6, margin: '0 0 12px' }}>
              <strong>{selectedFeatureData.feature}</strong> has <strong>{selectedFeatureData.pct}%</strong> adoption across all Copilot users.
            </p>
            <p style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.6, margin: 0 }}>
              Teams with low adoption of this feature can be identified via the Copilot Metrics API.
              Consider targeted enablement sessions for teams below the org-wide average.
            </p>
          </div>
        )}
      </Modal>

      {/* Cycle time comparison modal */}
      <Modal open={adoptionModal === 'cycle-time'} onClose={() => setAdoptionModal(null)} title="Cycle time comparison methodology" width={520}>
        <div className={styles.sampleDataNote}>
          ℹ️ This data is illustrative. Connect the Copilot Metrics API for live per-user data.
        </div>
        <div>
          <p style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.6, margin: '0 0 12px' }}>
            Cycle time is measured from first commit to PR merge. The comparison groups:
          </p>
          <ul style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.8, margin: '0 0 12px', paddingLeft: 20 }}>
            <li><strong>With Copilot (2.8h avg)</strong>: PRs where the author had active Copilot suggestions during the coding session</li>
            <li><strong>Without Copilot (4.7h avg)</strong>: PRs where the author did not use Copilot</li>
          </ul>
          <p style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.6, margin: 0 }}>
            The <strong>41% improvement</strong> is a correlation, not necessarily causation.
            Other factors (developer experience, PR complexity) may contribute. Per-team breakdowns require the Copilot Metrics API.
          </p>
        </div>
      </Modal>

      {/* Minimal user activity modal */}
      <Modal open={adoptionModal === 'minimal-user'} onClose={() => setAdoptionModal(null)} title={selectedMinimalUserData ? `@${selectedMinimalUserData.user} — Copilot activity` : 'User activity'} width={520}>
        <div className={styles.sampleDataNote}>
          ℹ️ This data is illustrative. Connect the Copilot Metrics API for live per-user data.
        </div>
        {selectedMinimalUserData && (
          <div style={{ overflowX: 'auto' }}>
            <table className={styles.modalTable}>
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ color: 'var(--fg-muted)' }}>User</td>
                  <td style={{ fontWeight: 500 }}>@{selectedMinimalUserData.user}</td>
                </tr>
                <tr>
                  <td style={{ color: 'var(--fg-muted)' }}>Team</td>
                  <td>{selectedMinimalUserData.team}</td>
                </tr>
                <tr>
                  <td style={{ color: 'var(--fg-muted)' }}>Uses (30d)</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{selectedMinimalUserData.uses}</td>
                </tr>
                <tr>
                  <td style={{ color: 'var(--fg-muted)' }}>Accepted</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{selectedMinimalUserData.accepted}</td>
                </tr>
                <tr>
                  <td style={{ color: 'var(--fg-muted)' }}>Last feature used</td>
                  <td>{selectedMinimalUserData.lastFeature}</td>
                </tr>
                <tr>
                  <td style={{ color: 'var(--fg-muted)' }}>Acceptance rate</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {selectedMinimalUserData.uses > 0 ? `${Math.round((selectedMinimalUserData.accepted / selectedMinimalUserData.uses) * 100)}%` : '—'}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </Modal>

      {/* Toast popover for power user clicks */}
      {toastMessage && (
        <div className={styles.toastPopover} role="status" aria-live="polite">
          {toastMessage}
        </div>
      )}
    </>
  );
}
