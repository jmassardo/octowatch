import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Button } from '../../components/primitives/Button';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { Modal } from '../../components/primitives/Modal';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { getCopilotAdoption } from '../../api/copilotMetrics';
import styles from './Copilot.module.css';

type AdoptionModal = 'tier' | 'feature' | 'minimal-user' | null;

interface PowerUser {
  user: string;
  days_active: number;
  features_used: number;
}

interface MinimalUser {
  user: string;
  days_active: number;
  last_feature: string;
}

export function AdoptionPane() {
  const navigate = useNavigate();
  const {
    data: adoption,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['copilot', 'adoption'],
    queryFn: getCopilotAdoption,
    staleTime: 30 * 60 * 1000,
  });

  const tiers = adoption?.tiers ?? [];
  const totalAdoption = adoption?.total_adoption ?? 0;
  const powerUsers = adoption?.power_users ?? [];
  const featureAdoption = adoption?.feature_adoption ?? [];
  const minimalUsers = adoption?.minimal_users ?? [];

  const [adoptionModal, setAdoptionModal] = useState<AdoptionModal>(null);
  const [selectedTierId, setSelectedTierId] = useState<string | null>(null);
  const [selectedFeature, setSelectedFeature] = useState<string | null>(null);
  const [selectedMinimalUser, setSelectedMinimalUser] = useState<string | null>(null);

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

  const selectedTier = tiers.find((t) => t.id === selectedTierId);
  const selectedFeatureData = featureAdoption.find((f) => f.feature === selectedFeature);
  const selectedMinimalUserData = minimalUsers.find((u) => u.user === selectedMinimalUser);

  const powerUserColumns: ColumnDef<PowerUser>[] = [
    {
      key: 'user',
      header: 'User',
      filterable: true,
      helpText: 'GitHub username of the Copilot user. From daily Copilot usage API sync.',
      render: (u) => <span style={{ fontWeight: 500 }}>{u.user}</span>,
      filterValue: (u) => u.user,
    },
    {
      key: 'days_active',
      header: 'Days active',
      sortable: true,
      helpText:
        'Number of days with recorded Copilot activity in the period. From daily usage sync. Power users typically have 20+ active days per month.',
      render: (u) => (
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>
          <span
            className={styles.clickableStat}
            style={{ cursor: 'pointer', textDecoration: 'underline', color: 'var(--accent)' }}
            role="button"
            tabIndex={0}
            onClick={() => navigate(`/actors/${encodeURIComponent(u.user)}`)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                navigate(`/actors/${encodeURIComponent(u.user)}`);
              }
            }}
          >
            {u.days_active}d
          </span>
        </span>
      ),
      sortValue: (u) => u.days_active,
    },
    {
      key: 'features_used',
      header: 'Features used',
      sortable: true,
      helpText:
        'Number of distinct Copilot features used (e.g. completions, chat, CLI). From daily usage sync. More features used indicates deeper adoption.',
      render: (u) => (
        <span style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--success)' }}>
          <span
            className={styles.clickableStat}
            style={{ cursor: 'pointer', textDecoration: 'underline' }}
            role="button"
            tabIndex={0}
            onClick={() => navigate(`/actors/${encodeURIComponent(u.user)}`)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                navigate(`/actors/${encodeURIComponent(u.user)}`);
              }
            }}
          >
            {u.features_used}
          </span>
        </span>
      ),
      sortValue: (u) => u.features_used,
    },
  ];

  const minimalUserColumns: ColumnDef<MinimalUser>[] = [
    {
      key: 'user',
      header: 'User',
      filterable: true,
      helpText: 'GitHub username of the Copilot user. From daily Copilot usage API sync.',
      render: (u) => <span style={{ fontWeight: 500 }}>{u.user}</span>,
      filterValue: (u) => u.user,
    },
    {
      key: 'days_active',
      header: 'Days active',
      sortable: true,
      helpText:
        'Number of days with recorded Copilot activity in the period. From daily usage sync. Users with 0 days may be candidates for seat reclamation.',
      render: (u) => (
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>
          <span
            className={styles.clickableStat}
            role="button"
            tabIndex={0}
            onClick={() => openMinimalUserModal(u.user)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openMinimalUserModal(u.user);
              }
            }}
          >
            {u.days_active}
          </span>
        </span>
      ),
      sortValue: (u) => u.days_active,
    },
    {
      key: 'last_feature',
      header: 'Last feature',
      filterable: true,
      helpText:
        'The most recent Copilot feature used by this user. From daily usage sync. Indicates which feature the user is most familiar with.',
      render: (u) => <span style={{ color: 'var(--fg-muted)' }}>{u.last_feature}</span>,
      filterValue: (u) => u.last_feature,
    },
    {
      key: 'action',
      header: 'Action',
      render: (u) => (
        <Button
          size="sm"
          onClick={() => {
            window.open(
              `mailto:?subject=${encodeURIComponent(`Copilot Onboarding Request for ${u.user}`)}`,
              '_blank',
            );
          }}
        >
          Request Onboarding
        </Button>
      ),
    },
  ];

  const modalPowerUserColumns: ColumnDef<PowerUser>[] = [
    {
      key: 'user',
      header: 'User',
      filterable: true,
      helpText: 'GitHub username of the Copilot user. From daily Copilot usage API sync.',
      render: (u) => <span style={{ fontWeight: 500 }}>{u.user}</span>,
      filterValue: (u) => u.user,
    },
    {
      key: 'days_active',
      header: 'Days active',
      sortable: true,
      helpText:
        'Number of days with recorded Copilot activity in the period. From daily usage sync.',
      render: (u) => <span style={{ fontVariantNumeric: 'tabular-nums' }}>{u.days_active}d</span>,
      sortValue: (u) => u.days_active,
    },
    {
      key: 'features_used',
      header: 'Features used',
      sortable: true,
      helpText:
        'Number of distinct Copilot features used (e.g. completions, chat, CLI). From daily usage sync.',
      render: (u) => (
        <span style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--success)' }}>
          {u.features_used}
        </span>
      ),
      sortValue: (u) => u.features_used,
    },
  ];

  const modalMinimalUserColumns: ColumnDef<MinimalUser>[] = [
    {
      key: 'user',
      header: 'User',
      filterable: true,
      helpText: 'GitHub username of the Copilot user. From daily Copilot usage API sync.',
      render: (u) => <span style={{ fontWeight: 500 }}>{u.user}</span>,
      filterValue: (u) => u.user,
    },
    {
      key: 'days_active',
      header: 'Days active',
      sortable: true,
      helpText:
        'Number of days with recorded Copilot activity in the period. From daily usage sync. Users with 0 days may be candidates for seat reclamation.',
      render: (u) => <span style={{ fontVariantNumeric: 'tabular-nums' }}>{u.days_active}</span>,
      sortValue: (u) => u.days_active,
    },
    {
      key: 'last_feature',
      header: 'Last feature',
      filterable: true,
      helpText: 'The most recent Copilot feature used by this user. From daily usage sync.',
      render: (u) => <span style={{ color: 'var(--fg-muted)' }}>{u.last_feature}</span>,
      filterValue: (u) => u.last_feature,
    },
  ];

  const minimalUserDetailColumns: ColumnDef<{ metric: string; value: string }>[] = [
    {
      key: 'metric',
      header: 'Metric',
      helpText: 'The name of the activity metric for this user. From daily Copilot usage API sync.',
      render: (r) => <span style={{ color: 'var(--fg-muted)' }}>{r.metric}</span>,
    },
    {
      key: 'value',
      header: 'Value',
      helpText: 'The value of this metric. From daily Copilot usage API sync data.',
      render: (r) => {
        if (r.metric === 'User') return <span style={{ fontWeight: 500 }}>{r.value}</span>;
        if (r.metric === 'Days active')
          return <span style={{ fontVariantNumeric: 'tabular-nums' }}>{r.value}</span>;
        return <span>{r.value}</span>;
      },
    },
  ];

  return (
    <>
      {adoption?.error && (
        <SampleDataBanner
          message={adoption.message ?? 'Adoption data is unavailable. Displaying limited data.'}
        />
      )}

      {isError && <ErrorBanner message="Failed to load adoption data" />}
      {isLoading && <Spinner />}

      {!isLoading && !isError && (
        <>
          {/* Adoption tier cards */}
          <div className={styles.sectionTitle}>Adoption tiers</div>
          <div className={styles.tierGrid}>
            {tiers.map((tier) => {
              const isClickable = tier.id === 'power' || tier.id === 'minimal';
              return (
                <div
                  key={tier.id}
                  className={`${styles.tierCard} ${isClickable ? styles.tierCardClickable : ''}`}
                  style={{ borderTopColor: tier.color }}
                  role={isClickable ? 'button' : undefined}
                  tabIndex={isClickable ? 0 : undefined}
                  onClick={isClickable ? () => openTierModal(tier.id) : undefined}
                  onKeyDown={
                    isClickable
                      ? (e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            openTierModal(tier.id);
                          }
                        }
                      : undefined
                  }
                >
                  <div className={styles.tierCount} style={{ color: tier.color }}>
                    {tier.count}
                  </div>
                  <div className={styles.tierLabel}>{tier.label}</div>
                  <div className={styles.tierDesc}>{tier.desc}</div>
                </div>
              );
            })}
          </div>

          {/* Stacked progress bar */}
          <div className={styles.stackedBarContainer}>
            <div className={styles.stackedBar}>
              {tiers.map((tier) => {
                const isClickable = tier.id === 'power' || tier.id === 'minimal';
                return (
                  <div
                    key={tier.id}
                    className={`${styles.stackedSegment} ${isClickable ? styles.stackedSegmentClickable : ''}`}
                    style={{
                      width: `${totalAdoption > 0 ? (tier.count / totalAdoption) * 100 : 0}%`,
                      background: tier.color,
                    }}
                    title={`${tier.label}: ${tier.count} (${totalAdoption > 0 ? Math.round((tier.count / totalAdoption) * 100) : 0}%)`}
                    role={isClickable ? 'button' : undefined}
                    tabIndex={isClickable ? 0 : undefined}
                    onClick={isClickable ? () => openTierModal(tier.id) : undefined}
                    onKeyDown={
                      isClickable
                        ? (e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              openTierModal(tier.id);
                            }
                          }
                        : undefined
                    }
                  />
                );
              })}
            </div>
            <div className={styles.stackedLegend}>
              {tiers.map((tier) => (
                <div key={tier.id} className={styles.stackedLegendItem}>
                  <span className={styles.stackedLegendDot} style={{ background: tier.color }} />
                  {tier.label} (
                  {totalAdoption > 0 ? Math.round((tier.count / totalAdoption) * 100) : 0}%)
                </div>
              ))}
            </div>
          </div>

          {/* Daily power users table */}
          <Card style={{ marginBottom: 20 }}>
            <CardHeader>Daily power users</CardHeader>
            <DataTable<PowerUser>
              columns={powerUserColumns}
              data={powerUsers}
              rowKey={(u) => u.user}
            />
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
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        openFeatureModal(f.feature);
                      }
                    }}
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
          </div>

          {/* Minimal users — onboarding candidates */}
          <Card style={{ marginBottom: 20 }}>
            <CardHeader>Minimal users — onboarding candidates</CardHeader>
            <DataTable<MinimalUser>
              columns={minimalUserColumns}
              data={minimalUsers}
              rowKey={(u) => u.user}
            />
          </Card>

          {/* Tier detail modal */}
          <Modal
            open={adoptionModal === 'tier'}
            onClose={() => setAdoptionModal(null)}
            title={
              selectedTier ? `${selectedTier.label} — ${selectedTier.count} users` : 'Tier details'
            }
            width={640}
          >
            {selectedTier && selectedTierId === 'power' && (
              <div style={{ overflowX: 'auto' }}>
                <p style={{ fontSize: 13, color: 'var(--fg-muted)', margin: '0 0 12px' }}>
                  {selectedTier.desc} — showing top power users by activity.
                </p>
                <DataTable<PowerUser>
                  columns={modalPowerUserColumns}
                  data={powerUsers}
                  rowKey={(u) => u.user}
                  className={styles.modalTable}
                />
              </div>
            )}
            {selectedTier && selectedTierId === 'minimal' && (
              <div style={{ overflowX: 'auto' }}>
                <p style={{ fontSize: 13, color: 'var(--fg-muted)', margin: '0 0 12px' }}>
                  {selectedTier.desc} — showing minimal users who may benefit from onboarding.
                </p>
                <DataTable<MinimalUser>
                  columns={modalMinimalUserColumns}
                  data={minimalUsers}
                  rowKey={(u) => u.user}
                  className={styles.modalTable}
                />
              </div>
            )}
          </Modal>

          {/* Feature adoption detail modal */}
          <Modal
            open={adoptionModal === 'feature'}
            onClose={() => setAdoptionModal(null)}
            title={
              selectedFeatureData
                ? `${selectedFeatureData.feature} — adoption details`
                : 'Feature details'
            }
            width={520}
          >
            {selectedFeatureData && (
              <div>
                <p
                  style={{
                    fontSize: 13,
                    color: 'var(--fg-muted)',
                    lineHeight: 1.6,
                    margin: '0 0 12px',
                  }}
                >
                  <strong>{selectedFeatureData.feature}</strong> has{' '}
                  <strong>{selectedFeatureData.pct}%</strong> adoption across all Copilot users.
                </p>
                <p style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.6, margin: 0 }}>
                  Teams with low adoption of this feature can be identified via the Copilot Metrics
                  API. Consider targeted enablement sessions for teams below the org-wide average.
                </p>
              </div>
            )}
          </Modal>

          {/* Minimal user activity modal */}
          <Modal
            open={adoptionModal === 'minimal-user'}
            onClose={() => setAdoptionModal(null)}
            title={
              selectedMinimalUserData
                ? `@${selectedMinimalUserData.user} — Copilot activity`
                : 'User activity'
            }
            width={520}
          >
            {selectedMinimalUserData && (
              <div style={{ overflowX: 'auto' }}>
                <DataTable<{ metric: string; value: string }>
                  columns={minimalUserDetailColumns}
                  data={[
                    { metric: 'User', value: `@${selectedMinimalUserData.user}` },
                    { metric: 'Days active', value: String(selectedMinimalUserData.days_active) },
                    { metric: 'Last feature used', value: selectedMinimalUserData.last_feature },
                  ]}
                  rowKey={(r) => r.metric}
                  className={styles.modalTable}
                />
              </div>
            )}
          </Modal>
        </>
      )}
    </>
  );
}
