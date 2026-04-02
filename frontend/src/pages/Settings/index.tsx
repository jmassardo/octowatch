import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listSettings,
  updateSetting,
  deleteSetting,
  getSettingsAuditTrail,
} from '../../api/setup';
import type { AppSetting, SettingAuditEntry } from '../../api/setup';
import { listNotificationConfigs } from '../../api/integrations';
import { SyncPanel } from '../Integrations/SyncPanel';
import { SyncRunHistory } from '../Integrations/SyncRunHistory';
import { ManualIngestPanel } from '../Integrations/ManualIngestPanel';
import { AuditStreamPanel } from './AuditStreamPanel';
import { Button } from '../../components/primitives/Button';
import { Modal } from '../../components/primitives/Modal';
import { ConfirmDialog } from '../../components/primitives/ConfirmDialog';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { useFeatures } from '../../hooks/useFeatures';
import { formatAbsolute } from '../../utils/dates';
import styles from './Settings.module.css';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const CATEGORIES = ['All', 'GitHub', 'Security', 'Storage', 'Notifications', 'System'] as const;
type Category = (typeof CATEGORIES)[number];

const SLUG_TO_TAB: Record<string, Category | 'Audit' | 'Features' | 'Integrations'> = {
  all: 'All',
  github: 'GitHub',
  security: 'Security',
  storage: 'Storage',
  notifications: 'Notifications',
  system: 'System',
  audit: 'Audit',
  features: 'Features',
  integrations: 'Integrations',
};

const TAB_TO_SLUG: Record<string, string> = Object.fromEntries(
  Object.entries(SLUG_TO_TAB).map(([slug, tab]) => [tab, slug]),
);

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function sensitivityClass(sensitivity: string): string {
  if (sensitivity === 'critical') return styles.sensitivityCritical;
  if (sensitivity === 'sensitive') return styles.sensitivitySensitive;
  return styles.sensitivityNormal;
}

function auditActionClass(action: string): string {
  const a = action.toLowerCase();
  if (a.includes('create') || a === 'set') return styles.auditActionCreate;
  if (a.includes('update') || a.includes('change')) return styles.auditActionUpdate;
  if (a.includes('delete') || a.includes('revert')) return styles.auditActionDelete;
  return '';
}

/* ------------------------------------------------------------------ */
/*  Edit Form                                                          */
/* ------------------------------------------------------------------ */

function EditSettingForm({
  setting,
  onSave,
  onCancel,
}: {
  setting: AppSetting;
  onSave: (value: string, description?: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState('');
  const [description, setDescription] = useState(setting.description ?? '');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim()) return;
    onSave(value.trim(), description.trim() || undefined);
  }

  return (
    <form onSubmit={handleSubmit} className={styles.editForm}>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Key</label>
        <input className={styles.formInput} value={setting.key} disabled />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Current value (masked)</label>
        <input className={styles.formInput} value={setting.value} disabled />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel} htmlFor="setting-value">New value</label>
        <input
          id="setting-value"
          className={styles.formInput}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Enter new value"
          required
          autoFocus
        />
        <span className={styles.formHint}>
          The previous value will be replaced. Sensitive values are stored encrypted.
        </span>
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel} htmlFor="setting-description">Description (optional)</label>
        <input
          id="setting-description"
          className={styles.formInput}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Short description of this setting"
        />
      </div>
      <div className={styles.formActions}>
        <Button type="button" onClick={onCancel}>Cancel</Button>
        <Button variant="primary" type="submit" disabled={!value.trim()}>Save</Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Audit Trail Table                                                  */
/* ------------------------------------------------------------------ */

