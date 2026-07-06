import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Button } from '../../components/primitives/Button';
import { DataTable } from '../../components/primitives/DataTable';
import type { ColumnDef } from '../../components/primitives/DataTable';
import { Modal } from '../../components/primitives/Modal';
import { Drawer } from '../../components/primitives/Drawer';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { SampleDataBanner } from '../../components/primitives/SampleDataBanner';
import { getCopilotAdoption } from '../../api/copilotMetrics';
import { useOrg } from '../../hooks/useOrg';
import styles from './Copilot.module.css';

type AdoptionModal = 'settings' | null;

interface UnifiedUser {
  user: string;
  tier: string;
  tier_color: string;
  days_active: number;
  features_used: number;
  last_feature: string;
  last_activity?: string;
  editor?: string;
  credits_consumed?: number;
}

export function AdoptionPane() {
  const { selectedOrg } = useOrg();
  const orgParam = selectedOrg || undefined;
  const {
    data: adoption,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['copilot', 'adoption', orgParam],
    queryFn: () => getCopilotAdoption(orgParam),
    staleTime: 30 * 60 * 1000,
  });

  const tiers = adoption?.tiers ?? [];
  const totalAdoption = adoption?.total_adoption ?? 0;
  const powerUsers = adoption?.power_users ?? [];
  const regularUsers = adoption?.regular_users ?? [];
  const featureAdoption = adoption?.feature_adoption ?? [];
  const minimalUsers = adoption?.minimal_users ?? [];
  const inactiveUsers = adoption?.inactive_users ?? [];

  const [adoptionModal, setAdoptionModal] = useState<AdoptionModal>(null);
  const [activeTier, setActiveTier] = useState<string | null>(null);
  const [drawerUser, setDrawerUser] = useState<UnifiedUser | null>(null);

  // Tier threshold settings (display-only for now, defaults from API)
  const [thresholds, setThresholds] = useState({
    power: 20,
    regular: 10,
    minimal: 1,
  });

  function handleTierClick(tierId: string) {
    setActiveTier((prev) => (prev === tierId ? null : tierId));
  }

  /** Build a unified user list from power_users, regular_users, and minimal_users */
  const allUsers: UnifiedUser[] = useMemo(() => {
    const tierColorMap: Record<string, string> = {};
    for (const t of tiers) {
      tierColorMap[t.id] = t.color;
    }

    const users: UnifiedUser[] = [];

    for (const u of powerUsers) {
      users.push({
        user: u.user,
        tier: 'power',
        tier_color: tierColorMap['power'] ?? '#3fb950',
        days_active: u.days_active,
        features_used: u.features_used,
        last_feature: '',
        last_activity: u.last_activity,
        editor: u.editor,
        credits_consumed: u.credits_consumed,
      });
    }

    for (const u of regularUsers) {
      users.push({
        user: u.user,
        tier: 'regular',
        tier_color: tierColorMap['regular'] ?? '#58a6ff',
        days_active: u.days_active,
        features_used: u.features_used,
        last_feature: '',
        last_activity: u.last_activity,
        editor: u.editor,
        credits_consumed: u.credits_consumed,
      });
    }

    for (const u of minimalUsers) {
      users.push({
        user: u.user,
        tier: 'minimal',
        tier_color: tierColorMap['minimal'] ?? '#d29922',
        days_active: u.days_active,
        features_used: 1,
        last_feature: u.last_feature,
        last_activity: u.last_activity,
        credits_consumed: u.credits_consumed,
      });
    }

    for (const u of inactiveUsers) {
      users.push({
        user: u.user,
        tier: 'inactive',
        tier_color: tierColorMap['inactive'] ?? '#8b949e',
        days_active: 0,
        features_used: 0,
        last_feature: '',
        last_activity: u.last_activity,
        credits_consumed: u.credits_consumed,
      });
    }

    return users;
  }, [powerUsers, regularUsers, minimalUsers, inactiveUsers, tiers]);

  const filteredUsers = useMemo(() => {
    if (!activeTier) return allUsers;
    return allUsers.filter((u) => u.tier === activeTier);
  }, [allUsers, activeTier]);

  const unifiedColumns: ColumnDef<UnifiedUser>[] = [
    {
      key: 'user',
      header: 'User',
      filterable: true,
      helpText: 'GitHub username of the Copilot user. From daily Copilot usage API sync.',
      render: (u) => <span style={{ fontWeight: 500 }}>{u.user}</span>,
      filterValue: (u) => u.user,
    },
    {
      key: 'tier',
      header: 'Tier',
      filterable: true,
      helpText:
        'Adoption tier classification based on days-active thresholds. Power: heavy daily use, Regular: moderate use, Minimal: infrequent use.',
      render: (u) => (
        <span
          style={{
            display: 'inline-block',
            padding: '2px 8px',
            borderRadius: 12,
            fontSize: 11,
            fontWeight: 600,
            background: u.tier_color,
            color: 'var(--fg-on-emphasis)',
          }}
        >
          {u.tier}
        </span>
      ),
      filterValue: (u) => u.tier,
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
    {
      key: 'last_feature',
      header: 'Last activity',
      helpText: 'The most recent Copilot feature used by this user. From daily usage sync.',
      render: (u) => <span style={{ color: 'var(--fg-muted)' }}>{u.last_feature || '—'}</span>,
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
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <div className={styles.sectionTitle}>Adoption tiers</div>
            <Button
              variant="default"
              size="sm"
              onClick={() => setAdoptionModal('settings')}
              aria-label="Tier threshold settings"
            >
              ⚙️ Thresholds
            </Button>
          </div>
          <div className={styles.tierGrid}>
            {tiers.map((tier) => (
              <div
                key={tier.id}
                className={`${styles.tierCard} ${styles.tierCardClickable} ${activeTier === tier.id ? styles.tierCardActive : ''}`}
                style={{ borderTopColor: tier.color }}
                role="button"
                tabIndex={0}
                aria-pressed={activeTier === tier.id}
                onClick={() => handleTierClick(tier.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleTierClick(tier.id);
                  }
                }}
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
                    opacity: activeTier && activeTier !== tier.id ? 0.4 : 1,
                  }}
                  title={`${tier.label}: ${tier.count} (${totalAdoption > 0 ? Math.round((tier.count / totalAdoption) * 100) : 0}%)`}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleTierClick(tier.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleTierClick(tier.id);
                    }
                  }}
                />
              ))}
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

          {/* Tier guidance */}
          <div
            style={{
              padding: '16px 20px',
              background: 'var(--bg-secondary)',
              borderRadius: 8,
              marginBottom: 20,
            }}
          >
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: 'var(--fg-muted)',
                marginBottom: 12,
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}
            >
              💡 Guidance
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {(!activeTier || activeTier === 'power') && (
                <div style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.5 }}>
                  <strong style={{ color: 'var(--fg)' }}>Power Users:</strong> Recruit power users
                  as product champions in their departments. Invite them to present at internal
                  office hours and demo sessions. They can drive organic adoption.
                </div>
              )}
              {(!activeTier || activeTier === 'regular') && (
                <div style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.5 }}>
                  <strong style={{ color: 'var(--fg)' }}>Regular Users:</strong> These users are
                  engaged but haven&apos;t maximized Copilot&apos;s potential. Share tips, new
                  features, and encourage chat/PR review usage to move them toward power user
                  status.
                </div>
              )}
              {(!activeTier || activeTier === 'minimal') && (
                <div style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.5 }}>
                  <strong style={{ color: 'var(--fg)' }}>Minimal Users:</strong> These users tried
                  Copilot but aren&apos;t making it a daily habit. Consider pairing them with a
                  power user buddy, sharing use cases relevant to their role, or offering hands-on
                  workshops.
                </div>
              )}
              {(!activeTier || activeTier === 'inactive') && (
                <div style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.5 }}>
                  <strong style={{ color: 'var(--fg)' }}>Inactive Users:</strong> These users have
                  seats but no activity. Reach out to confirm they still need access. Consider
                  reassigning seats or providing onboarding/training resources.
                </div>
              )}
            </div>
          </div>

          {/* Unified users table */}
          <Card style={{ marginBottom: 20 }}>
            <CardHeader>
              {activeTier ? `Copilot users — ${activeTier} tier` : 'Copilot users'}
            </CardHeader>
            <DataTable<UnifiedUser>
              columns={unifiedColumns}
              data={filteredUsers}
              rowKey={(u) => u.user}
              onRowClick={(u) => setDrawerUser(u)}
              pageSize={25}
            />
          </Card>

          {/* User detail drawer */}
          <Drawer
            open={drawerUser !== null}
            onClose={() => setDrawerUser(null)}
            title={drawerUser ? `@${drawerUser.user}` : 'User details'}
          >
            {drawerUser && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {/* Avatar placeholder & name */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div
                    style={{
                      width: 48,
                      height: 48,
                      borderRadius: '50%',
                      background: 'var(--bg-secondary)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 20,
                      fontWeight: 600,
                      color: 'var(--fg-muted)',
                    }}
                  >
                    {drawerUser.user.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 15 }}>@{drawerUser.user}</div>
                    <span
                      style={{
                        display: 'inline-block',
                        padding: '2px 8px',
                        borderRadius: 12,
                        fontSize: 11,
                        fontWeight: 600,
                        background: drawerUser.tier_color,
                        color: 'var(--fg-on-emphasis)',
                        marginTop: 4,
                      }}
                    >
                      {drawerUser.tier}
                    </span>
                  </div>
                </div>

                {/* Days active */}
                <div
                  style={{
                    padding: '12px 16px',
                    background: 'var(--bg-secondary)',
                    borderRadius: 8,
                  }}
                >
                  <div style={{ fontSize: 11, color: 'var(--fg-muted)', marginBottom: 4 }}>
                    Days active in period
                  </div>
                  <div
                    style={{ fontSize: 22, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}
                  >
                    {drawerUser.days_active}d
                  </div>
                </div>

                {/* Credits consumed */}
                {drawerUser.credits_consumed !== undefined && drawerUser.credits_consumed > 0 && (
                  <div
                    style={{
                      padding: '12px 16px',
                      background: 'var(--bg-secondary)',
                      borderRadius: 8,
                    }}
                  >
                    <div style={{ fontSize: 11, color: 'var(--fg-muted)', marginBottom: 4 }}>
                      Credits consumed (28d)
                    </div>
                    <div
                      style={{ fontSize: 22, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}
                    >
                      {drawerUser.credits_consumed.toFixed(1)}
                    </div>
                  </div>
                )}

                {/* Last activity date */}
                {drawerUser.last_activity && (
                  <div
                    style={{
                      padding: '12px 16px',
                      background: 'var(--bg-secondary)',
                      borderRadius: 8,
                    }}
                  >
                    <div style={{ fontSize: 11, color: 'var(--fg-muted)', marginBottom: 4 }}>
                      Last activity
                    </div>
                    <div style={{ fontSize: 14 }}>
                      {new Date(drawerUser.last_activity).toLocaleDateString(undefined, {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                      })}
                    </div>
                  </div>
                )}

                {/* Features breakdown */}
                <div>
                  <div
                    style={{
                      fontSize: 12,
                      fontWeight: 600,
                      color: 'var(--fg-muted)',
                      marginBottom: 8,
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                    }}
                  >
                    Features breakdown
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 6,
                    }}
                  >
                    {featureAdoption.map((f) => (
                      <div
                        key={f.feature}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '8px 12px',
                          borderRadius: 6,
                          background: 'var(--bg-secondary)',
                        }}
                      >
                        <span style={{ fontSize: 13 }}>{f.feature}</span>
                        <span
                          style={{
                            fontSize: 13,
                            fontWeight: 600,
                            fontVariantNumeric: 'tabular-nums',
                            color: f.color,
                          }}
                        >
                          {f.pct}%
                        </span>
                      </div>
                    ))}
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: 'var(--fg-muted)',
                      marginTop: 8,
                    }}
                  >
                    Total features used: {drawerUser.features_used}
                  </div>
                </div>

                {/* Editor */}
                {drawerUser.editor && (
                  <div
                    style={{
                      padding: '12px 16px',
                      background: 'var(--bg-secondary)',
                      borderRadius: 8,
                    }}
                  >
                    <div style={{ fontSize: 11, color: 'var(--fg-muted)', marginBottom: 4 }}>
                      Editor
                    </div>
                    <div style={{ fontSize: 14 }}>{drawerUser.editor}</div>
                  </div>
                )}

                {/* GitHub profile link */}
                <a
                  href={`https://github.com/${drawerUser.user}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '10px 16px',
                    background: 'var(--bg-secondary)',
                    borderRadius: 8,
                    fontSize: 13,
                    fontWeight: 500,
                    color: 'var(--fg)',
                    textDecoration: 'none',
                    border: '1px solid var(--border)',
                  }}
                >
                  View on GitHub ↗
                </a>
              </div>
            )}
          </Drawer>

          {/* Tier threshold settings modal */}
          <Modal
            open={adoptionModal === 'settings'}
            onClose={() => setAdoptionModal(null)}
            title="Adoption tier thresholds"
            width={420}
          >
            <div style={{ padding: 16 }}>
              <p style={{ fontSize: 13, color: 'var(--fg-muted)', marginBottom: 16 }}>
                Configure the minimum days-active thresholds used to classify users into adoption
                tiers. Changes apply to future calculations.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <label style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <span>Power User (days active in 30d)</span>
                  <input
                    type="number"
                    min={1}
                    max={30}
                    value={thresholds.power}
                    onChange={(e) =>
                      setThresholds((prev) => ({
                        ...prev,
                        power: Number(e.target.value),
                      }))
                    }
                    aria-label="Power user threshold"
                    style={{
                      width: 60,
                      padding: '2px 6px',
                      borderRadius: 4,
                      border: '1px solid var(--border)',
                      background: 'var(--bg-secondary)',
                      color: 'var(--fg)',
                      textAlign: 'center',
                    }}
                  />
                </label>
                <label style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <span>Regular User (days active in 30d)</span>
                  <input
                    type="number"
                    min={1}
                    max={30}
                    value={thresholds.regular}
                    onChange={(e) =>
                      setThresholds((prev) => ({
                        ...prev,
                        regular: Number(e.target.value),
                      }))
                    }
                    aria-label="Regular user threshold"
                    style={{
                      width: 60,
                      padding: '2px 6px',
                      borderRadius: 4,
                      border: '1px solid var(--border)',
                      background: 'var(--bg-secondary)',
                      color: 'var(--fg)',
                      textAlign: 'center',
                    }}
                  />
                </label>
                <label style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <span>Minimal User (days active in 30d)</span>
                  <input
                    type="number"
                    min={1}
                    max={30}
                    value={thresholds.minimal}
                    onChange={(e) =>
                      setThresholds((prev) => ({
                        ...prev,
                        minimal: Number(e.target.value),
                      }))
                    }
                    aria-label="Minimal user threshold"
                    style={{
                      width: 60,
                      padding: '2px 6px',
                      borderRadius: 4,
                      border: '1px solid var(--border)',
                      background: 'var(--bg-secondary)',
                      color: 'var(--fg)',
                      textAlign: 'center',
                    }}
                  />
                </label>
              </div>
              <div
                style={{
                  marginTop: 16,
                  fontSize: 11,
                  color: 'var(--fg-muted)',
                  lineHeight: 1.5,
                }}
              >
                Current defaults — Power: ≥{thresholds.power}d, Regular: ≥{thresholds.regular}d,
                Minimal: ≥{thresholds.minimal}d. Users below Minimal threshold are classified as
                Inactive.
              </div>
            </div>
          </Modal>
        </>
      )}
    </>
  );
}
