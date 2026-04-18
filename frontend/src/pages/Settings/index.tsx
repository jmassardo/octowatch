import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listSettings,
  updateSetting,
  deleteSetting,
  getSettingsAuditTrail,
  getEnterprisePATStatus,
  saveEnterprisePAT,
  deleteEnterprisePAT,
  testEnterprisePAT,
} from '../../api/setup';
import type { AppSetting, SettingAuditEntry } from '../../api/setup';
import {
  listNotificationConfigs,
  listTicketingConfigs,
  listSiemConfigs,
  createNotificationConfig,
  createTicketingConfig,
  createSiemConfig,
} from '../../api/integrations';
import { getRetentionPolicies, updateRetentionPolicies } from '../../api/admin';
import type { RetentionPolicyItem } from '../../api/admin';
import { SyncPanel } from '../Integrations/SyncPanel';
import { SyncRunHistory } from '../Integrations/SyncRunHistory';
import { ManualIngestPanel } from '../Integrations/ManualIngestPanel';
import { AuditStreamPanel } from './AuditStreamPanel';
import { Button } from '../../components/primitives/Button';
import { Drawer } from '../../components/primitives/Drawer';
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

const SLUG_TO_TAB: Record<string, Category | 'Audit' | 'Features' | 'Integrations' | 'Retention'> =
  {
    all: 'All',
    github: 'GitHub',
    security: 'Security',
    storage: 'Storage',
    notifications: 'Notifications',
    system: 'System',
    audit: 'Audit',
    features: 'Features',
    integrations: 'Integrations',
    retention: 'Retention',
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
        <label className={styles.formLabel} htmlFor="setting-value">
          New value
        </label>
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
        <label className={styles.formLabel} htmlFor="setting-description">
          Description (optional)
        </label>
        <input
          id="setting-description"
          className={styles.formInput}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Short description of this setting"
        />
      </div>
      <div className={styles.formActions}>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
        <Button variant="primary" type="submit" disabled={!value.trim()}>
          Save
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Audit Trail Table                                                  */
/* ------------------------------------------------------------------ */

function AuditTrailTable() {
  const {
    data: entries,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['settings', 'audit-trail'],
    queryFn: getSettingsAuditTrail,
  });

  if (isLoading) return <Spinner />;
  if (isError)
    return <ErrorBanner message="Failed to load audit trail" onRetry={() => refetch()} />;

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
/*  Enterprise PAT Section                                             */
/* ------------------------------------------------------------------ */

function EnterprisePATSection() {
  const queryClient = useQueryClient();
  const [tokenInput, setTokenInput] = useState('');
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);

  const { data: patStatus, isLoading: patLoading } = useQuery({
    queryKey: ['enterprise-pat-status'],
    queryFn: getEnterprisePATStatus,
  });

  const saveMutation = useMutation({
    mutationFn: (token: string) => saveEnterprisePAT(token),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['enterprise-pat-status'] });
      setTokenInput('');
      setSaveError(null);
      setSaveSuccess(`PAT saved successfully (${result.masked}).`);
      setTestMessage(null);
      setTestError(null);
      setTimeout(() => setSaveSuccess(null), 5000);
    },
    onError: (err: Error & { status?: number; body?: { detail?: string } }) => {
      const detail = (err as unknown as { body?: { detail?: string } }).body?.detail ?? err.message;
      setSaveError(detail);
      setSaveSuccess(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteEnterprisePAT(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['enterprise-pat-status'] });
      setTestMessage(null);
      setTestError(null);
      setSaveError(null);
      setSaveSuccess('Enterprise PAT removed.');
      setTimeout(() => setSaveSuccess(null), 5000);
    },
    onError: (err: Error) => {
      setSaveError(err.message);
    },
  });

  const testMutation = useMutation({
    mutationFn: () => testEnterprisePAT(),
    onSuccess: (result) => {
      if (result.status === 'ok') {
        setTestMessage(
          `Connected as ${result.login ?? 'unknown'}. Scopes: ${result.scopes || 'none detected'}.`,
        );
        setTestError(null);
      } else {
        setTestError(result.message ?? 'Test failed.');
        setTestMessage(null);
      }
    },
    onError: (err: Error) => {
      setTestError(err.message);
      setTestMessage(null);
    },
  });

  const configured = patStatus?.configured ?? false;

  return (
    <div className={styles.configForm} data-testid="enterprise-pat-section">
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="enterprise-pat-token">
          Classic Personal Access Token
        </label>
        {patLoading ? (
          <Spinner />
        ) : configured ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              className={styles.configInput}
              value={patStatus?.masked ?? ''}
              disabled
              style={{ flex: 1 }}
            />
            <span
              className={styles.integrationStatus}
              data-status="active"
              title="Enterprise PAT is configured and ready for audit log ingestion"
            >
              Configured
            </span>
          </div>
        ) : (
          <span
            className={styles.integrationStatus}
            data-status="inactive"
            title="No Enterprise PAT has been configured yet"
          >
            Not configured
          </span>
        )}
      </div>
      <div className={styles.configField}>
        <input
          id="enterprise-pat-token"
          className={styles.configInput}
          type="password"
          value={tokenInput}
          onChange={(e) => {
            setTokenInput(e.target.value);
            setSaveError(null);
            setSaveSuccess(null);
          }}
          placeholder={configured ? 'Enter new token to replace…' : 'ghp_… or github_pat_…'}
          autoComplete="off"
        />
        <span className={styles.configHelp}>
          Required for audit log ingestion. Create a classic PAT with <code>admin:enterprise</code>{' '}
          scope in your GitHub Enterprise settings.
        </span>
      </div>
      {saveSuccess && <div className={styles.configSuccess}>{saveSuccess}</div>}
      {saveError && <div className={styles.configError}>{saveError}</div>}
      {testMessage && <div className={styles.configSuccess}>{testMessage}</div>}
      {testError && <div className={styles.configError}>{testError}</div>}
      <div className={styles.configActions}>
        <Button
          variant="primary"
          size="sm"
          disabled={!tokenInput.trim() || saveMutation.isPending}
          onClick={() => saveMutation.mutate(tokenInput.trim())}
        >
          {saveMutation.isPending ? 'Saving…' : 'Save'}
        </Button>
        {configured && (
          <>
            <Button
              size="sm"
              disabled={testMutation.isPending}
              onClick={() => testMutation.mutate()}
            >
              {testMutation.isPending ? 'Testing…' : 'Test Connection'}
            </Button>
            <Button
              size="sm"
              variant="danger"
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
            >
              {deleteMutation.isPending ? 'Removing…' : 'Remove'}
            </Button>
          </>
        )}
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
        GitHub Enterprise connection and data import settings. Connection credentials are configured
        during initial setup.
      </p>

      <div className={styles.integrationsSectionDivider}>
        <h3 className={styles.integrationsSectionTitle}>Classic PAT for Audit Log</h3>
        <p className={styles.featuresDescription}>
          The enterprise audit log API requires a classic Personal Access Token with{' '}
          <code>admin:enterprise</code> scope. GitHub App installation tokens cannot access this
          endpoint.
        </p>
      </div>
      <EnterprisePATSection />

      <div className={styles.integrationsSectionDivider}>
        <h3 className={styles.integrationsSectionTitle}>Audit Log Streaming</h3>
        <p className={styles.featuresDescription}>
          Stream audit log events from GitHub Enterprise into OctoWatch via an S3-compatible
          endpoint.
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

