import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listSettings,
  updateSetting,
  deleteSetting,
  getEnterprisePATStatus,
  saveEnterprisePAT,
  deleteEnterprisePAT,
  testEnterprisePAT,
} from '../../api/setup';
import type { AppSetting } from '../../api/setup';
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
import {
  getSyncConfig,
  getSyncSchedule,
  updateSyncConfig,
  updateSyncSchedule,
  triggerSync,
} from '../../api/sync';
import { PagerDutyIntegration } from '../Integrations/PagerDutyIntegration';
import { TeamsIntegration } from '../Integrations/TeamsIntegration';
import { PageHeader } from '../../components/common/PageHeader';
import { useToast } from '../../hooks/useToast';
import { SlackIntegration } from '../Integrations/SlackIntegration';
import { AuditStreamPanel } from './AuditStreamPanel';
import { MaintenanceSettingsPanel } from './MaintenanceSettingsPanel';
import { Button } from '../../components/primitives/Button';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Drawer } from '../../components/primitives/Drawer';
import { ConfirmDialog } from '../../components/primitives/ConfirmDialog';
import { Spinner } from '../../components/primitives/Spinner';
import { Label } from '../../components/primitives/Label';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { useFeatures } from '../../hooks/useFeatures';
import { formatAbsolute } from '../../utils/dates';
import { getPagerDutyConfig } from '../../api/pagerduty';
import { getTeamsConfig } from '../../api/teams';
import styles from './Settings.module.css';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const CATEGORIES = ['Secrets', 'GitHub', 'Security', 'Notifications', 'System'] as const;
type Category = (typeof CATEGORIES)[number];

const SLUG_TO_TAB: Record<string, Category | 'Features' | 'Integrations' | 'Retention'> = {
  secrets: 'Secrets',
  github: 'GitHub',
  security: 'Security',
  notifications: 'Notifications',
  system: 'System',
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
  const { showToast } = useToast();
  const [tokenInput, setTokenInput] = useState('');
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [showRemoveConfirm, setShowRemoveConfirm] = useState(false);

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
      showToast('Enterprise PAT saved successfully', 'success');
      setTimeout(() => setSaveSuccess(null), 5000);
    },
    onError: (err: Error & { status?: number; body?: { detail?: string } }) => {
      const detail = (err as unknown as { body?: { detail?: string } }).body?.detail ?? err.message;
      setSaveError(detail);
      setSaveSuccess(null);
      showToast('Failed to save Enterprise PAT', 'error');
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
      showToast('Enterprise PAT removed', 'success');
      setTimeout(() => setSaveSuccess(null), 5000);
    },
    onError: (err: Error) => {
      setSaveError(err.message);
      showToast('Failed to remove Enterprise PAT', 'error');
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
        showToast('Connection test successful', 'success');
      } else {
        setTestError(result.message ?? 'Test failed.');
        setTestMessage(null);
        showToast('Connection test failed', 'error');
      }
    },
    onError: (err: Error) => {
      setTestError(err.message);
      setTestMessage(null);
      showToast('Connection test failed', 'error');
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
              onClick={() => setShowRemoveConfirm(true)}
            >
              {deleteMutation.isPending ? 'Removing…' : 'Remove'}
            </Button>
          </>
        )}
      </div>
      <ConfirmDialog
        open={showRemoveConfirm}
        onClose={() => setShowRemoveConfirm(false)}
        title="Remove Enterprise PAT"
        message="Are you sure you want to remove the Enterprise PAT? Audit log ingestion will stop until a new token is configured."
        confirmLabel="Remove"
        confirmVariant="danger"
        onConfirm={() => {
          setShowRemoveConfirm(false);
          deleteMutation.mutate();
        }}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  GitHub Pane                                                        */
/* ------------------------------------------------------------------ */

