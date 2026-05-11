import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PageHeader } from '../../components/common/PageHeader';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Avatar } from '../../components/primitives/Avatar';
import { Button } from '../../components/primitives/Button';
import {
  getUserProfile,
  getUserPreferences,
  updateUserPreferences,
  getUserSessions,
  revokeSession,
} from '../../api/userProfile';
import type { UserPreferences, SessionInfo } from '../../api/userProfile';
import styles from './Profile.module.css';

type TabKey = 'profile' | 'preferences' | 'sessions';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'profile', label: 'Profile' },
  { key: 'preferences', label: 'Preferences' },
  { key: 'sessions', label: 'Sessions' },
];

const ROLE_DISPLAY_NAMES: Record<string, string> = {
  sys_admin: 'System Admin',
  super_admin: 'Super Admin',
  report_admin: 'Report Admin',
  rule_author: 'Rule Author',
  analyst: 'Analyst',
  viewer: 'Viewer',
};

const DASHBOARD_VIEW_OPTIONS = [
  { value: 'operations', label: 'Operations' },
  { value: 'executive', label: 'Executive' },
  { value: 'security', label: 'Security' },
  { value: 'cicd', label: 'CI/CD' },
];

const ITEMS_PER_PAGE_OPTIONS = [25, 50, 100];

/**
 * ProfilePage — User profile, preferences, and session management.
 */