/* ------------------------------------------------------------------ */
/*  Integration Icons                                                  */
/* ------------------------------------------------------------------ */

function SlackIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="8" cy="12" r="2" fill="#E01E5A" />
      <circle cx="12" cy="8" r="2" fill="#36C5F0" />
      <circle cx="16" cy="12" r="2" fill="#2EB67D" />
      <circle cx="12" cy="16" r="2" fill="#ECB22E" />
    </svg>
  );
}

function SentinelIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M13 3l7 14H6L13 3z" fill="#0078d4" fillOpacity="0.9" />
      <path d="M13 9v4M13 15h.01" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function SplunkIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 18L12 4l7 14H5z" fill="#65a637" fillOpacity="0.85" />
      <path d="M12 10v4" stroke="white" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function PagerDutyIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8" stroke="#06ac38" strokeWidth="2" fill="none" />
      <circle cx="12" cy="12" r="3" fill="#06ac38" />
    </svg>
  );
}

function JiraIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M6 13l4-4 2 2 6-6"
        stroke="#0052CC"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M14 5h6v6"
        stroke="#0052CC"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SyslogIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="4" y="6" width="16" height="12" rx="2" stroke="white" strokeWidth="1.5" />
      <path d="M8 10h8M8 14h5" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function SoarWebhookIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 4v8l4 4" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="12" cy="12" r="8" stroke="white" strokeWidth="1.5" />
      <path d="M17 17l3 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Integration config form data                                       */
/* ------------------------------------------------------------------ */

const INTEGRATION_INFO: {
  key: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  iconBg: string;
}[] = [
  {
    key: 'slack',
    label: 'Slack',
    description: 'Send real-time alerts and weekly digest reports to Slack channels.',
    icon: <SlackIcon />,
    iconBg: '#4a154b',
  },
  {
    key: 'jira',
    label: 'Jira',
    description: 'Automatically create Jira issues for security findings and track remediation.',
    icon: <JiraIcon />,
    iconBg: '#0052CC',
  },
  {
    key: 'sentinel',
    label: 'Microsoft Sentinel',
    description: 'Forward normalized security events to Microsoft Sentinel for SIEM correlation.',
    icon: <SentinelIcon />,
    iconBg: '#0078d4',
  },
  {
    key: 'splunk',
    label: 'Splunk',
    description: 'Stream audit events and Copilot metrics to Splunk via HEC.',
    icon: <SplunkIcon />,
    iconBg: '#1a1a1a',
  },
  {
    key: 'pagerduty',
    label: 'PagerDuty',
    description: 'Trigger PagerDuty incidents for critical security detections.',
    icon: <PagerDutyIcon />,
    iconBg: '#06ac38',
  },
  {
    key: 'syslog_cef',
    label: 'Syslog / CEF',
    description:
      'Export detections in CEF or LEEF format via syslog for SIEM correlation (Splunk, QRadar, Sentinel).',
    icon: <SyslogIcon />,
    iconBg: '#6366f1',
  },
  {
    key: 'splunk_hec',
    label: 'Splunk HEC',
    description:
      'Stream events and detections to Splunk via HTTP Event Collector with proper sourcetype and index.',
    icon: <SplunkIcon />,
    iconBg: '#65a637',
  },
  {
    key: 'soar_webhook',
    label: 'SOAR Webhook',
    description:
      'Send detection events to a SOAR webhook URL to trigger automated response playbooks.',
    icon: <SoarWebhookIcon />,
    iconBg: '#f59e0b',
  },
];

/* ------------------------------------------------------------------ */
/*  Slack config form                                                  */
/* ------------------------------------------------------------------ */