function EnterprisePATWidget() {
  return (
    <Card>
      <CardHeader>Classic PAT for Audit Log</CardHeader>
      <div className={styles.auditStreamBody}>
        <p className={styles.featuresDescription}>
          The enterprise audit log API requires a classic Personal Access Token with{' '}
          <code>admin:enterprise</code> scope. GitHub App installation tokens cannot access this
          endpoint.
        </p>
        <EnterprisePATSection />
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Sync Setup Wizard Steps                                            */
/* ------------------------------------------------------------------ */

type SyncWizardStep = 'connection' | 'entities' | 'schedule' | 'confirm';

const SYNC_WIZARD_STEPS: { key: SyncWizardStep; label: string }[] = [
  { key: 'connection', label: 'Connection' },
  { key: 'entities', label: 'Entities' },
  { key: 'schedule', label: 'Schedule' },
  { key: 'confirm', label: 'Confirm' },
];

const SYNC_SCOPE_OPTIONS = [
  { value: 'full', label: 'Full sync (all entity types)' },
  { value: 'repos', label: 'Repositories only' },
  { value: 'users', label: 'Users only' },
  { value: 'teams', label: 'Teams only' },
];

const INTERVAL_OPTIONS = [
  { value: 1, label: 'Every hour' },
  { value: 4, label: 'Every 4 hours' },
  { value: 8, label: 'Every 8 hours' },
  { value: 12, label: 'Every 12 hours' },
  { value: 24, label: 'Every 24 hours' },
];

function GitHubSyncSetupPanel() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [wizardOpen, setWizardOpen] = useState(false);
  const [step, setStep] = useState<SyncWizardStep>('connection');

  // Wizard draft state
  const [draftOrgs, setDraftOrgs] = useState<string[]>([]);
  const [draftOrgInput, setDraftOrgInput] = useState('');
  const [draftSyncEnabled, setDraftSyncEnabled] = useState(true);
  const [draftScheduleEnabled, setDraftScheduleEnabled] = useState(true);
  const [draftInterval, setDraftInterval] = useState(4);
  const [draftScope, setDraftScope] = useState('full');

  const {
    data: config,
    isLoading: configLoading,
    isError: configError,
    error: configErrorObj,
    refetch: refetchConfig,
  } = useQuery({ queryKey: ['sync-config'], queryFn: getSyncConfig });

  const {
    data: schedule,
    isLoading: scheduleLoading,
    isError: scheduleError,
    error: scheduleErrorObj,
    refetch: refetchSchedule,
  } = useQuery({ queryKey: ['sync-schedule'], queryFn: getSyncSchedule });

  const configMutation = useMutation({
    mutationFn: (updates: { sync_enabled?: boolean; orgs?: string[] }) => updateSyncConfig(updates),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['sync-config'] });
    },
  });

  const scheduleMutation = useMutation({
    mutationFn: (updates: { enabled?: boolean; interval_hours?: number; scope?: string }) =>
      updateSyncSchedule(updates),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['sync-schedule'] });
    },
  });

  const triggerMutation = useMutation({
    mutationFn: (scope: string) => triggerSync(scope),
  });

  const isLoading = configLoading || scheduleLoading;
  const isError = configError || scheduleError;
  const errorMessage = configError
    ? configErrorObj instanceof Error
      ? configErrorObj.message
      : 'Failed to load sync config.'
    : scheduleErrorObj instanceof Error
      ? scheduleErrorObj.message
      : 'Failed to load sync schedule.';

  function openWizard() {
    // Pre-populate wizard with current config
    setDraftOrgs(config?.orgs ?? []);
    setDraftSyncEnabled(config?.sync_enabled ?? true);
    setDraftScheduleEnabled(schedule?.enabled ?? true);
    setDraftInterval(schedule?.interval_hours ?? 4);
    setDraftScope(schedule?.scope ?? 'full');
    setDraftOrgInput('');
    setStep('connection');
    setWizardOpen(true);
  }

  function handleAddOrg(inputValue?: string) {
    const org = (inputValue ?? draftOrgInput).trim().toLowerCase();
    if (org && !draftOrgs.includes(org)) {
      setDraftOrgs([...draftOrgs, org]);
    }
    setDraftOrgInput('');
  }

  function handleRemoveOrg(org: string) {
    setDraftOrgs(draftOrgs.filter((o) => o !== org));
  }

  function handleOrgInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddOrg(e.currentTarget.value);
    }
  }

  async function handleSaveConfig() {
    try {
      await configMutation.mutateAsync({
        sync_enabled: draftSyncEnabled,
        orgs: draftOrgs,
      });
      await scheduleMutation.mutateAsync({
        enabled: draftScheduleEnabled,
        interval_hours: draftInterval,
        scope: draftScope,
      });
      setWizardOpen(false);
      showToast('Sync configuration saved successfully', 'success');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to save sync configuration.';
      showToast(msg, 'error');
    }
  }

  async function handleTriggerSync() {
    try {
      await triggerMutation.mutateAsync(schedule?.scope ?? 'full');
      showToast('Sync triggered successfully', 'success');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to trigger sync.';
      showToast(msg, 'error');
    }
  }

  const stepIndex = SYNC_WIZARD_STEPS.findIndex((s) => s.key === step);
  const isSaving = configMutation.isPending || scheduleMutation.isPending;

  if (isLoading) {
    return (
      <Card>
        <CardHeader>GitHub Enterprise Sync</CardHeader>
        <div style={{ padding: '2rem', textAlign: 'center' }}>
          <Spinner size={24} />
        </div>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card>
        <CardHeader>GitHub Enterprise Sync</CardHeader>
        <div style={{ padding: '1rem' }}>
          <ErrorBanner
            message={errorMessage}
            onRetry={() => {
              void refetchConfig();
              void refetchSchedule();
            }}
          />
        </div>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader>GitHub Enterprise Sync</CardHeader>
        <div className={styles.auditStreamBody} data-testid="sync-setup-summary">
          <p className={styles.featuresDescription}>
            Sync configuration determines which GitHub Enterprise data is pulled into OctoWatch and
            how often.
          </p>
          <div className={styles.configGrid}>
            <div className={styles.configRow}>
              <span className={styles.configLabel}>Connection</span>
              <span className={styles.configValue}>
                <code>
                  {config?.enterprise_slug
                    ? `Enterprise: ${config.enterprise_slug}`
                    : 'Not configured'}
                </code>
                {config?.app_id && <Label variant="success">Connected</Label>}
              </span>
            </div>
            <div className={styles.configRow}>
              <span className={styles.configLabel}>Sync status</span>
              <span className={styles.configValue}>
                <Label variant={config?.sync_enabled ? 'success' : 'muted'}>
                  {config?.sync_enabled ? 'Enabled' : 'Disabled'}
                </Label>
              </span>
            </div>
            <div className={styles.configRow}>
              <span className={styles.configLabel}>Organizations</span>
              <span className={styles.configValue}>
                <code>{config?.orgs?.length ? config.orgs.join(', ') : 'All (default)'}</code>
              </span>
            </div>
            <div className={styles.configRow}>
              <span className={styles.configLabel}>Schedule</span>
              <span className={styles.configValue}>
                <code>
                  {schedule?.enabled
                    ? `Every ${schedule.interval_hours}h — ${schedule.scope} scope`
                    : 'Disabled'}
                </code>
              </span>
            </div>
            {schedule?.next_run_at && (
              <div className={styles.configRow}>
                <span className={styles.configLabel}>Next run</span>
                <span className={styles.configValue}>
                  <code>{formatAbsolute(schedule.next_run_at)}</code>
                </span>
              </div>
            )}
          </div>
          <div className={styles.configActions}>
            <Button variant="primary" size="sm" onClick={openWizard}>
              Configure Sync
            </Button>
            <Button
              size="sm"
              disabled={!config?.sync_enabled || triggerMutation.isPending}
              onClick={() => void handleTriggerSync()}
            >
              {triggerMutation.isPending ? 'Triggering…' : 'Trigger Sync Now'}
            </Button>
          </div>
        </div>
      </Card>

      {/* Wizard Drawer */}
      <Drawer open={wizardOpen} onClose={() => setWizardOpen(false)} title="Configure GitHub Sync">
        <div className={styles.syncWizard} data-testid="sync-wizard">
          {/* Step indicator */}
          <div className={styles.syncWizardSteps}>
            {SYNC_WIZARD_STEPS.map((s, idx) => (
              <div
                key={s.key}
                className={
                  idx === stepIndex
                    ? styles.syncWizardStepActive
                    : idx < stepIndex
                      ? styles.syncWizardStepDone
                      : styles.syncWizardStepPending
                }
              >
                <span className={styles.syncWizardStepNumber}>{idx + 1}</span>
                <span className={styles.syncWizardStepLabel}>{s.label}</span>
              </div>
            ))}
          </div>

          {/* Step content */}
          <div className={styles.syncWizardContent}>
            {step === 'connection' && (
              <div data-testid="wizard-step-connection">
                <h4 className={styles.syncWizardTitle}>Connection Details</h4>
                <p className={styles.syncWizardDescription}>
                  Your GitHub App connection status. Connection is managed via the GitHub App
                  installation — update it in GitHub if needed.
                </p>
                <div className={styles.configGrid}>
                  <div className={styles.configRow}>
                    <span className={styles.configLabel}>App ID</span>
                    <span className={styles.configValue}>
                      <code>{config?.app_id ?? 'Not configured'}</code>
                    </span>
                  </div>
                  <div className={styles.configRow}>
                    <span className={styles.configLabel}>Enterprise</span>
                    <span className={styles.configValue}>
                      <code>{config?.enterprise_slug ?? 'Not configured'}</code>
                    </span>
                  </div>
                  <div className={styles.configRow}>
                    <span className={styles.configLabel}>Installations</span>
                    <span className={styles.configValue}>
                      <code>
                        {config?.installation_ids?.length
                          ? `${config.installation_ids.length} org(s)`
                          : 'None'}
                      </code>
                    </span>
                  </div>
                </div>
                <div className={styles.syncWizardField}>
                  <label className={styles.toggleSwitch}>
                    <input
                      type="checkbox"
                      checked={draftSyncEnabled}
                      onChange={(e) => setDraftSyncEnabled(e.target.checked)}
                    />
                    <span className={styles.toggleSlider} />
                  </label>
                  <span className={styles.syncWizardFieldLabel}>Enable data sync</span>
                </div>
              </div>
            )}

            {step === 'entities' && (
              <div data-testid="wizard-step-entities">
                <h4 className={styles.syncWizardTitle}>Entity Selection</h4>
                <p className={styles.syncWizardDescription}>
                  Choose which organizations to sync. Leave empty to sync all organizations
                  accessible by the GitHub App installation.
                </p>
                <div className={styles.syncWizardField}>
                  <label className={styles.configLabel} htmlFor="org-input">
                    Organizations
                  </label>
                  <div className={styles.syncOrgInputRow}>
                    <input
                      id="org-input"
                      className={styles.configInput}
                      value={draftOrgInput}
                      onChange={(e) => setDraftOrgInput(e.target.value)}
                      onKeyDown={handleOrgInputKeyDown}
                      placeholder="Enter org slug and press Enter"
                    />
                    <Button
                      size="sm"
                      onClick={() => handleAddOrg()}
                      disabled={!draftOrgInput.trim()}
                    >
                      Add
                    </Button>
                  </div>
                  {draftOrgs.length > 0 && (
                    <div className={styles.syncOrgTags}>
                      {draftOrgs.map((org) => (
                        <span key={org} className={styles.syncOrgTag}>
                          {org}
                          <button
                            type="button"
                            className={styles.syncOrgTagRemove}
                            onClick={() => handleRemoveOrg(org)}
                            aria-label={`Remove ${org}`}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                  {draftOrgs.length === 0 && (
                    <span className={styles.configHelp}>
                      No organizations specified — all accessible orgs will be synced.
                    </span>
                  )}
                </div>
              </div>
            )}

            {step === 'schedule' && (
              <div data-testid="wizard-step-schedule">
                <h4 className={styles.syncWizardTitle}>Sync Schedule</h4>
                <p className={styles.syncWizardDescription}>
                  Configure how frequently OctoWatch syncs data from GitHub Enterprise.
                </p>
                <div className={styles.syncWizardField}>
                  <label className={styles.toggleSwitch}>
                    <input
                      type="checkbox"
                      checked={draftScheduleEnabled}
                      onChange={(e) => setDraftScheduleEnabled(e.target.checked)}
                    />
                    <span className={styles.toggleSlider} />
                  </label>
                  <span className={styles.syncWizardFieldLabel}>Enable scheduled sync</span>
                </div>
                {draftScheduleEnabled && (
                  <>
                    <div className={styles.syncWizardField}>
                      <label className={styles.configLabel} htmlFor="sync-interval">
                        Interval
                      </label>
                      <select
                        id="sync-interval"
                        className={styles.configInput}
                        value={draftInterval}
                        onChange={(e) => setDraftInterval(Number(e.target.value))}
                      >
                        {INTERVAL_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className={styles.syncWizardField}>
                      <label className={styles.configLabel} htmlFor="sync-scope">
                        Scope
                      </label>
                      <select
                        id="sync-scope"
                        className={styles.configInput}
                        value={draftScope}
                        onChange={(e) => setDraftScope(e.target.value)}
                      >
                        {SYNC_SCOPE_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </>
                )}
              </div>
            )}

            {step === 'confirm' && (
              <div data-testid="wizard-step-confirm">
                <h4 className={styles.syncWizardTitle}>Review &amp; Confirm</h4>
                <p className={styles.syncWizardDescription}>
                  Review your sync configuration before saving.
                </p>
                <div className={styles.configGrid}>
                  <div className={styles.configRow}>
                    <span className={styles.configLabel}>Sync enabled</span>
                    <span className={styles.configValue}>
                      <Label variant={draftSyncEnabled ? 'success' : 'muted'}>
                        {draftSyncEnabled ? 'Yes' : 'No'}
                      </Label>
                    </span>
                  </div>
                  <div className={styles.configRow}>
                    <span className={styles.configLabel}>Organizations</span>
                    <span className={styles.configValue}>
                      <code>{draftOrgs.length ? draftOrgs.join(', ') : 'All (default)'}</code>
                    </span>
                  </div>
                  <div className={styles.configRow}>
                    <span className={styles.configLabel}>Schedule</span>
                    <span className={styles.configValue}>
                      <code>
                        {draftScheduleEnabled
                          ? `Every ${draftInterval}h — ${draftScope}`
                          : 'Disabled'}
                      </code>
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Navigation buttons */}
          <div className={styles.syncWizardNav}>
            {stepIndex > 0 && (
              <Button
                size="sm"
                onClick={() => setStep(SYNC_WIZARD_STEPS[stepIndex - 1].key)}
                disabled={isSaving}
              >
                Back
              </Button>
            )}
            <div style={{ flex: 1 }} />
            {stepIndex < SYNC_WIZARD_STEPS.length - 1 ? (
              <Button
                variant="primary"
                size="sm"
                onClick={() => setStep(SYNC_WIZARD_STEPS[stepIndex + 1].key)}
              >
                Next
              </Button>
            ) : (
              <Button
                variant="primary"
                size="sm"
                disabled={isSaving}
                onClick={() => void handleSaveConfig()}
              >
                {isSaving ? 'Saving…' : 'Save Configuration'}
              </Button>
            )}
          </div>
        </div>
      </Drawer>
    </>
  );
}

function GitHubPane() {
  return (
    <div className={styles.featuresPane}>
      <p className={styles.featuresDescription}>
        GitHub Enterprise connection and data sync settings.
      </p>
      <div className={styles.githubGrid}>
        <EnterprisePATWidget />
        <AuditStreamPanel />
        <GitHubSyncSetupPanel />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Integrations Pane                                                  */
/* ------------------------------------------------------------------ */

/* ------------------------------------------------------------------ */
/*  Integration Icons                                                  */
/* ------------------------------------------------------------------ */

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

function TeamsIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="4" y="5" width="16" height="14" rx="3" fill="#5b5fc7" />
      <path d="M9 10h6M9 14h4" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
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
    description: 'Send real-time notifications and alerts to Slack channels.',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
        <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zm1.271 0a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313z" />
      </svg>
    ),
    iconBg: '#4A154B',
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
    key: 'teams',
    label: 'Microsoft Teams',
    description: 'Send adaptive card notifications to Teams channels through incoming webhooks.',
    icon: <TeamsIcon />,
    iconBg: '#5b5fc7',
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

  const { data: pagerDutyConfig } = useQuery({
    queryKey: ['pagerduty-config'],
    queryFn: getPagerDutyConfig,
  });

  const { data: teamsConfig } = useQuery({
    queryKey: ['teams-config'],
    queryFn: getTeamsConfig,
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
        const configured = Boolean(pagerDutyConfig?.routing_key_configured);
        const enabled =
          configured && Object.values(pagerDutyConfig?.notification_settings ?? {}).some(Boolean);
        return { configured, enabled };
      }
      case 'teams': {
        const configured = Object.values(teamsConfig?.channel_webhook_configured ?? {}).some(
          Boolean,
        );
        const enabled =
          configured && Object.values(teamsConfig?.notification_settings ?? {}).some(Boolean);
        return { configured, enabled };
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
      <SlackIntegration />
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

      {/* Jira config modal */}
      <Drawer
        open={configTarget === 'jira'}
        onClose={() => setConfigTarget(null)}
        title="Configure Jira"
      >
        <JiraConfigForm onClose={() => setConfigTarget(null)} />
      </Drawer>

      {/* Webhook-based config modal (Sentinel, Splunk) */}
      <Drawer
        open={configTarget !== null && ['sentinel', 'splunk'].includes(configTarget)}
        onClose={() => setConfigTarget(null)}
        title={getConfigModalTitle(configTarget ?? '')}
      >
        {configTarget && ['sentinel', 'splunk'].includes(configTarget) && (
          <WebhookConfigForm
            name={INTEGRATION_INFO.find((i) => i.key === configTarget)?.label ?? configTarget}
            onClose={() => setConfigTarget(null)}
          />
        )}
      </Drawer>

      <Drawer
        open={configTarget === 'pagerduty'}
        onClose={() => setConfigTarget(null)}
        title="Configure PagerDuty"
      >
        <PagerDutyIntegration />
      </Drawer>

      <Drawer
        open={configTarget === 'teams'}
        onClose={() => setConfigTarget(null)}
        title="Configure Microsoft Teams"
      >
        <TeamsIntegration />
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

  const handleChange = useCallback(
    (key: string, value: string) => {
      setValues((prev) => ({ ...prev, [key]: value }));
      setSaveMessage(null);
      setSaveError(null);
    },
    [setSaveMessage, setSaveError],
  );

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
        Configure how long each data type is retained before automatic cleanup.
      </p>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Table</th>
              <th scope="col">Time Column</th>
              <th scope="col">Retention (days)</th>
              <th scope="col">Default</th>
              <th scope="col">Rows</th>
              <th scope="col">Size</th>
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
  const activeTab: Category | 'Features' | 'Integrations' | 'Retention' =
    SLUG_TO_TAB[tabSlug ?? 'secrets'] ?? 'Secrets';
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
      setEditTarget(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (key: string) => deleteSetting(key),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] });
      setDeleteTarget(null);
    },
  });

  const filteredSettings =
    settings?.filter(
      (s: AppSetting) =>
        activeTab === 'Secrets' && ['sensitive', 'critical'].includes(s.sensitivity.toLowerCase()),
    ) ?? [];

  return (
    <div className={styles.page}>
      <PageHeader
        title="Settings"
        description="Manage application settings, secrets, and integrations"
        showHelp
      />

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
          <>
            <CategorySettingsForm
              category="System"
              fields={SYSTEM_FIELDS}
              description="System-level configuration including logging, maintenance, and data retention."
              settings={settings ?? []}
            />
            <MaintenanceSettingsPanel />
          </>
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
                    <th scope="col">Name</th>
                    <th scope="col">Type</th>
                    <th scope="col">Last Rotated</th>
                    <th scope="col">Status</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSettings.map((s: AppSetting) => (
                    <tr key={s.key}>
                      <td className={styles.settingKey}>{s.key}</td>
                      <td className={styles.settingMeta}>{s.category}</td>
                      <td className={styles.settingMeta}>{formatAbsolute(s.updated_at)}</td>
                      <td>
                        <span className={sensitivityClass(s.sensitivity)}>{s.sensitivity}</span>
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

      {/* Edit drawer */}
      <Drawer
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
      </Drawer>

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
