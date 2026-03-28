import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listTicketingConfigs,
  listNotificationConfigs,
  createNotificationConfig,
  createTicketingConfig,
} from '../../api/integrations';
import { getSyncConfig, updateSyncConfig } from '../../api/sync';
import { Button } from '../../components/primitives/Button';
import { Modal } from '../../components/primitives/Modal';
import { SyncPanel } from './SyncPanel';
import { SyncRunHistory } from './SyncRunHistory';
import { ManualIngestPanel } from './ManualIngestPanel';
import styles from './Integrations.module.css';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type IntegrationStatus = 'connected' | 'configured' | 'not_installed';

interface MarketplaceIntegration {
  name: string;
  description: string;
  icon: React.ReactNode;
  status: IntegrationStatus;
  iconBg: string;
}

/* ------------------------------------------------------------------ */
/*  Icons                                                              */
/* ------------------------------------------------------------------ */

function GitHubEnterpriseIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 2a10 10 0 00-3.16 19.49c.5.09.68-.22.68-.48v-1.7c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.89 1.52 2.34 1.08 2.91.83.09-.65.35-1.08.63-1.33-2.22-.25-4.56-1.11-4.56-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02A9.56 9.56 0 0112 6.84c.85 0 1.71.12 2.51.34 1.91-1.29 2.75-1.02 2.75-1.02.55 1.37.2 2.39.1 2.64.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.69-4.57 4.93.36.31.68.92.68 1.85v2.74c0 .27.18.58.69.48A10 10 0 0012 2z" fill="white" />
    </svg>
  );
}

function SlackIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="8" cy="12" r="2" fill="#E01E5A" />
      <circle cx="12" cy="8" r="2" fill="#36C5F0" />
      <circle cx="16" cy="12" r="2" fill="#2EB67D" />
      <circle cx="12" cy="16" r="2" fill="#ECB22E" />
    </svg>
  );
}

function SentinelIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M13 3l7 14H6L13 3z" fill="white" fillOpacity="0.9" />
      <path d="M13 9v4M13 15h.01" stroke="#0078d4" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function SplunkIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 18L12 4l7 14H5z" fill="white" fillOpacity="0.85" />
      <path d="M12 10v4" stroke="#1a1a1a" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function PagerDutyIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8" stroke="white" strokeWidth="2" fill="none" />
      <circle cx="12" cy="12" r="3" fill="white" />
    </svg>
  );
}

function JiraIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 13l4-4 2 2 6-6" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M14 5h6v6" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Marketplace card component                                         */
/* ------------------------------------------------------------------ */

function statusMeta(status: IntegrationStatus): { label: string; className: string } {
  switch (status) {
    case 'connected':
      return { label: 'Connected', className: styles.statusConnected };
    case 'configured':
      return { label: 'Configured', className: styles.statusConfigured };
    case 'not_installed':
      return { label: 'Not installed', className: styles.statusNotInstalled };
  }
}