function AuditTrailTable() {
  const { data: entries, isLoading, isError, refetch } = useQuery({
    queryKey: ['settings', 'audit-trail'],
    queryFn: getSettingsAuditTrail,
  });

  if (isLoading) return <Spinner />;
  if (isError) return <ErrorBanner message="Failed to load audit trail" onRetry={() => refetch()} />;

  if (!entries || entries.length === 0) {
    return <div className={styles.empty}>No audit trail entries yet</div>;
  }

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Setting</th>
            <th>Action</th>
            <th>Changed by</th>
            <th>Old value</th>
            <th>New value</th>
            <th>Date</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry: SettingAuditEntry, idx: number) => (
            <tr key={`${entry.setting_key}-${entry.created_at}-${idx}`}>
              <td className={styles.settingKey}>{entry.setting_key}</td>
              <td>
                <span className={`${styles.auditAction} ${auditActionClass(entry.action)}`}>
                  {entry.action}
                </span>
              </td>
              <td>{entry.changed_by}</td>
              <td className={styles.settingValue}>{entry.old_value_masked ?? '—'}</td>
              <td className={styles.settingValue}>{entry.new_value_masked ?? '—'}</td>
              <td className={styles.settingMeta}>{formatAbsolute(entry.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Features Pane                                                      */
/* ------------------------------------------------------------------ */

const FEATURE_INFO = [
  {
    key: 'copilot_insights' as const,
    label: 'Copilot Insights',
    description:
      'GitHub Copilot adoption, seat utilization, and model usage analytics. Requires Copilot subscription and Metrics API access enabled in enterprise settings.',
  },
  {
    key: 'velocity' as const,
    label: 'Engineering Velocity',
    description:
      'CI/CD pipeline metrics, deployment frequency, lead time, and DORA metrics derived from GitHub Actions workflow data.',
  },
  {
    key: 'dev_activity' as const,
    label: 'Developer Activity',
    description:
      'Individual and team contribution analytics including commits, pull requests, and code review activity.',
  },
  {
    key: 'org_health' as const,
    label: 'Org Health',
    description:
      'Repository health signals, access auditing, license optimization, and GitHub Well-Architected Framework alignment.',
  },
];

function FeaturesPane() {
  const { features, toggleFeature, isToggling } = useFeatures();

  return (
    <div className={styles.featuresPane}>
      <p className={styles.featuresDescription}>
        Enable or disable optional platform features. Disabled features are hidden from the sidebar
        and will not make API calls.
      </p>
      <div className={styles.featuresList}>
        {FEATURE_INFO.map(({ key, label, description }) => (
          <div key={key} className={styles.featureRow}>
            <div className={styles.featureInfo}>
              <div className={styles.featureLabel}>{label}</div>
              <div className={styles.featureDescription}>{description}</div>
            </div>
            <label className={styles.toggleSwitch}>
              <input
                type="checkbox"
                checked={features[key]}
                onChange={(e) => toggleFeature(key, e.target.checked)}
                disabled={isToggling}
              />
              <span className={styles.toggleSlider} />
            </label>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  GitHub Pane                                                        */
/* ------------------------------------------------------------------ */

function GitHubPane() {
  return (
    <div className={styles.featuresPane}>
      <p className={styles.featuresDescription}>
        GitHub Enterprise connection and data import settings. Connection credentials
        are configured during initial setup.
      </p>

      <div className={styles.integrationsSectionDivider}>
        <h3 className={styles.integrationsSectionTitle}>Audit Log Streaming</h3>
        <p className={styles.featuresDescription}>
          Stream audit log events from GitHub Enterprise into OctoWatch via an S3-compatible endpoint.
        </p>
      </div>
      <AuditStreamPanel />

      <div className={styles.integrationsSectionDivider}>
        <h3 className={styles.integrationsSectionTitle}>Data Import</h3>
        <p className={styles.featuresDescription}>
          Sync data from GitHub Enterprise or manually import exported files for analysis.
        </p>
      </div>
      <SyncPanel />
      <SyncRunHistory />
      <ManualIngestPanel />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Integrations Pane                                                  */
/* ------------------------------------------------------------------ */

const INTEGRATION_INFO: {
  key: string;
  label: string;
  description: string;
}[] = [
  {
    key: 'slack',
    label: 'Slack',
    description:
      'Send real-time alerts and weekly digest reports to Slack channels.',
  },
  {
    key: 'sentinel',
    label: 'Microsoft Sentinel',
    description:
      'Forward normalized security events to Microsoft Sentinel for SIEM correlation.',
  },
  {
    key: 'splunk',
    label: 'Splunk',
    description:
      'Stream audit events and Copilot metrics to Splunk via HEC.',
  },
  {
    key: 'pagerduty',
    label: 'PagerDuty',
    description:
      'Trigger PagerDuty incidents for critical security detections.',
  },
];

function IntegrationsPane() {
  const navigate = useNavigate();
  const { data: notificationConfigs } = useQuery({
    queryKey: ['notification-configs'],
    queryFn: listNotificationConfigs,
  });

  const configs = notificationConfigs ?? [];

  function isEnabled(key: string): boolean {
    switch (key) {
      case 'slack':
        return configs.some((c) => c.channel_type === 'slack' && c.enabled);
      case 'sentinel':
        return configs.some(
          (c) =>
            c.channel_type === 'webhook' &&
            c.display_name.toLowerCase().includes('sentinel') &&
            c.enabled,
        );
      case 'splunk':
        return configs.some(
          (c) =>
            c.channel_type === 'webhook' &&
            c.display_name.toLowerCase().includes('splunk') &&
            c.enabled,
        );
      case 'pagerduty':
        return configs.some((c) => c.channel_type === 'pagerduty' && c.enabled);
      default:
        return false;
    }
  }

  function isConfigured(key: string): boolean {
    switch (key) {
      case 'slack':
        return configs.some((c) => c.channel_type === 'slack');
      case 'sentinel':
        return configs.some(
          (c) =>
            c.channel_type === 'webhook' &&
            c.display_name.toLowerCase().includes('sentinel'),
        );
      case 'splunk':
        return configs.some(
          (c) =>
            c.channel_type === 'webhook' &&
            c.display_name.toLowerCase().includes('splunk'),
        );
      case 'pagerduty':
        return configs.some((c) => c.channel_type === 'pagerduty');
      default:
        return false;
    }
  }

  return (
    <div className={styles.featuresPane}>
      <p className={styles.featuresDescription}>
        Connect external services to extend OctoWatch capabilities. GitHub Enterprise
        is always connected and managed via setup configuration.
      </p>
      <div className={styles.featuresList}>
        {INTEGRATION_INFO.map(({ key, label, description }) => {
          const enabled = isEnabled(key);
          const configured = isConfigured(key);
          return (
            <div key={key} className={styles.featureRow}>
              <div className={styles.featureInfo}>
                <div className={styles.featureLabel}>
                  {label}
                  {configured && (
                    <span
                      className={styles.integrationStatus}
                      data-status={enabled ? 'active' : 'configured'}
                    >
                      {enabled ? 'Active' : 'Configured'}
                    </span>
                  )}
                  {!configured && (
                    <span
                      className={styles.integrationStatus}
                      data-status="inactive"
                    >
                      Not configured
                    </span>
                  )}
                </div>
                <div className={styles.featureDescription}>{description}</div>
              </div>
              {configured ? (
                <Button size="sm" onClick={() => navigate('/settings/integrations')}>
                  Configure
                </Button>
              ) : (
                <Button size="sm" variant="primary" onClick={() => navigate('/settings/integrations')}>
                  Set up
                </Button>
              )}
            </div>
          );
        })}
      </div>

    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Category empty-state helpers                                       */
/* ------------------------------------------------------------------ */

function getCategoryEmptyMessage(category: string): string {
  switch (category) {
    case 'GitHub':
      return 'No GitHub settings configured yet.';
    case 'Security':
      return 'No security settings configured yet.';
    case 'Storage':
      return 'No storage settings configured yet.';
    case 'Notifications':
      return 'No notification settings configured yet.';
    case 'System':
      return 'No system settings configured yet.';
    default:
      return 'No settings configured yet.';
  }
}

function getCategoryEmptyHint(category: string): string {
  switch (category) {
    case 'GitHub':
      return 'GitHub connection settings are configured during setup. Data import and sync settings are available on this tab.';
    case 'Security':
      return 'Security settings including authentication, session management, and access controls.';
    case 'Storage':
      return 'Object storage (MinIO/S3) configuration for audit log archives.';
    case 'Notifications':
      return 'Notification channel configuration for alerts and reports.';
    case 'System':
      return 'System-level configuration including data retention, performance tuning, and maintenance settings.';
    default:
      return 'Settings are automatically populated during setup and sync. You can also add custom settings using the admin API.';
  }
}

/* ------------------------------------------------------------------ */
/*  Settings Page                                                      */
/* ------------------------------------------------------------------ */

export function SettingsPage() {
  const qc = useQueryClient();
  const { tab: tabSlug } = useParams<{ tab: string }>();
  const navigate = useNavigate();
  const activeTab: Category | 'Audit' | 'Features' | 'Integrations' = SLUG_TO_TAB[tabSlug ?? 'all'] ?? 'All';
  const [editTarget, setEditTarget] = useState<AppSetting | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AppSetting | null>(null);

  const { data: settings, isLoading, isError, refetch } = useQuery({
    queryKey: ['settings'],
    queryFn: listSettings,
  });

  const updateMutation = useMutation({
    mutationFn: ({ key, value, description }: { key: string; value: string; description?: string }) =>
      updateSetting(key, value, description),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] });
      qc.invalidateQueries({ queryKey: ['settings', 'audit-trail'] });
      setEditTarget(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (key: string) => deleteSetting(key),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] });
      qc.invalidateQueries({ queryKey: ['settings', 'audit-trail'] });
      setDeleteTarget(null);
    },
  });

  const filteredSettings = settings?.filter(
    (s: AppSetting) => activeTab === 'All' || s.category.toLowerCase() === (activeTab as string).toLowerCase(),
  ) ?? [];

  const isCategory = activeTab !== 'Audit' && activeTab !== 'Features' && activeTab !== 'Integrations' && activeTab !== 'GitHub';

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Settings</h1>
          <p className={styles.pageSub}>Manage application settings and view the audit trail</p>
        </div>
      </div>

      {/* Tab bar */}
      <div className={styles.tabs}>
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            className={activeTab === cat ? styles.tabActive : styles.tab}
            onClick={() => navigate(`/settings/${TAB_TO_SLUG[cat]}`)}
          >
            {cat}
          </button>
        ))}
        <button
          className={activeTab === 'Audit' ? styles.tabActive : styles.tab}
          onClick={() => navigate('/settings/audit')}
        >
          Audit Trail
        </button>
        <button
          className={activeTab === 'Features' ? styles.tabActive : styles.tab}
          onClick={() => navigate('/settings/features')}
        >
          Features
        </button>
        <button
          className={activeTab === 'Integrations' ? styles.tabActive : styles.tab}
          onClick={() => navigate('/settings/integrations')}
        >
          Integrations
        </button>
      </div>

      {/* Content */}
      {activeTab === 'Features' ? (
        <FeaturesPane />
      ) : activeTab === 'Integrations' ? (
        <IntegrationsPane />
      ) : activeTab === 'Audit' ? (
        <AuditTrailTable />
      ) : activeTab === 'GitHub' ? (
        <GitHubPane />
      ) : (
        <>
          {isError && <ErrorBanner message="Failed to load settings" onRetry={() => refetch()} />}

          {isLoading ? (
            <Spinner />
          ) : isCategory && filteredSettings.length === 0 ? (
            <div className={styles.empty}>
              <p>{getCategoryEmptyMessage(activeTab)}</p>
              <p style={{ color: 'var(--fg-subtle)', fontSize: '0.8125rem', marginTop: '0.5rem' }}>
                {getCategoryEmptyHint(activeTab)}
              </p>
            </div>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Value</th>
                    <th>Sensitivity</th>
                    <th>Description</th>
                    <th>Updated</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSettings.map((s: AppSetting) => (
                    <tr key={s.key}>
                      <td className={styles.settingKey}>{s.key}</td>
                      <td className={styles.settingValue}>{s.value}</td>
                      <td>
                        <span className={sensitivityClass(s.sensitivity)}>{s.sensitivity}</span>
                      </td>
                      <td className={styles.settingDescription}>{s.description ?? '—'}</td>
                      <td className={styles.settingMeta}>
                        {s.updated_by} · {formatAbsolute(s.updated_at)}
                      </td>
                      <td>
                        <div className={styles.cellActions}>
                          <Button size="sm" onClick={() => setEditTarget(s)}>Edit</Button>
                          <Button size="sm" variant="danger" onClick={() => setDeleteTarget(s)}>Reset</Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Edit modal */}
      <Modal open={!!editTarget} onClose={() => setEditTarget(null)} title={`Edit: ${editTarget?.key ?? ''}`}>
        {editTarget && (
          <EditSettingForm
            setting={editTarget}
            onSave={(value, description) =>
              updateMutation.mutate({ key: editTarget.key, value, description })
            }
            onCancel={() => setEditTarget(null)}
          />
        )}
      </Modal>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Reset setting"
        message={
          deleteTarget
            ? `Reset "${deleteTarget.key}" to its default (environment variable) value? This action is logged.`
            : ''
        }
        confirmLabel="Reset to default"
        confirmVariant="danger"
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.key)}
      />
    </div>
  );
}
