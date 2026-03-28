import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Button } from '../../components/primitives/Button';
import { Modal } from '../../components/primitives/Modal';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { getCopilotAdoption } from '../../api/copilotMetrics';
import styles from './Copilot.module.css';

type AdoptionModal = 'tier' | 'feature' | 'minimal-user' | null;

export function AdoptionPane() {
  const { data: adoption, isLoading, isError } = useQuery({
    queryKey: ['copilot', 'adoption'],
    queryFn: getCopilotAdoption,
    staleTime: 300_000,
  });

  const tiers = adoption?.tiers ?? [];
  const totalAdoption = adoption?.total_adoption ?? 0;
  const powerUsers = adoption?.power_users ?? [];
  const featureAdoption = adoption?.feature_adoption ?? [];
  const minimalUsers = adoption?.minimal_users ?? [];

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

  const selectedTier = tiers.find((t) => t.id === selectedTierId);
  const selectedFeatureData = featureAdoption.find((f) => f.feature === selectedFeature);
  const selectedMinimalUserData = minimalUsers.find((u) => u.user === selectedMinimalUser);

  return (
    <>
      {adoption?.error && (
        <SampleDataBanner message={adoption.message ?? 'Adoption data is unavailable. Displaying limited data.'} />
      )}

      {isError && <ErrorBanner message="Failed to load adoption data" />}
      {isLoading && <Spinner />}

      {!isLoading && !isError && (
        <>
      {/* Adoption tier cards */}
      <div className={styles.sectionTitle}>Adoption tiers</div>
      <div className={styles.tierGrid}>
        {tiers.map((tier) => (
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
          {tiers.map((tier) => (
            <div
              key={tier.id}
              className={`${styles.stackedSegment} ${styles.stackedSegmentClickable}`}
              style={{
                width: `${totalAdoption > 0 ? (tier.count / totalAdoption) * 100 : 0}%`,
                background: tier.color,
              }}
              title={`${tier.label}: ${tier.count} (${totalAdoption > 0 ? Math.round((tier.count / totalAdoption) * 100) : 0}%)`}
              role="button"
              tabIndex={0}
              onClick={() => openTierModal(tier.id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openTierModal(tier.id); } }}
            />
          ))}
        </div>
        <div className={styles.stackedLegend}>
          {tiers.map((tier) => (
            <div key={tier.id} className={styles.stackedLegendItem}>
              <span
                className={styles.stackedLegendDot}
                style={{ background: tier.color }}
              />
              {tier.label} ({totalAdoption > 0 ? Math.round((tier.count / totalAdoption) * 100) : 0}%)
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
                <th>Days active</th>
                <th>Features used</th>
              </tr>
            </thead>
            <tbody>
              {powerUsers.map((u) => (
                <tr key={u.user}>
                  <td style={{ fontWeight: 500 }}>{u.user}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                    <span
                      className={styles.clickableStat}
                      role="button"
                      tabIndex={0}
                      onClick={() => showToast(u.user)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showToast(u.user); } }}
                    >
                      {u.days_active}d
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
                      {u.features_used}
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
            {featureAdoption.map((f) => (
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

        {/* CCR impact comparison — requires deployment data */}
        <Card>
          <CardHeader>Copilot impact on cycle time</CardHeader>
          <div className={styles.ccrGrid} style={{ opacity: 0.6 }}>
            <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--fg-muted)', fontSize: 13 }}>
              Cycle time correlation requires deployment data. Connect your CI/CD pipeline to see Copilot&apos;s impact on delivery speed.
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
                <th>Days active</th>
                <th>Last feature</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {minimalUsers.map((u) => (
                <tr key={u.user}>
                  <td style={{ fontWeight: 500 }}>{u.user}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                    <span
                      className={styles.clickableStat}
                      role="button"
                      tabIndex={0}
                      onClick={() => openMinimalUserModal(u.user)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openMinimalUserModal(u.user); } }}
                    >
                      {u.days_active}
                    </span>
                  </td>
                  <td style={{ color: 'var(--fg-muted)' }}>{u.last_feature}</td>
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
          ℹ️ Connect the Copilot Metrics API for live per-user data.
        </div>
        {selectedTier && selectedTierId === 'power' && (
          <div style={{ overflowX: 'auto' }}>
            <p style={{ fontSize: 13, color: 'var(--fg-muted)', margin: '0 0 12px' }}>
              {selectedTier.desc} — showing top power users by activity.
            </p>
            <table className={styles.modalTable}>
              <thead>
                <tr>
                  <th>User</th>
                  <th>Days active</th>
                  <th>Features used</th>
                </tr>
              </thead>
              <tbody>
                {powerUsers.map((u) => (
                  <tr key={u.user}>
                    <td style={{ fontWeight: 500 }}>{u.user}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{u.days_active}d</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--success)' }}>{u.features_used}</td>
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
                  <th>Days active</th>
                  <th>Last feature</th>
                </tr>
              </thead>
              <tbody>
                {minimalUsers.map((u) => (
                  <tr key={u.user}>
                    <td style={{ fontWeight: 500 }}>{u.user}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{u.days_active}</td>
                    <td style={{ color: 'var(--fg-muted)' }}>{u.last_feature}</td>
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
              <strong>{selectedTier.count} users</strong> ({totalAdoption > 0 ? Math.round((selectedTier.count / totalAdoption) * 100) : 0}% of total).
              Individual user lists for this tier require the Copilot Metrics API integration.
            </p>
          </div>
        )}
      </Modal>

      {/* Feature adoption detail modal */}
      <Modal open={adoptionModal === 'feature'} onClose={() => setAdoptionModal(null)} title={selectedFeatureData ? `${selectedFeatureData.feature} — adoption details` : 'Feature details'} width={520}>
        <div className={styles.sampleDataNote}>
          ℹ️ Connect the Copilot Metrics API for live per-user data.
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

      {/* Minimal user activity modal */}
      <Modal open={adoptionModal === 'minimal-user'} onClose={() => setAdoptionModal(null)} title={selectedMinimalUserData ? `@${selectedMinimalUserData.user} — Copilot activity` : 'User activity'} width={520}>
        <div className={styles.sampleDataNote}>
          ℹ️ Connect the Copilot Metrics API for live per-user data.
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
                  <td style={{ color: 'var(--fg-muted)' }}>Days active</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{selectedMinimalUserData.days_active}</td>
                </tr>
                <tr>
                  <td style={{ color: 'var(--fg-muted)' }}>Last feature used</td>
                  <td>{selectedMinimalUserData.last_feature}</td>
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
      )}
    </>
  );
}