function MktCard({ integration, onConfigure }: { integration: MarketplaceIntegration; onConfigure?: () => void }) {
  const { label, className } = statusMeta(integration.status);
  const isInstalled = integration.status !== 'not_installed';

  return (
    <div className={styles.mktCard} data-testid={`mkt-card-${integration.name.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className={styles.mktCardHeader}>
        <div className={styles.mktCardIcon} style={{ backgroundColor: integration.iconBg }}>
          {integration.icon}
        </div>
        <div className={styles.mktCardInfo}>
          <p className={styles.mktCardName}>{integration.name}</p>
          <p className={styles.mktCardDesc}>{integration.description}</p>
        </div>
      </div>
      <div className={styles.mktCardFooter}>
        <span
          className={`${styles.statusLabel} ${className} ${styles.clickableStatus}`}
          tabIndex={0}
          aria-label={`${integration.name} status: ${label}`}
          onClick={onConfigure}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onConfigure?.();
            }
          }}
        >
          <span className={styles.statusDot} />
          {label}
        </span>
        {isInstalled ? (
          <Button size="sm" onClick={onConfigure}>Configure</Button>
        ) : (
          <Button variant="primary" size="sm" onClick={onConfigure}>Configure</Button>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  GitHub Enterprise config form                                      */
/* ------------------------------------------------------------------ */

function GitHubEnterpriseConfigForm({ onClose }: { onClose: () => void }) {
  const { data: config, isLoading } = useQuery({
    queryKey: ['sync-config'],
    queryFn: getSyncConfig,
  });

  if (isLoading || !config) {
    return <p style={{ margin: 0, color: 'var(--fg-muted)', fontSize: 13 }}>Loading configuration…</p>;
  }

  return <ConfigFormFields config={config} onClose={onClose} />;
}

function ConfigFormFields({ config, onClose }: { config: import('../../types/sync').SyncConfig; onClose: () => void }) {
  const queryClient = useQueryClient();

  const [syncEnabled, setSyncEnabled] = useState(config.sync_enabled);
  const [intervalDays, setIntervalDays] = useState(config.interval_days);
  const [orgsText, setOrgsText] = useState(config.orgs.join(', '));
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const saveMutation = useMutation({
    mutationFn: () => {
      const orgs = orgsText
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      return updateSyncConfig({
        sync_enabled: syncEnabled,
        interval_days: intervalDays,
        orgs,
      });
    },
    onSuccess: () => {
      setSuccessMessage('Configuration saved successfully.');
      queryClient.invalidateQueries({ queryKey: ['sync-config'] });
      setTimeout(() => setSuccessMessage(null), 3000);
    },
  });

  function handleCancel() {
    setSyncEnabled(config.sync_enabled);
    setIntervalDays(config.interval_days);
    setOrgsText(config.orgs.join(', '));
    onClose();
  }

  const intervalInvalid = intervalDays < 60 || intervalDays > 90;

  return (
    <div className={styles.configForm}>
      {/* Sync enabled toggle */}
      <div className={styles.configField}>
        <div className={styles.configToggleRow}>
          <label className={styles.configLabel} htmlFor="sync-enabled-toggle">
            Enable scheduled sync
          </label>
          <input
            id="sync-enabled-toggle"
            type="checkbox"
            checked={syncEnabled}
            onChange={(e) => setSyncEnabled(e.target.checked)}
          />
        </div>
      </div>

      {/* Interval days */}
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="sync-interval-input">
          Sync interval (days)
        </label>
        <input
          id="sync-interval-input"
          type="number"
          className={styles.configInput}
          min={60}
          max={90}
          value={intervalDays}
          onChange={(e) => setIntervalDays(Number(e.target.value))}
        />
        {intervalInvalid && (
          <span className={styles.configHelp} style={{ color: 'var(--danger)' }}>
            Must be between 60 and 90 days.
          </span>
        )}
      </div>

      {/* Organizations */}
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="sync-orgs-input">
          Organizations to sync
        </label>
        <input
          id="sync-orgs-input"
          type="text"
          className={styles.configInput}
          value={orgsText}
          onChange={(e) => setOrgsText(e.target.value)}
          placeholder="e.g. acme-corp, widgets-inc"
        />
        <span className={styles.configHelp}>
          Leave empty to sync all organizations. Comma-separated org slugs.
        </span>
      </div>

      {/* Read-only info */}
      <dl className={styles.configReadonly}>
        <dt>App ID</dt>
        <dd>{config.app_id ?? '—'}</dd>
        <dt>Enterprise slug</dt>
        <dd>{config.enterprise_slug ?? '—'}</dd>
        <dt>Installations</dt>
        <dd>{config.installation_ids.length}</dd>
        <dd className={styles.configHelp}>
          GitHub App credentials are configured via environment variables.
        </dd>
      </dl>

      {successMessage && (
        <div className={styles.configSuccess}>{successMessage}</div>
      )}
      {saveMutation.isError && (
        <div className={styles.configError}>
          Failed to save configuration. Please try again.
        </div>
      )}

      {/* Actions */}
      <div className={styles.configActions}>
        <Button size="sm" onClick={handleCancel}>Cancel</Button>
        <Button
          size="sm"
          variant="primary"
          disabled={saveMutation.isPending || intervalInvalid}
          onClick={() => saveMutation.mutate()}
        >
          {saveMutation.isPending ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </div>
  );
}

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
        <label className={styles.configLabel} htmlFor="slack-display-name">Display Name</label>
        <input
          id="slack-display-name"
          className={styles.configInput}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="e.g. #security-alerts"
        />
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="slack-webhook-url">Webhook URL</label>
        <input
          id="slack-webhook-url"
          className={styles.configInput}
          value={webhookUrl}
          onChange={(e) => setWebhookUrl(e.target.value)}
          placeholder="https://hooks.slack.com/services/..."
          required
        />
      </div>
      <div className={styles.configField}>
        <span className={styles.configLabel}>Alert severities</span>
        <div style={{ display: 'flex', gap: 12, marginTop: 4 }}>
          {['critical', 'high', 'medium', 'low'].map((s) => (
            <label key={s} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--fg)' }}>
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
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="slack-cooldown">Cooldown (seconds)</label>
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
        <Button size="sm" onClick={onClose}>Cancel</Button>
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
        <label className={styles.configLabel} htmlFor="jira-display-name">Display Name</label>
        <input
          id="jira-display-name"
          className={styles.configInput}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="e.g. Security Project"
        />
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="jira-base-url">Jira Base URL</label>
        <input
          id="jira-base-url"
          className={styles.configInput}
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://your-org.atlassian.net"
          required
        />
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="jira-project-key">Project Key</label>
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
        <label className={styles.configLabel} htmlFor="jira-credential">API Token Environment Variable</label>
        <input
          id="jira-credential"
          className={styles.configInput}
          value={credentialEnvVar}
          onChange={(e) => setCredentialEnvVar(e.target.value)}
          placeholder="JIRA_API_TOKEN"
          required
        />
        <span className={styles.configHelp}>Name of the environment variable holding the Jira API token.</span>
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
      </div>
      {createMutation.isError && (
        <div className={styles.configError}>Failed to save configuration. Please try again.</div>
      )}
      <div className={styles.configActions}>
        <Button size="sm" onClick={onClose}>Cancel</Button>
        <Button variant="primary" size="sm" disabled={!baseUrl || !credentialEnvVar || createMutation.isPending}>
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
        <label className={styles.configLabel} htmlFor="webhook-display-name">Display Name</label>
        <input
          id="webhook-display-name"
          className={styles.configInput}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder={name}
        />
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="webhook-url">Endpoint URL</label>
        <input
          id="webhook-url"
          className={styles.configInput}
          value={webhookUrl}
          onChange={(e) => setWebhookUrl(e.target.value)}
          placeholder={placeholderUrl}
          required
        />
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="webhook-credential">Auth Token Environment Variable</label>
        <input
          id="webhook-credential"
          className={styles.configInput}
          value={credentialEnvVar}
          onChange={(e) => setCredentialEnvVar(e.target.value)}
          placeholder={`${name.toUpperCase().replace(/\s+/g, '_')}_TOKEN`}
        />
        <span className={styles.configHelp}>Optional. Name of the environment variable holding the auth token.</span>
      </div>
      <div className={styles.configField}>
        <span className={styles.configLabel}>Alert severities</span>
        <div style={{ display: 'flex', gap: 12, marginTop: 4 }}>
          {['critical', 'high', 'medium', 'low'].map((s) => (
            <label key={s} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--fg)' }}>
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
      </div>
      <div className={styles.configField}>
        <label className={styles.configLabel} htmlFor="webhook-cooldown">Cooldown (seconds)</label>
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
        <Button size="sm" onClick={onClose}>Cancel</Button>
        <Button variant="primary" size="sm" disabled={!webhookUrl || createMutation.isPending}>
          {createMutation.isPending ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Main page                                                          */
/* ------------------------------------------------------------------ */

export function IntegrationsPage() {
  const [configTarget, setConfigTarget] = useState<string | null>(null);

  /* Keep API hooks alive so integration data is cached for future use */
  const { data: ticketingConfigs } = useQuery({ queryKey: ['ticketing-configs'], queryFn: listTicketingConfigs });
  const { data: notificationConfigs } = useQuery({ queryKey: ['notification-configs'], queryFn: listNotificationConfigs });

  const { data: syncConfig } = useQuery({
    queryKey: ['sync-config'],
    queryFn: getSyncConfig,
  });

  const ghStatus: IntegrationStatus = syncConfig?.app_id ? 'connected' : 'not_installed';

  const slackConfigured = (notificationConfigs ?? []).some((c) => c.channel_type === 'slack');
  const jiraConfigured = (ticketingConfigs ?? []).some((c) => c.provider === 'jira');
  const pagerdutyConfigured = (notificationConfigs ?? []).some((c) => c.channel_type === 'pagerduty');
  const webhookConfigs = (notificationConfigs ?? []).filter((c) => c.channel_type === 'webhook');
  const sentinelConfigured = webhookConfigs.some((c) => c.display_name.toLowerCase().includes('sentinel'));
  const splunkConfigured = webhookConfigs.some((c) => c.display_name.toLowerCase().includes('splunk'));

  const integrations: MarketplaceIntegration[] = [
    {
      name: 'GitHub Enterprise',
      description: 'Connect your GitHub Enterprise instance for audit log streaming and Copilot metrics.',
      icon: <GitHubEnterpriseIcon />,
      status: ghStatus,
      iconBg: '#24292f',
    },
    {
      name: 'Slack',
      description: 'Send real-time alerts and weekly digest reports to Slack channels.',
      icon: <SlackIcon />,
      status: slackConfigured ? 'configured' : 'not_installed',
      iconBg: '#4a154b',
    },
    {
      name: 'Microsoft Sentinel',
      description: 'Forward normalized security events to Microsoft Sentinel for SIEM correlation.',
      icon: <SentinelIcon />,
      status: sentinelConfigured ? 'configured' : 'not_installed',
      iconBg: '#0078d4',
    },
    {
      name: 'Splunk',
      description: 'Stream audit events and Copilot metrics to Splunk via HEC.',
      icon: <SplunkIcon />,
      status: splunkConfigured ? 'configured' : 'not_installed',
      iconBg: '#1a1a1a',
    },
    {
      name: 'PagerDuty',
      description: 'Trigger PagerDuty incidents for critical security detections.',
      icon: <PagerDutyIcon />,
      status: pagerdutyConfigured ? 'configured' : 'not_installed',
      iconBg: '#06ac38',
    },
    {
      name: 'Jira',
      description: 'Automatically create Jira issues for security findings and track remediation.',
      icon: <JiraIcon />,
      status: jiraConfigured ? 'configured' : 'not_installed',
      iconBg: '#0052CC',
    },
  ];

  return (
    <div className={styles.page}>
      {/* Page header */}
      <div>
        <h1 className={styles.pageTitle}>Integrations</h1>
        <p className={styles.pageSub}>
          Connect external services, import data, and extend OctoWatch capabilities
        </p>
      </div>

      {/* Marketplace grid */}
      <section>
        <h2 className={styles.sectionTitle}>Marketplace</h2>
        <div className={styles.mktGrid}>
          {integrations.map((integration) => (
            <MktCard
              key={integration.name}
              integration={integration}
              onConfigure={() => setConfigTarget(integration.name)}
            />
          ))}
        </div>
      </section>

      {/* Enterprise Sync */}
      <section>
        <h2 className={styles.sectionTitle}>Enterprise Sync</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <SyncPanel />
          <SyncRunHistory />
        </div>
      </section>

      {/* Import Data */}
      <section>
        <h2 className={styles.sectionTitle}>Import Data</h2>
        <ManualIngestPanel />
      </section>

      {/* Configure modal — GitHub Enterprise gets a real form */}
      <Modal
        open={configTarget === 'GitHub Enterprise'}
        onClose={() => setConfigTarget(null)}
        title="Configure GitHub Enterprise"
        width={520}
      >
        <GitHubEnterpriseConfigForm onClose={() => setConfigTarget(null)} />
      </Modal>

      {/* Configure modal — Slack */}
      <Modal
        open={configTarget === 'Slack'}
        onClose={() => setConfigTarget(null)}
        title="Configure Slack"
        width={520}
      >
        <SlackConfigForm onClose={() => setConfigTarget(null)} />
      </Modal>

      {/* Configure modal — Jira */}
      <Modal
        open={configTarget === 'Jira'}
        onClose={() => setConfigTarget(null)}
        title="Configure Jira"
        width={520}
      >
        <JiraConfigForm onClose={() => setConfigTarget(null)} />
      </Modal>

      {/* Configure modal — Webhook-based integrations (Sentinel, Splunk, PagerDuty) */}
      <Modal
        open={configTarget !== null && ['Microsoft Sentinel', 'Splunk', 'PagerDuty'].includes(configTarget)}
        onClose={() => setConfigTarget(null)}
        title={configTarget ? `Configure ${configTarget}` : ''}
        width={520}
      >
        {configTarget && ['Microsoft Sentinel', 'Splunk', 'PagerDuty'].includes(configTarget) && (
          <WebhookConfigForm name={configTarget} onClose={() => setConfigTarget(null)} />
        )}
      </Modal>
    </div>
  );
}