function SlackConfigForm({ onClose }: { onClose: () => void }) {
  const [displayName, setDisplayName] = useState('');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [severities, setSeverities] = useState<string[]>(['critical', 'high']);
  const [cooldown, setCooldown] = useState(3600);
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: () =>
      createNotificationConfig({
        channel_type: 'slack',
        display_name: displayName || 'Slack',
        target: webhookUrl,
        notify_severities: severities,
        cooldown_seconds: cooldown,
        enabled: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-configs'] });
      onClose();
    },
  });

  return (
    <form
      className={styles.configForm}
      onSubmit={(e) => {
        e.preventDefault();
        createMutation.mutate();
      }}
    >
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="slack-display-name">
          Display Name
        </label>
        <input
          id="slack-display-name"
          className={styles.configInput}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="e.g. #security-alerts"
        />
        <span className={styles.configHelp}>
          A friendly name to identify this Slack integration in the dashboard.
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="slack-webhook-url">
          Webhook URL
        </label>
        <input
          id="slack-webhook-url"
          className={styles.configInput}
          value={webhookUrl}
          onChange={(e) => setWebhookUrl(e.target.value)}
          placeholder="https://hooks.slack.com/services/..."
          required
        />
        <span className={styles.configHelp}>
          Incoming webhook URL from your Slack app. Create one at api.slack.com.
        </span>
      </div>
      <div className={styles.configField}>
        <span className={styles.configLabel}>Alert severities</span>
        <div style={{ display: 'flex', gap: 12, marginTop: 4 }}>
          {['critical', 'high', 'medium', 'low'].map((s) => (
            <label
              key={s}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                fontSize: 12,
                color: 'var(--fg)',
              }}
            >
              <input
                type="checkbox"
                checked={severities.includes(s)}
                onChange={(e) =>
                  setSeverities((prev) =>
                    e.target.checked ? [...prev, s] : prev.filter((x) => x !== s),
                  )
                }
              />
              {s}
            </label>
          ))}
        </div>
        <span className={styles.configHelp}>
          Select which severity levels trigger Slack notifications.
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="slack-cooldown">
          Cooldown (seconds)
        </label>
        <input
          id="slack-cooldown"
          className={styles.configInput}
          type="number"
          min={60}
          max={86400}
          value={cooldown}
          onChange={(e) => setCooldown(Number(e.target.value))}
        />
        <span className={styles.configHelp}>Minimum time between alerts (60–86,400 seconds).</span>
      </div>
      {createMutation.isError && (
        <div className={styles.configError}>Failed to save configuration. Please try again.</div>
      )}
      <div className={styles.configActions}>
        <Button size="sm" type="button" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="primary" size="sm" disabled={!webhookUrl || createMutation.isPending}>
          {createMutation.isPending ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Jira config form                                                   */
/* ------------------------------------------------------------------ */

function JiraConfigForm({ onClose }: { onClose: () => void }) {
  const [displayName, setDisplayName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [projectKey, setProjectKey] = useState('');
  const [credentialEnvVar, setCredentialEnvVar] = useState('JIRA_API_TOKEN');
  const [autoCreate, setAutoCreate] = useState(false);
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: () =>
      createTicketingConfig({
        provider: 'jira',
        display_name: displayName || 'Jira',
        target: baseUrl,
        project_key: projectKey || undefined,
        default_issue_type: 'Bug',
        auto_create: autoCreate,
        auto_create_severities: ['critical', 'high'],
        credential_env_var: credentialEnvVar,
        enabled: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ticketing-configs'] });
      queryClient.invalidateQueries({ queryKey: ['notification-configs'] });
      onClose();
    },
  });

  return (
    <form
      className={styles.configForm}
      onSubmit={(e) => {
        e.preventDefault();
        createMutation.mutate();
      }}
    >
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="jira-display-name">
          Display Name
        </label>
        <input
          id="jira-display-name"
          className={styles.configInput}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="e.g. Security Project"
        />
        <span className={styles.configHelp}>
          A friendly name to identify this Jira integration in the dashboard.
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="jira-base-url">
          Jira Base URL
        </label>
        <input
          id="jira-base-url"
          className={styles.configInput}
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://your-org.atlassian.net"
          required
        />
        <span className={styles.configHelp}>
          The root URL of your Jira Cloud or Server instance.
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="jira-project-key">
          Project Key
        </label>
        <input
          id="jira-project-key"
          className={styles.configInput}
          value={projectKey}
          onChange={(e) => setProjectKey(e.target.value)}
          placeholder="e.g. SEC"
        />
        <span className={styles.configHelp}>Jira project key for issue creation.</span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="jira-credential">
          API Token Environment Variable
        </label>
        <input
          id="jira-credential"
          className={styles.configInput}
          value={credentialEnvVar}
          onChange={(e) => setCredentialEnvVar(e.target.value)}
          placeholder="JIRA_API_TOKEN"
          required
        />
        <span className={styles.configHelp}>
          Name of the environment variable holding the Jira API token.
        </span>
      </div>
      <div className={styles.configField}>
        <div className={styles.configToggleRow}>
          <label className={styles.configLabel} htmlFor="jira-auto-create">
            Auto-create issues for critical/high findings
          </label>
          <input
            id="jira-auto-create"
            type="checkbox"
            checked={autoCreate}
            onChange={(e) => setAutoCreate(e.target.checked)}
          />
        </div>
        <span className={styles.configHelp}>
          When enabled, Jira issues are automatically filed for critical and high severity findings.
        </span>
      </div>
      {createMutation.isError && (
        <div className={styles.configError}>Failed to save configuration. Please try again.</div>
      )}
      <div className={styles.configActions}>
        <Button size="sm" type="button" onClick={onClose}>
          Cancel
        </Button>
        <Button
          variant="primary"
          size="sm"
          disabled={!baseUrl || !credentialEnvVar || createMutation.isPending}
        >
          {createMutation.isPending ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Webhook config form (Sentinel, Splunk, PagerDuty)                  */
/* ------------------------------------------------------------------ */

function WebhookConfigForm({ name, onClose }: { name: string; onClose: () => void }) {
  const channelType: 'webhook' | 'pagerduty' = name === 'PagerDuty' ? 'pagerduty' : 'webhook';
  const [displayName, setDisplayName] = useState(name);
  const [webhookUrl, setWebhookUrl] = useState('');
  const [credentialEnvVar, setCredentialEnvVar] = useState('');
  const [severities, setSeverities] = useState<string[]>(['critical', 'high']);
  const [cooldown, setCooldown] = useState(3600);
  const queryClient = useQueryClient();

  const placeholderUrl =
    name === 'PagerDuty'
      ? 'https://events.pagerduty.com/v2/enqueue'
      : name === 'Splunk'
        ? 'https://your-splunk-hec:8088/services/collector'
        : 'https://your-sentinel-workspace.ods.opinsights.azure.com/...';

  const createMutation = useMutation({
    mutationFn: () =>
      createNotificationConfig({
        channel_type: channelType,
        display_name: displayName || name,
        target: webhookUrl,
        credential_env_var: credentialEnvVar || undefined,
        notify_severities: severities,
        cooldown_seconds: cooldown,
        enabled: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-configs'] });
      onClose();
    },
  });

  return (
    <form
      className={styles.configForm}
      onSubmit={(e) => {
        e.preventDefault();
        createMutation.mutate();
      }}
    >
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="webhook-display-name">
          Display Name
        </label>
        <input
          id="webhook-display-name"
          className={styles.configInput}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder={name}
        />
        <span className={styles.configHelp}>
          A friendly name to identify this integration in the dashboard.
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="webhook-url">
          Endpoint URL
        </label>
        <input
          id="webhook-url"
          className={styles.configInput}
          value={webhookUrl}
          onChange={(e) => setWebhookUrl(e.target.value)}
          placeholder={placeholderUrl}
          required
        />
        <span className={styles.configHelp}>
          The HTTPS endpoint that will receive alert payloads via POST.
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="webhook-credential">
          Auth Token Environment Variable
        </label>
        <input
          id="webhook-credential"
          className={styles.configInput}
          value={credentialEnvVar}
          onChange={(e) => setCredentialEnvVar(e.target.value)}
          placeholder={`${name.toUpperCase().replace(/\s+/g, '_')}_TOKEN`}
        />
        <span className={styles.configHelp}>
          Optional. Name of the environment variable holding the auth token.
        </span>
      </div>
      <div className={styles.configField}>
        <span className={styles.configLabel}>Alert severities</span>
        <div style={{ display: 'flex', gap: 12, marginTop: 4 }}>
          {['critical', 'high', 'medium', 'low'].map((s) => (
            <label
              key={s}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                fontSize: 12,
                color: 'var(--fg)',
              }}
            >
              <input
                type="checkbox"
                checked={severities.includes(s)}
                onChange={(e) =>
                  setSeverities((prev) =>
                    e.target.checked ? [...prev, s] : prev.filter((x) => x !== s),
                  )
                }
              />
              {s}
            </label>
          ))}
        </div>
        <span className={styles.configHelp}>
          Select which severity levels trigger notifications to this endpoint.
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="webhook-cooldown">
          Cooldown (seconds)
        </label>
        <input
          id="webhook-cooldown"
          className={styles.configInput}
          type="number"
          min={60}
          max={86400}
          value={cooldown}
          onChange={(e) => setCooldown(Number(e.target.value))}
        />
        <span className={styles.configHelp}>Minimum time between alerts (60–86,400 seconds).</span>
      </div>
      {createMutation.isError && (
        <div className={styles.configError}>Failed to save configuration. Please try again.</div>
      )}
      <div className={styles.configActions}>
        <Button size="sm" type="button" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="primary" size="sm" disabled={!webhookUrl || createMutation.isPending}>
          {createMutation.isPending ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Syslog/CEF config form                                            */
/* ------------------------------------------------------------------ */

function SyslogConfigForm({ onClose }: { onClose: () => void }) {
  const [displayName, setDisplayName] = useState('Syslog / CEF');
  const [host, setHost] = useState('');
  const [port, setPort] = useState(514);
  const [protocol, setProtocol] = useState<'tcp' | 'udp' | 'tls'>('udp');
  const [format, setFormat] = useState<'cef' | 'leef'>('cef');
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: () =>
      createSiemConfig({
        export_type: 'syslog',
        display_name: displayName || 'Syslog / CEF',
        syslog_host: host,
        syslog_port: port,
        syslog_protocol: protocol,
        syslog_format: format,
        enabled: true,
        export_detections: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['siem-configs'] });
      onClose();
    },
  });

  return (
    <form
      className={styles.configForm}
      onSubmit={(e) => {
        e.preventDefault();
        createMutation.mutate();
      }}
    >
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="syslog-name">
          Display Name
        </label>
        <input
          id="syslog-name"
          className={styles.configInput}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="Syslog / CEF"
        />
        <span className={styles.configHelp}>
          A friendly name to identify this syslog export in the dashboard.
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="syslog-host">
          Syslog Host
        </label>
        <input
          id="syslog-host"
          className={styles.configInput}
          value={host}
          onChange={(e) => setHost(e.target.value)}
          placeholder="syslog.example.com"
          required
        />
        <span className={styles.configHelp}>Hostname or IP address of the syslog receiver.</span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="syslog-port">
          Port
        </label>
        <input
          id="syslog-port"
          className={styles.configInput}
          type="number"
          min={1}
          max={65535}
          value={port}
          onChange={(e) => setPort(Number(e.target.value))}
        />
        <span className={styles.configHelp}>
          Network port the syslog receiver listens on (default: 514).
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="syslog-protocol">
          Protocol
        </label>
        <select
          id="syslog-protocol"
          className={styles.configInput}
          value={protocol}
          onChange={(e) => setProtocol(e.target.value as 'tcp' | 'udp' | 'tls')}
        >
          <option value="udp">UDP</option>
          <option value="tcp">TCP</option>
          <option value="tls">TLS</option>
        </select>
        <span className={styles.configHelp}>
          Transport protocol. Use TLS for encrypted delivery.
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="syslog-format">
          Format
        </label>
        <select
          id="syslog-format"
          className={styles.configInput}
          value={format}
          onChange={(e) => setFormat(e.target.value as 'cef' | 'leef')}
        >
          <option value="cef">CEF (Common Event Format)</option>
          <option value="leef">LEEF (QRadar)</option>
        </select>
        <span className={styles.configHelp}>
          CEF is widely supported; LEEF is preferred for IBM QRadar.
        </span>
      </div>
      {createMutation.isError && (
        <div className={styles.configError}>Failed to save configuration. Please try again.</div>
      )}
      <div className={styles.configActions}>
        <Button size="sm" type="button" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="primary" size="sm" disabled={!host || createMutation.isPending}>
          {createMutation.isPending ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Splunk HEC config form                                            */
/* ------------------------------------------------------------------ */

function SplunkHecConfigForm({ onClose }: { onClose: () => void }) {
  const [displayName, setDisplayName] = useState('Splunk HEC');
  const [hecUrl, setHecUrl] = useState('');
  const [tokenEnvVar, setTokenEnvVar] = useState('');
  const [splunkIndex, setSplunkIndex] = useState('main');
  const [exportEvents, setExportEvents] = useState(false);
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: () =>
      createSiemConfig({
        export_type: 'splunk_hec',
        display_name: displayName || 'Splunk HEC',
        splunk_hec_url: hecUrl,
        splunk_hec_token_env_var: tokenEnvVar,
        splunk_index: splunkIndex,
        enabled: true,
        export_detections: true,
        export_events: exportEvents,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['siem-configs'] });
      onClose();
    },
  });

  return (
    <form
      className={styles.configForm}
      onSubmit={(e) => {
        e.preventDefault();
        createMutation.mutate();
      }}
    >
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="splunk-name">
          Display Name
        </label>
        <input
          id="splunk-name"
          className={styles.configInput}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="Splunk HEC"
        />
        <span className={styles.configHelp}>
          A friendly name to identify this Splunk HEC export in the dashboard.
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="splunk-url">
          HEC Endpoint URL
        </label>
        <input
          id="splunk-url"
          className={styles.configInput}
          value={hecUrl}
          onChange={(e) => setHecUrl(e.target.value)}
          placeholder="https://splunk.example.com:8088/services/collector"
          required
        />
        <span className={styles.configHelp}>
          Splunk HTTP Event Collector URL including port and path.
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="splunk-token">
          HEC Token Environment Variable
        </label>
        <input
          id="splunk-token"
          className={styles.configInput}
          value={tokenEnvVar}
          onChange={(e) => setTokenEnvVar(e.target.value)}
          placeholder="SPLUNK_HEC_TOKEN"
          required
        />
        <span className={styles.configHelp}>
          Name of the environment variable holding the Splunk HEC token.
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="splunk-index">
          Splunk Index
        </label>
        <input
          id="splunk-index"
          className={styles.configInput}
          value={splunkIndex}
          onChange={(e) => setSplunkIndex(e.target.value)}
          placeholder="main"
        />
        <span className={styles.configHelp}>
          Target Splunk index for ingested events. Defaults to &apos;main&apos;.
        </span>
      </div>
      <div className={styles.configField}>
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 13,
            color: 'var(--fg)',
          }}
        >
          <input
            type="checkbox"
            checked={exportEvents}
            onChange={(e) => setExportEvents(e.target.checked)}
          />
          Also stream raw audit events (not just detections)
        </label>
        <span className={styles.configHelp}>
          When checked, raw audit log events are also forwarded alongside detection exports.
        </span>
      </div>
      {createMutation.isError && (
        <div className={styles.configError}>Failed to save configuration. Please try again.</div>
      )}
      <div className={styles.configActions}>
        <Button size="sm" type="button" onClick={onClose}>
          Cancel
        </Button>
        <Button
          variant="primary"
          size="sm"
          disabled={!hecUrl || !tokenEnvVar || createMutation.isPending}
        >
          {createMutation.isPending ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  SOAR Webhook config form                                          */
/* ------------------------------------------------------------------ */

function SoarWebhookConfigForm({ onClose }: { onClose: () => void }) {
  const [displayName, setDisplayName] = useState('SOAR Webhook');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [secretEnvVar, setSecretEnvVar] = useState('');
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: () =>
      createSiemConfig({
        export_type: 'webhook',
        display_name: displayName || 'SOAR Webhook',
        webhook_url: webhookUrl,
        webhook_secret_env_var: secretEnvVar || undefined,
        enabled: true,
        export_detections: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['siem-configs'] });
      onClose();
    },
  });

  return (
    <form
      className={styles.configForm}
      onSubmit={(e) => {
        e.preventDefault();
        createMutation.mutate();
      }}
    >
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="soar-name">
          Display Name
        </label>
        <input
          id="soar-name"
          className={styles.configInput}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="SOAR Webhook"
        />
        <span className={styles.configHelp}>
          A friendly name to identify this SOAR webhook in the dashboard.
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="soar-url">
          Webhook URL
        </label>
        <input
          id="soar-url"
          className={styles.configInput}
          value={webhookUrl}
          onChange={(e) => setWebhookUrl(e.target.value)}
          placeholder="https://soar.example.com/api/webhook/octowatch"
          required
        />
        <span className={styles.configHelp}>
          The HTTPS endpoint of your SOAR platform that will receive detection events.
        </span>
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="soar-secret">
          Signing Secret Environment Variable
        </label>
        <input
          id="soar-secret"
          className={styles.configInput}
          value={secretEnvVar}
          onChange={(e) => setSecretEnvVar(e.target.value)}
          placeholder="SOAR_WEBHOOK_SECRET"
        />
        <span className={styles.configHelp}>
          Optional. Payloads will be signed with HMAC-SHA256 if set.
        </span>
      </div>
      {createMutation.isError && (
        <div className={styles.configError}>Failed to save configuration. Please try again.</div>
      )}
      <div className={styles.configActions}>
        <Button size="sm" type="button" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="primary" size="sm" disabled={!webhookUrl || createMutation.isPending}>
          {createMutation.isPending ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Integrations Pane                                                  */
/* ------------------------------------------------------------------ */

function IntegrationsPane() {
  const [configTarget, setConfigTarget] = useState<string | null>(null);

  const { data: notificationConfigs } = useQuery({
    queryKey: ['notification-configs'],
    queryFn: listNotificationConfigs,
  });

  const { data: ticketingConfigs } = useQuery({
    queryKey: ['ticketing-configs'],
    queryFn: listTicketingConfigs,
  });

  const { data: siemConfigs } = useQuery({
    queryKey: ['siem-configs'],
    queryFn: listSiemConfigs,
  });

  const notifConfigs = notificationConfigs ?? [];
  const ticketConfigs = ticketingConfigs ?? [];
  const siemCfgs = siemConfigs ?? [];

  function getStatus(key: string): { configured: boolean; enabled: boolean } {
    switch (key) {
      case 'slack': {
        const found = notifConfigs.filter((c) => c.channel_type === 'slack');
        return { configured: found.length > 0, enabled: found.some((c) => c.enabled) };
      }
      case 'jira': {
        const found = ticketConfigs.filter((c) => c.provider === 'jira');
        return { configured: found.length > 0, enabled: found.some((c) => c.enabled) };
      }
      case 'sentinel': {
        const found = notifConfigs.filter(
          (c) => c.channel_type === 'webhook' && c.display_name.toLowerCase().includes('sentinel'),
        );
        return { configured: found.length > 0, enabled: found.some((c) => c.enabled) };
      }
      case 'splunk': {
        const found = notifConfigs.filter(
          (c) => c.channel_type === 'webhook' && c.display_name.toLowerCase().includes('splunk'),
        );
        return { configured: found.length > 0, enabled: found.some((c) => c.enabled) };
      }
      case 'pagerduty': {
        const found = notifConfigs.filter((c) => c.channel_type === 'pagerduty');
        return { configured: found.length > 0, enabled: found.some((c) => c.enabled) };
      }
      case 'syslog_cef': {
        const found = siemCfgs.filter((c) => c.export_type === 'syslog');
        return { configured: found.length > 0, enabled: found.some((c) => c.enabled) };
      }
      case 'splunk_hec': {
        const found = siemCfgs.filter((c) => c.export_type === 'splunk_hec');
        return { configured: found.length > 0, enabled: found.some((c) => c.enabled) };
      }
      case 'soar_webhook': {
        const found = siemCfgs.filter((c) => c.export_type === 'webhook');
        return { configured: found.length > 0, enabled: found.some((c) => c.enabled) };
      }
      default:
        return { configured: false, enabled: false };
    }
  }

  function getConfigModalTitle(key: string): string {
    const info = INTEGRATION_INFO.find((i) => i.key === key);
    return info ? `Configure ${info.label}` : '';
  }

  return (
    <div className={styles.featuresPane}>
      <p className={styles.featuresDescription}>
        Connect external services to extend OctoWatch capabilities. GitHub Enterprise is always
        connected and managed in the GitHub tab.
      </p>
      <div className={styles.featuresList}>
        {INTEGRATION_INFO.map(({ key, label, description, icon, iconBg }) => {
          const { configured, enabled } = getStatus(key);
          return (
            <div key={key} className={styles.featureRow} data-testid={`integration-card-${key}`}>
              <div className={styles.integrationCardLeft}>
                <div
                  className={styles.integrationIcon}
                  style={{ backgroundColor: iconBg }}
                  title={label}
                >
                  {icon}
                </div>
                <div className={styles.featureInfo}>
                  <div className={styles.featureLabel}>
                    {label}
                    {configured && (
                      <span
                        className={styles.integrationStatus}
                        data-status={enabled ? 'active' : 'configured'}
                        title={
                          enabled
                            ? `${label} is active and sending data`
                            : `${label} is configured but currently disabled`
                        }
                      >
                        {enabled ? 'Active' : 'Configured'}
                      </span>
                    )}
                    {!configured && (
                      <span
                        className={styles.integrationStatus}
                        data-status="inactive"
                        title={`${label} has not been set up yet`}
                      >
                        Not configured
                      </span>
                    )}
                  </div>
                  <div className={styles.featureDescription}>{description}</div>
                </div>
              </div>
              <Button
                size="sm"
                variant={configured ? undefined : 'primary'}
                onClick={() => setConfigTarget(key)}
              >
                {configured ? 'Configure' : 'Set up'}
              </Button>
            </div>
          );
        })}
      </div>

      {/* Slack config modal */}
      <Drawer
        open={configTarget === 'slack'}
        onClose={() => setConfigTarget(null)}
        title="Configure Slack"
      >
        <SlackConfigForm onClose={() => setConfigTarget(null)} />
      </Drawer>

      {/* Jira config modal */}
      <Drawer
        open={configTarget === 'jira'}
        onClose={() => setConfigTarget(null)}
        title="Configure Jira"
      >
        <JiraConfigForm onClose={() => setConfigTarget(null)} />
      </Drawer>

      {/* Webhook-based config modal (Sentinel, Splunk, PagerDuty) */}
      <Drawer
        open={configTarget !== null && ['sentinel', 'splunk', 'pagerduty'].includes(configTarget)}
        onClose={() => setConfigTarget(null)}
        title={getConfigModalTitle(configTarget ?? '')}
      >
        {configTarget && ['sentinel', 'splunk', 'pagerduty'].includes(configTarget) && (
          <WebhookConfigForm
            name={INTEGRATION_INFO.find((i) => i.key === configTarget)?.label ?? configTarget}
            onClose={() => setConfigTarget(null)}
          />
        )}
      </Drawer>

      {/* Syslog/CEF config modal */}
      <Drawer
        open={configTarget === 'syslog_cef'}
        onClose={() => setConfigTarget(null)}
        title="Configure Syslog / CEF Export"
      >
        <SyslogConfigForm onClose={() => setConfigTarget(null)} />
      </Drawer>

      {/* Splunk HEC config modal */}
      <Drawer
        open={configTarget === 'splunk_hec'}
        onClose={() => setConfigTarget(null)}
        title="Configure Splunk HEC Export"
      >
        <SplunkHecConfigForm onClose={() => setConfigTarget(null)} />
      </Drawer>

      {/* SOAR Webhook config modal */}
      <Drawer
        open={configTarget === 'soar_webhook'}
        onClose={() => setConfigTarget(null)}
        title="Configure SOAR Webhook"
      >
        <SoarWebhookConfigForm onClose={() => setConfigTarget(null)} />
      </Drawer>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Category Setting Form helpers                                      */
/* ------------------------------------------------------------------ */

interface SettingFieldDef {
  key: string;
  label: string;
  description: string;
  type: 'text' | 'number' | 'toggle' | 'select';
  defaultValue: string;
  options?: string[];
  min?: number;
  max?: number;
}

function getSettingValue(settings: AppSetting[], key: string, defaultValue: string): string {
  const found = settings.find((s) => s.key === key);
  return found ? found.value : defaultValue;
}

/* ------------------------------------------------------------------ */
/*  Category Settings Form                                             */
/* ------------------------------------------------------------------ */

function CategorySettingsForm({
  category,
  fields,
  description,
  settings,
}: {
  category: string;
  fields: SettingFieldDef[];
  description: string;
  settings: AppSetting[];
}) {
  const queryClient = useQueryClient();
  const categorySettings = settings.filter(
    (s) => s.category.toLowerCase() === category.toLowerCase(),
  );

  const initialValues: Record<string, string> = {};
  for (const field of fields) {
    initialValues[field.key] = getSettingValue(categorySettings, field.key, field.defaultValue);
  }

  const [values, setValues] = useState(initialValues);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleChange = useCallback((key: string, value: string) => {
    setValues((prev) => ({ ...prev, [key]: value }));
    setSaveMessage(null);
    setSaveError(null);
  }, []);

  const hasChanges = fields.some(
    (f) => values[f.key] !== getSettingValue(categorySettings, f.key, f.defaultValue),
  );

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    setSaveMessage(null);
    try {
      for (const field of fields) {
        const currentValue = getSettingValue(categorySettings, field.key, field.defaultValue);
        if (values[field.key] !== currentValue) {
          await updateSetting(field.key, values[field.key], field.description, {
            category,
            sensitivity: 'normal',
          });
        }
      }
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['settings', 'audit-trail'] });
      setSaveMessage('Settings saved successfully.');
      setTimeout(() => setSaveMessage(null), 3000);
    } catch {
      setSaveError('Failed to save settings. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={styles.featuresPane}>
      <p className={styles.featuresDescription}>{description}</p>
      <div className={styles.categoryForm}>
        {fields.map((field) => (
          <div key={field.key} className={styles.categoryFormRow}>
            <div className={styles.categoryFormInfo}>
              <label className={styles.categoryFormLabel} htmlFor={`setting-${field.key}`}>
                {field.label}
              </label>
              <span className={styles.categoryFormHint}>{field.description}</span>
            </div>
            <div className={styles.categoryFormControl}>
              {field.type === 'toggle' ? (
                <label className={styles.toggleSwitch}>
                  <input
                    id={`setting-${field.key}`}
                    type="checkbox"
                    checked={values[field.key] === 'true'}
                    onChange={(e) => handleChange(field.key, e.target.checked ? 'true' : 'false')}
                  />
                  <span className={styles.toggleSlider} />
                </label>
              ) : field.type === 'select' ? (
                <select
                  id={`setting-${field.key}`}
                  className={styles.categoryFormSelect}
                  value={values[field.key]}
                  onChange={(e) => handleChange(field.key, e.target.value)}
                >
                  {field.options?.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id={`setting-${field.key}`}
                  className={styles.categoryFormInput}
                  type={field.type}
                  value={values[field.key]}
                  onChange={(e) => handleChange(field.key, e.target.value)}
                  min={field.min}
                  max={field.max}
                />
              )}
            </div>
          </div>
        ))}
        {saveMessage && <div className={styles.configSuccess}>{saveMessage}</div>}
        {saveError && <div className={styles.configError}>{saveError}</div>}
        <div className={styles.categoryFormActions}>
          <Button variant="primary" size="sm" disabled={saving || !hasChanges} onClick={handleSave}>
            {saving ? 'Saving…' : 'Save changes'}
          </Button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Retention policy pane                                              */
/* ------------------------------------------------------------------ */

const TABLE_LABELS: Record<string, string> = {
  events: 'Audit Events',
  audit_trail: 'Audit Trail',
  detections: 'Detections',
  event_raw_payloads: 'Raw Payloads',
  event_dedup: 'Dedup Index',
  enterprise_sync_log_entries: 'Sync Logs',
  behavioral_baselines: 'Baselines',
  system_health_events: 'Health Events',
};

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / k ** i).toFixed(1)} ${sizes[i]}`;
}

function RetentionPane() {
  const qc = useQueryClient();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['admin', 'retention'],
    queryFn: getRetentionPolicies,
  });

  const [edited, setEdited] = useState<Record<string, number>>({});
  const hasChanges = Object.keys(edited).length > 0;

  const saveMutation = useMutation({
    mutationFn: (policies: Record<string, number>) => updateRetentionPolicies(policies),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'retention'] });
      setEdited({});
    },
  });

  const handleChange = (tableName: string, value: number, currentDays: number) => {
    if (value === currentDays) {
      const next = { ...edited };
      delete next[tableName];
      setEdited(next);
    } else {
      setEdited((prev) => ({ ...prev, [tableName]: value }));
    }
  };

  if (isError)
    return <ErrorBanner message="Failed to load retention policies" onRetry={() => refetch()} />;
  if (isLoading || !data) return <Spinner />;

  return (
    <div>
      <p style={{ color: 'var(--fg-subtle)', fontSize: '0.875rem', marginBottom: '1rem' }}>
        Configure how long each data type is retained before automatic cleanup. Expired data can be
        archived to S3/MinIO before deletion if archival is enabled.
      </p>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Table</th>
              <th>Time Column</th>
              <th>Retention (days)</th>
              <th>Default</th>
              <th>Rows</th>
              <th>Size</th>
            </tr>
          </thead>
          <tbody>
            {data.policies.map((p: RetentionPolicyItem) => (
              <tr key={p.table_name}>
                <td className={styles.settingKey}>{TABLE_LABELS[p.table_name] ?? p.table_name}</td>
                <td style={{ color: 'var(--fg-subtle)', fontSize: '0.8125rem' }}>
                  {p.time_column}
                </td>
                <td>
                  <input
                    type="number"
                    min={1}
                    max={3650}
                    value={edited[p.table_name] ?? p.retention_days}
                    onChange={(e) =>
                      handleChange(
                        p.table_name,
                        parseInt(e.target.value, 10) || 1,
                        p.retention_days,
                      )
                    }
                    className={styles.formInput}
                    style={{ width: '5rem' }}
                  />
                </td>
                <td style={{ color: 'var(--fg-subtle)' }}>{p.default_days}</td>
                <td>{p.row_count.toLocaleString()}</td>
                <td>{formatBytes(p.size_bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={styles.formActions} style={{ marginTop: '1rem' }}>
        <Button
          disabled={!hasChanges || saveMutation.isPending}
          onClick={() => saveMutation.mutate(edited)}
        >
          {saveMutation.isPending ? 'Saving…' : 'Save Changes'}
        </Button>
        {hasChanges && (
          <Button variant="default" onClick={() => setEdited({})}>
            Cancel
          </Button>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Category pane field definitions                                    */
/* ------------------------------------------------------------------ */

const SECURITY_FIELDS: SettingFieldDef[] = [
  {
    key: 'security.session_timeout',
    label: 'Session timeout (minutes)',
    description: 'Maximum idle time before a user session expires.',
    type: 'number',
    defaultValue: '30',
    min: 5,
    max: 1440,
  },
  {
    key: 'security.mfa_required',
    label: 'Require MFA',
    description: 'Enforce multi-factor authentication for all users.',
    type: 'toggle',
    defaultValue: 'false',
  },
  {
    key: 'security.ip_allowlist_enabled',
    label: 'Enable IP allowlist',
    description: 'Restrict access to specific IP addresses or CIDR ranges.',
    type: 'toggle',
    defaultValue: 'false',
  },
  {
    key: 'security.max_failed_login_attempts',
    label: 'Max failed login attempts',
    description: 'Number of failed login attempts before an account is temporarily locked.',
    type: 'number',
    defaultValue: '5',
    min: 1,
    max: 20,
  },
];

const STORAGE_FIELDS: SettingFieldDef[] = [
  {
    key: 'storage.s3_bucket_name',
    label: 'S3/MinIO bucket name',
    description: 'Object storage bucket for audit log archives and exports.',
    type: 'text',
    defaultValue: '',
  },
  {
    key: 'storage.retention_period_days',
    label: 'Retention period (days)',
    description: 'Number of days to retain archived data before automatic cleanup.',
    type: 'number',
    defaultValue: '90',
    min: 7,
    max: 3650,
  },
  {
    key: 'storage.max_upload_size_mb',
    label: 'Max upload size (MB)',
    description: 'Maximum file size allowed for manual data imports.',
    type: 'number',
    defaultValue: '500',
    min: 1,
    max: 5000,
  },
];

const NOTIFICATIONS_FIELDS: SettingFieldDef[] = [
  {
    key: 'notifications.email_enabled',
    label: 'Email notifications',
    description: 'Send email notifications for alerts and scheduled reports.',
    type: 'toggle',
    defaultValue: 'false',
  },
  {
    key: 'notifications.slack_webhook',
    label: 'Slack webhook URL',
    description: 'Default Slack webhook for system-level notifications.',
    type: 'text',
    defaultValue: '',
  },
  {
    key: 'notifications.alert_threshold',
    label: 'Alert threshold',
    description: 'Minimum number of events before triggering a consolidated alert.',
    type: 'number',
    defaultValue: '5',
    min: 1,
    max: 100,
  },
];

const SYSTEM_FIELDS: SettingFieldDef[] = [
  {
    key: 'system.log_level',
    label: 'Log level',
    description: 'Application logging verbosity level.',
    type: 'select',
    defaultValue: 'info',
    options: ['debug', 'info', 'warning', 'error'],
  },
  {
    key: 'system.debug_mode',
    label: 'Debug mode',
    description: 'Enable verbose debug output and diagnostic endpoints.',
    type: 'toggle',
    defaultValue: 'false',
  },
  {
    key: 'system.maintenance_mode',
    label: 'Maintenance mode',
    description: 'Display a maintenance banner and restrict write operations.',
    type: 'toggle',
    defaultValue: 'false',
  },
  {
    key: 'system.data_retention_days',
    label: 'Data retention (days)',
    description: 'Number of days to retain event and detection data.',
    type: 'number',
    defaultValue: '365',
    min: 30,
    max: 3650,
  },
];

/* ------------------------------------------------------------------ */
/*  Settings Page                                                      */
/* ------------------------------------------------------------------ */

export function SettingsPage() {
  const qc = useQueryClient();
  const { tab: tabSlug } = useParams<{ tab: string }>();
  const navigate = useNavigate();
  const activeTab: Category | 'Audit' | 'Features' | 'Integrations' | 'Retention' =
    SLUG_TO_TAB[tabSlug ?? 'all'] ?? 'All';
  const [editTarget, setEditTarget] = useState<AppSetting | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AppSetting | null>(null);

  const {
    data: settings,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['settings'],
    queryFn: listSettings,
  });

  const updateMutation = useMutation({
    mutationFn: ({
      key,
      value,
      description,
    }: {
      key: string;
      value: string;
      description?: string;
    }) => updateSetting(key, value, description),
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

  const filteredSettings =
    settings?.filter(
      (s: AppSetting) =>
        activeTab === 'All' || s.category.toLowerCase() === (activeTab as string).toLowerCase(),
    ) ?? [];

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
        <button
          className={activeTab === 'Retention' ? styles.tabActive : styles.tab}
          onClick={() => navigate('/settings/retention')}
        >
          Retention
        </button>
      </div>

      {/* Content */}
      {activeTab === 'Features' ? (
        <FeaturesPane />
      ) : activeTab === 'Integrations' ? (
        <IntegrationsPane />
      ) : activeTab === 'Retention' ? (
        <RetentionPane />
      ) : activeTab === 'Audit' ? (
        <AuditTrailTable />
      ) : activeTab === 'GitHub' ? (
        <GitHubPane />
      ) : activeTab === 'Security' ? (
        isLoading ? (
          <Spinner />
        ) : (
          <CategorySettingsForm
            category="Security"
            fields={SECURITY_FIELDS}
            description="Authentication, session management, and access control settings."
            settings={settings ?? []}
          />
        )
      ) : activeTab === 'Storage' ? (
        isLoading ? (
          <Spinner />
        ) : (
          <CategorySettingsForm
            category="Storage"
            fields={STORAGE_FIELDS}
            description="Object storage (MinIO/S3) configuration for audit log archives and data exports."
            settings={settings ?? []}
          />
        )
      ) : activeTab === 'Notifications' ? (
        isLoading ? (
          <Spinner />
        ) : (
          <CategorySettingsForm
            category="Notifications"
            fields={NOTIFICATIONS_FIELDS}
            description="Notification channel configuration for system alerts and scheduled reports."
            settings={settings ?? []}
          />
        )
      ) : activeTab === 'System' ? (
        isLoading ? (
          <Spinner />
        ) : (
          <CategorySettingsForm
            category="System"
            fields={SYSTEM_FIELDS}
            description="System-level configuration including logging, maintenance, and data retention."
            settings={settings ?? []}
          />
        )
      ) : (
        <>
          {isError && <ErrorBanner message="Failed to load settings" onRetry={() => refetch()} />}

          {isLoading ? (
            <Spinner />
          ) : filteredSettings.length === 0 ? (
            <div className={styles.empty}>
              <p>No settings configured yet.</p>
              <p style={{ color: 'var(--fg-subtle)', fontSize: '0.8125rem', marginTop: '0.5rem' }}>
                Settings are automatically populated during setup and sync. You can also add custom
                settings using the admin API.
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
                          <Button size="sm" onClick={() => setEditTarget(s)}>
                            Edit
                          </Button>
                          <Button size="sm" variant="danger" onClick={() => setDeleteTarget(s)}>
                            Reset
                          </Button>
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
      <Modal
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
        title={`Edit: ${editTarget?.key ?? ''}`}
      >
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