export function ProfilePage() {
  const [activeTab, setActiveTab] = useState<TabKey>('profile');

  return (
    <div className={styles.page}>
      <PageHeader
        title="Profile &amp; Preferences"
        description="View your profile and manage personal settings."
      />

      <div className={styles.tabs} role="tablist" aria-label="Profile tabs">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            className={`${styles.tab}${activeTab === tab.key ? ` ${styles.tabActive}` : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'profile' && <ProfileTab />}
      {activeTab === 'preferences' && <PreferencesTab />}
      {activeTab === 'sessions' && <SessionsTab />}
    </div>
  );
}

/* ─── Profile Tab ──────────────────────────────────────────────────────────── */

function ProfileTab() {
  const {
    data: profile,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['user-profile'],
    queryFn: getUserProfile,
  });

  if (isLoading) return <p>Loading profile…</p>;
  if (error) return <p className={styles.errorMsg}>Failed to load profile.</p>;
  if (!profile) return null;

  return (
    <>
      <Card>
        <CardHeader>Profile</CardHeader>
        <div style={{ padding: '16px' }}>
          <div className={styles.profileHeader}>
            <Avatar username={profile.github_login} size={64} className={styles.avatarLarge} />
            <div className={styles.profileInfo}>
              <p className={styles.displayName}>{profile.display_name}</p>
              <p className={styles.username}>@{profile.github_login}</p>
              {profile.email && <p className={styles.email}>{profile.email}</p>}
            </div>
          </div>

          <div className={styles.rolesSection}>
            <p className={styles.sectionLabel}>Roles</p>
            <div className={styles.roleBadges}>
              {profile.roles.length === 0 && (
                <span className={styles.emptyState}>No roles assigned</span>
              )}
              {profile.roles.map((role) => (
                <span key={role} className={styles.roleBadge} data-testid="role-badge">
                  {ROLE_DISPLAY_NAMES[role] ?? role}
                </span>
              ))}
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader>Login History</CardHeader>
        <div style={{ padding: '16px' }}>
          {profile.login_history.length === 0 ? (
            <p className={styles.emptyState}>No login history available.</p>
          ) : (
            <table className={styles.historyTable}>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>IP Address</th>
                </tr>
              </thead>
              <tbody>
                {profile.login_history.map((entry, i) => (
                  <tr key={i}>
                    <td>{new Date(entry.timestamp).toLocaleString()}</td>
                    <td>{entry.ip_address ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Card>
    </>
  );
}

/* ─── Preferences Tab ──────────────────────────────────────────────────────── */

function PreferencesTab() {
  const queryClient = useQueryClient();

  const {
    data: prefs,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['user-preferences'],
    queryFn: getUserPreferences,
  });

  const [formState, setFormState] = useState<UserPreferences | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Initialise form when data loads
  const currentPrefs = formState ?? prefs;

  const mutation = useMutation({
    mutationFn: updateUserPreferences,
    onSuccess: (updated) => {
      queryClient.setQueryData(['user-preferences'], updated);
      setFormState(null);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    },
  });

  if (isLoading) return <p>Loading preferences…</p>;
  if (error) return <p className={styles.errorMsg}>Failed to load preferences.</p>;
  if (!currentPrefs) return null;

  function handleChange(field: keyof UserPreferences, value: string | number) {
    setFormState((prev) => ({
      ...(prev ?? prefs!),
      [field]: value,
    }));
    setSaveSuccess(false);
  }

  function handleSave() {
    if (currentPrefs) {
      mutation.mutate(currentPrefs);
    }
  }

  return (
    <Card>
      <CardHeader>Preferences</CardHeader>
      <div style={{ padding: '16px' }}>
        <div className={styles.prefsForm}>
          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel} htmlFor="pref-theme">
              Theme
            </label>
            <select
              id="pref-theme"
              className={styles.fieldSelect}
              value={currentPrefs.theme}
              onChange={(e) => handleChange('theme', e.target.value)}
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
            <p className={styles.fieldHint}>Saved to your profile and synced across devices.</p>
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel} htmlFor="pref-dashboard">
              Default Dashboard View
            </label>
            <select
              id="pref-dashboard"
              className={styles.fieldSelect}
              value={currentPrefs.default_dashboard_view}
              onChange={(e) => handleChange('default_dashboard_view', e.target.value)}
            >
              {DASHBOARD_VIEW_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel} htmlFor="pref-org">
              Default Organization
            </label>
            <input
              id="pref-org"
              className={styles.fieldInput}
              type="text"
              placeholder="e.g. my-org"
              value={currentPrefs.default_org}
              onChange={(e) => handleChange('default_org', e.target.value)}
            />
            <p className={styles.fieldHint}>Pre-selected organization for filtered pages.</p>
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel} htmlFor="pref-tz">
              Timezone
            </label>
            <input
              id="pref-tz"
              className={styles.fieldInput}
              type="text"
              placeholder="e.g. America/New_York"
              value={currentPrefs.timezone}
              onChange={(e) => handleChange('timezone', e.target.value)}
            />
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel} htmlFor="pref-dateformat">
              Date Format
            </label>
            <select
              id="pref-dateformat"
              className={styles.fieldSelect}
              value={currentPrefs.date_format}
              onChange={(e) => handleChange('date_format', e.target.value)}
            >
              <option value="relative">Relative (e.g. 2 hours ago)</option>
              <option value="absolute">Absolute (e.g. 2025-06-15 14:30)</option>
            </select>
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel} htmlFor="pref-perpage">
              Items Per Page
            </label>
            <select
              id="pref-perpage"
              className={styles.fieldSelect}
              value={currentPrefs.items_per_page}
              onChange={(e) => handleChange('items_per_page', Number(e.target.value))}
            >
              {ITEMS_PER_PAGE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>

          <div className={styles.saveBtn}>
            <Button
              variant="primary"
              size="sm"
              onClick={handleSave}
              disabled={mutation.isPending || !formState}
            >
              {mutation.isPending ? 'Saving…' : 'Save Preferences'}
            </Button>
          </div>

          {saveSuccess && <p className={styles.successMsg}>Preferences saved successfully.</p>}
          {mutation.isError && <p className={styles.errorMsg}>Failed to save preferences.</p>}
        </div>
      </div>
    </Card>
  );
}

/* ─── Sessions Tab ─────────────────────────────────────────────────────────── */

function SessionsTab() {
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['user-sessions'],
    queryFn: getUserSessions,
  });

  const revokeMutation = useMutation({
    mutationFn: revokeSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-sessions'] });
    },
  });

  if (isLoading) return <p>Loading sessions…</p>;
  if (error) return <p className={styles.errorMsg}>Failed to load sessions.</p>;

  const sessions: readonly SessionInfo[] = data?.sessions ?? [];

  return (
    <Card>
      <CardHeader>Active Sessions</CardHeader>
      <div style={{ padding: '16px' }}>
        {sessions.length === 0 ? (
          <p className={styles.emptyState}>No active sessions found.</p>
        ) : (
          <table className={styles.sessionsTable}>
            <thead>
              <tr>
                <th>Session</th>
                <th>IP Address</th>
                <th>Expires</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((session) => (
                <tr key={session.session_id}>
                  <td>
                    {session.session_id.slice(0, 8)}…
                    {session.is_current && <span className={styles.currentBadge}>Current</span>}
                  </td>
                  <td>{session.ip_address ?? '—'}</td>
                  <td>
                    {session.expires_at ? new Date(session.expires_at).toLocaleString() : '—'}
                  </td>
                  <td>
                    {session.is_current ? (
                      <span style={{ fontSize: '12px', color: 'var(--fg-muted)' }}>—</span>
                    ) : (
                      <button
                        className={styles.revokeBtn}
                        onClick={() => revokeMutation.mutate(session.session_id)}
                        disabled={revokeMutation.isPending}
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {revokeMutation.isError && <p className={styles.errorMsg}>Failed to revoke session.</p>}
      </div>
    </Card>
  );
}
