import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';
import { ToastProvider } from '../../components/common/ToastProvider';
import { SettingsPage } from './index';

const mockListSettings = vi.fn().mockResolvedValue([
  {
    key: 'github.client_id',
    value: 'Ov23li****',
    category: 'GitHub',
    sensitivity: 'sensitive',
    description: 'GitHub OAuth Client ID',
    updated_by: 'admin',
    updated_at: '2025-06-01T10:00:00Z',
  },
  {
    key: 'github.app_id',
    value: '12345',
    category: 'GitHub',
    sensitivity: 'normal',
    description: 'GitHub App ID',
    updated_by: 'admin',
    updated_at: '2025-06-01T10:00:00Z',
  },
  {
    key: 'tls.cert_path',
    value: '/etc/certs/server.crt',
    category: 'Security',
    sensitivity: 'normal',
    description: 'TLS certificate path',
    updated_by: 'system',
    updated_at: '2025-06-01T09:00:00Z',
  },
  {
    key: 'notifications.slack_webhook',
    value: 'https://hooks.****',
    category: 'Notifications',
    sensitivity: 'sensitive',
    description: 'Slack webhook URL',
    updated_by: 'admin',
    updated_at: '2025-06-02T12:00:00Z',
  },
  {
    key: 'db.connection_string',
    value: 'postgres://****',
    category: 'System',
    sensitivity: 'critical',
    description: 'Primary database connection string',
    updated_by: 'system',
    updated_at: '2025-06-03T08:00:00Z',
  },
  {
    key: 'system.log_level',
    value: 'info',
    category: 'System',
    sensitivity: 'normal',
    description: 'Application log level',
    updated_by: 'admin',
    updated_at: '2025-06-01T10:00:00Z',
  },
]);

const mockUpdateSetting = vi.fn().mockResolvedValue({
  key: 'system.log_level',
  value: 'debug',
  category: 'System',
  sensitivity: 'normal',
  description: 'Application log level',
  updated_by: 'admin',
  updated_at: '2025-06-03T10:00:00Z',
});

const mockDeleteSetting = vi.fn().mockResolvedValue(undefined);
const mockGetMaintenanceStatus = vi.fn().mockResolvedValue({
  enabled: false,
  message: 'Scheduled maintenance',
  severity: 'warning',
  block_writes: false,
  started_at: null,
  estimated_end: null,
});
const mockUpdateMaintenanceStatus = vi.fn().mockResolvedValue({
  enabled: true,
  message: 'Scheduled maintenance',
  severity: 'warning',
  block_writes: true,
  started_at: '2025-06-03T10:00:00Z',
  estimated_end: null,
});
const mockToggleMaintenanceMode = vi.fn().mockResolvedValue({
  enabled: true,
  message: 'Scheduled maintenance',
  severity: 'warning',
  block_writes: false,
  started_at: '2025-06-03T10:00:00Z',
  estimated_end: null,
});

vi.mock('../../api/setup', () => ({
  listSettings: (...args: unknown[]) => mockListSettings(...args),
  updateSetting: (...args: unknown[]) => mockUpdateSetting(...args),
  deleteSetting: (...args: unknown[]) => mockDeleteSetting(...args),
  getSetupStatus: vi.fn().mockResolvedValue({ setup_required: false }),
  setupLogin: vi.fn().mockResolvedValue(undefined),
  setupGitHubOAuth: vi.fn().mockResolvedValue(undefined),
  setupGitHubApp: vi.fn().mockResolvedValue(undefined),
  setupTLS: vi.fn().mockResolvedValue(undefined),
  completeSetup: vi.fn().mockResolvedValue(undefined),
  getSetupCurrentConfig: vi.fn().mockResolvedValue({}),
  getEnterprisePATStatus: vi.fn().mockResolvedValue({ configured: false, masked: null }),
  saveEnterprisePAT: vi.fn().mockResolvedValue({ status: 'ok', masked: 'ghp_****...wxyz' }),
  deleteEnterprisePAT: vi
    .fn()
    .mockResolvedValue({ status: 'ok', message: 'Enterprise PAT removed' }),
  testEnterprisePAT: vi
    .fn()
    .mockResolvedValue({ status: 'ok', login: 'admin-bot', scopes: 'admin:enterprise' }),
}));

vi.mock('../../api/integrations', () => ({
  listTicketingConfigs: vi.fn().mockResolvedValue([]),
  listNotificationConfigs: vi.fn().mockResolvedValue([]),
  listSiemConfigs: vi.fn().mockResolvedValue([]),
  createNotificationConfig: vi.fn().mockResolvedValue({}),
  createTicketingConfig: vi.fn().mockResolvedValue({}),
  createSiemConfig: vi.fn().mockResolvedValue({}),
}));

vi.mock('../../api/maintenance', () => ({
  getMaintenanceStatus: (...args: unknown[]) => mockGetMaintenanceStatus(...args),
  updateMaintenanceStatus: (...args: unknown[]) => mockUpdateMaintenanceStatus(...args),
  toggleMaintenanceMode: (...args: unknown[]) => mockToggleMaintenanceMode(...args),
}));

vi.mock('../../api/slack', () => ({
  getSlackConfig: vi.fn().mockResolvedValue({
    bot_token_configured: false,
    signing_secret_configured: false,
    bot_token_masked: null,
    signing_secret_masked: null,
    default_channel: '',
    channel_mappings: {
      detections: '',
      sync_errors: '',
      system_health: '',
      threat_intel: '',
    },
    notification_settings: {
      detections: true,
      sync_errors: true,
      system_health: true,
      threat_intel: false,
    },
    installation_url: 'https://api.slack.com/apps',
    installation_instructions: ['Create a Slack app'],
    commands: ['/octowatch status'],
  }),
  updateSlackConfig: vi.fn().mockResolvedValue({}),
  testSlackConnection: vi.fn().mockResolvedValue({
    ok: true,
    channel: '#security-alerts',
    message: 'Test message sent successfully',
  }),
}));

vi.mock('../../api/pagerduty', () => ({
  getPagerDutyConfig: vi.fn().mockResolvedValue({
    routing_key_configured: true,
    routing_key_masked: 'abcd********wxyz',
    severity_mapping: {
      critical: 'critical',
      high: 'error',
      medium: 'warning',
      low: 'info',
      info: 'info',
    },
    notification_settings: {
      detections: true,
      sync_errors: true,
      system_health: false,
      threat_intel: false,
    },
    auto_resolve: true,
  }),
}));

vi.mock('../../api/teams', () => ({
  getTeamsConfig: vi.fn().mockResolvedValue({
    channel_webhook_configured: {
      default: true,
      detections: true,
      sync_errors: false,
      system_health: false,
      threat_intel: false,
    },
    channel_webhooks_masked: {
      default: 'https://o*******1234',
      detections: 'https://d*******5678',
      sync_errors: null,
      system_health: null,
      threat_intel: null,
    },
    source_mappings: {
      detections: 'detections',
      sync_errors: 'default',
      system_health: 'default',
      threat_intel: 'default',
    },
    notification_settings: {
      detections: true,
      sync_errors: true,
      system_health: false,
      threat_intel: false,
    },
  }),
}));

vi.mock('../../api/sync', () => ({
  getSyncStatus: vi.fn().mockResolvedValue({
    id: 'run-1',
    status: 'completed',
    trigger_type: 'manual',
    triggered_by: 'admin',
    scope: 'full',
    started_at: '2025-06-01T08:00:00Z',
    completed_at: '2025-06-01T08:15:00Z',
    error_message: null,
    entity_counts: {},
    cursors: [],
  }),
  triggerSync: vi.fn().mockResolvedValue({ run_id: 'r', status: 'pending' }),
  cancelSyncRun: vi.fn().mockResolvedValue(undefined),
  getSyncConfig: vi.fn().mockResolvedValue({
    app_id: 12345,
    enterprise_slug: 'my-corp',
    installation_ids: [],
    sync_enabled: false,
    interval_days: 60,
    orgs: [],
  }),
  updateSyncConfig: vi.fn().mockResolvedValue({}),
  listSyncRuns: vi
    .fn()
    .mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10, has_next: false }),
  getSyncRun: vi.fn().mockResolvedValue(null),
  getSyncSchedule: vi.fn().mockResolvedValue({
    enabled: false,
    interval_hours: 24,
    scope: 'full',
    next_run_at: null,
    last_completed_at: null,
  }),
  updateSyncSchedule: vi.fn().mockResolvedValue({}),
  getSyncLogs: vi.fn().mockResolvedValue([]),
  getAuditLogEnrichment: vi.fn().mockResolvedValue({
    enabled: false,
    interval_minutes: 60,
    last_run_at: null,
  }),
  updateAuditLogEnrichment: vi.fn().mockResolvedValue({
    enabled: false,
    interval_minutes: 60,
    last_run_at: null,
  }),
}));

vi.mock('../../api/ingest', () => ({
  uploadFile: vi.fn().mockResolvedValue(null),
  getIngestJob: vi.fn().mockResolvedValue(null),
  listIngestJobs: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}));

function renderPage(initialTab = 'secrets') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={[`/settings/${initialTab}`]}>
          <Routes>
            <Route path="/settings/:tab" element={<SettingsPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe('SettingsPage', () => {
  beforeEach(() => {
    mockListSettings.mockClear();
    mockUpdateSetting.mockClear();
    mockDeleteSetting.mockClear();
    mockGetMaintenanceStatus.mockClear();
    mockUpdateMaintenanceStatus.mockClear();
    mockToggleMaintenanceMode.mockClear();
  });

  /* ---------------------------------------------------------------- */
  /*  Page structure                                                    */
  /* ---------------------------------------------------------------- */

  it('renders page title and subtitle', () => {
    renderPage();

    expect(screen.getByRole('heading', { level: 1, name: /settings/i })).toBeInTheDocument();
    expect(screen.getByText(/manage application settings/i)).toBeInTheDocument();
  });

  it('renders category tabs', () => {
    renderPage();

    expect(screen.getByRole('button', { name: 'Secrets' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'GitHub' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Security' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'System' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Audit Trail' })).not.toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Settings list                                                     */
  /* ---------------------------------------------------------------- */

  it('renders secrets in the Secrets tab', async () => {
    renderPage();

    expect(await screen.findByText('github.client_id')).toBeInTheDocument();
    expect(screen.getByText('notifications.slack_webhook')).toBeInTheDocument();
    expect(screen.getByText('db.connection_string')).toBeInTheDocument();
    expect(screen.queryByText('github.app_id')).not.toBeInTheDocument();
    expect(screen.queryByText('tls.cert_path')).not.toBeInTheDocument();
    expect(screen.queryByText('system.log_level')).not.toBeInTheDocument();
  });

  it('shows secret metadata columns', async () => {
    renderPage();

    await screen.findByText('github.client_id');

    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Type' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Last Rotated' })).toBeInTheDocument();
    expect(screen.getAllByText('GitHub').length).toBeGreaterThan(1);
  });

  it('shows sensitivity badges', async () => {
    renderPage();

    await screen.findByText('github.client_id');

    expect(screen.getAllByText('sensitive')).toHaveLength(2);
    expect(screen.getByText('critical')).toBeInTheDocument();
    expect(screen.queryByText('normal')).not.toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Category filtering                                                */
  /* ---------------------------------------------------------------- */

  it('filters settings by category when tab is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('github.client_id');
    expect(screen.queryByText('system.log_level')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'GitHub' }));

    expect(screen.getByText('Classic PAT for Audit Log')).toBeInTheDocument();
    expect(screen.queryByText('db.connection_string')).not.toBeInTheDocument();
    expect(screen.queryByText('system.log_level')).not.toBeInTheDocument();
  });

  it('shows category form controls when category tab is clicked', async () => {
    mockListSettings.mockResolvedValueOnce([]);
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(mockListSettings).toHaveBeenCalled();
    });

    await user.click(screen.getByRole('button', { name: 'Security' }));

    // Should show the form with real settings controls
    expect(screen.getByText(/session timeout/i)).toBeInTheDocument();
    expect(screen.getByText(/require mfa/i)).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Edit setting                                                      */
  /* ---------------------------------------------------------------- */

  it('opens edit drawer when Edit is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('github.client_id');

    const rows = screen.getAllByRole('row');
    const secretRow = rows.find((r) => within(r).queryByText('github.client_id'));
    expect(secretRow).toBeDefined();

    const editBtn = within(secretRow!).getByRole('button', { name: /edit/i });
    await user.click(editBtn);

    await waitFor(() => {
      expect(screen.getByText(/edit: github\.client_id/i)).toBeInTheDocument();
    });
  });

  it('calls updateSetting when form is submitted', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('github.client_id');

    const rows = screen.getAllByRole('row');
    const secretRow = rows.find((r) => within(r).queryByText('github.client_id'));
    const editBtn = within(secretRow!).getByRole('button', { name: /edit/i });
    await user.click(editBtn);

    const newValueInput = await screen.findByPlaceholderText('Enter new value');

    await user.click(newValueInput);
    await user.type(newValueInput, 'new-secret');
    expect(newValueInput).toHaveValue('new-secret');

    await user.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => {
      expect(mockUpdateSetting).toHaveBeenCalledWith(
        'github.client_id',
        'new-secret',
        'GitHub OAuth Client ID',
      );
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Delete (reset) setting                                            */
  /* ---------------------------------------------------------------- */

  it('opens confirm dialog when Reset is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('github.client_id');

    const rows = screen.getAllByRole('row');
    const secretRow = rows.find((r) => within(r).queryByText('github.client_id'));
    const resetBtn = within(secretRow!).getByRole('button', { name: /reset/i });
    await user.click(resetBtn);

    await waitFor(() => {
      expect(screen.getByText(/reset "github\.client_id" to its default/i)).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Category settings forms                                          */
  /* ---------------------------------------------------------------- */

  it('shows Security settings form with real controls', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(mockListSettings).toHaveBeenCalled();
    });

    await user.click(screen.getByRole('button', { name: 'Security' }));

    expect(screen.getByText(/authentication, session management/i)).toBeInTheDocument();
    expect(screen.getByText(/session timeout/i)).toBeInTheDocument();
    expect(screen.getByText(/require mfa/i)).toBeInTheDocument();
    expect(screen.getByText(/enable ip allowlist/i)).toBeInTheDocument();
    expect(screen.getByText(/max failed login attempts/i)).toBeInTheDocument();
  });

  it('shows Notifications settings form with real controls', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(mockListSettings).toHaveBeenCalled();
    });

    await user.click(screen.getByRole('button', { name: 'Notifications' }));

    expect(screen.getByText(/notification channel configuration/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email notifications/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/slack webhook url/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/alert threshold/i)).toBeInTheDocument();
  });

  it('shows System settings form with real controls', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(mockListSettings).toHaveBeenCalled();
    });

    await user.click(screen.getByRole('button', { name: 'System' }));

    expect(
      screen.getByText(
        /system-level configuration including logging, maintenance, and data retention/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/log level/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/debug mode/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^maintenance mode$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/banner message/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/data retention/i)).toBeInTheDocument();
  });

  it('pre-populates category form with existing setting values', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(mockListSettings).toHaveBeenCalled();
    });

    await user.click(screen.getByRole('button', { name: 'System' }));

    // system.log_level exists in mock data with value 'info'
    const logLevelSelect = screen.getByLabelText(/log level/i) as HTMLSelectElement;
    expect(logLevelSelect.value).toBe('info');
  });

  it('shows Save changes button disabled when no changes', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(mockListSettings).toHaveBeenCalled();
    });

    await user.click(screen.getByRole('button', { name: 'Security' }));

    const saveBtn = screen.getByRole('button', { name: /save changes/i });
    expect(saveBtn).toBeDisabled();
  });

  /* ---------------------------------------------------------------- */
  /*  Integrations tab                                                 */
  /* ---------------------------------------------------------------- */

  it('renders Integrations tab button', () => {
    renderPage();
    expect(screen.getByRole('button', { name: 'Integrations' })).toBeInTheDocument();
  });

  it('shows integrations pane when Integrations tab is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: 'Integrations' }));

    await waitFor(() => {
      expect(screen.getByText(/connect external services/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/slack integration/i)).toBeInTheDocument();
    expect(screen.getByText('Slack')).toBeInTheDocument();
    expect(screen.getByText('Microsoft Teams')).toBeInTheDocument();
    expect(screen.getByText('Microsoft Sentinel')).toBeInTheDocument();
    expect(screen.getByText('Splunk')).toBeInTheDocument();
    expect(screen.getByText('PagerDuty')).toBeInTheDocument();
    expect(screen.getByText('Microsoft Teams')).toBeInTheDocument();
  });

  it('renders Integrations tab via direct URL', async () => {
    renderPage('integrations');

    await waitFor(() => {
      expect(screen.getByText(/connect external services/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/slack integration/i)).toBeInTheDocument();
  });

  it('shows GitHub grid widgets on the GitHub tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: 'GitHub' }));

    await waitFor(() => {
      expect(screen.getByText('GitHub Enterprise Sync')).toBeInTheDocument();
    });

    expect(screen.getByText('Classic PAT for Audit Log')).toBeInTheDocument();
    expect(screen.getByText('Audit Log Streaming')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  GitHub Sync Setup Panel                                          */
  /* ---------------------------------------------------------------- */

  it('shows sync summary with connection and schedule info', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: 'GitHub' }));

    await waitFor(() => {
      expect(screen.getByTestId('sync-setup-summary')).toBeInTheDocument();
    });

    expect(screen.getByText(/Enterprise: my-corp/)).toBeInTheDocument();
    expect(screen.getByText('Configure Sync')).toBeInTheDocument();
    expect(screen.getByText('Trigger Sync Now')).toBeInTheDocument();
  });

  it('opens sync wizard drawer when Configure Sync is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: 'GitHub' }));

    await waitFor(() => {
      expect(screen.getByText('Configure Sync')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Configure Sync'));

    await waitFor(() => {
      expect(screen.getByTestId('sync-wizard')).toBeInTheDocument();
    });

    expect(screen.getByTestId('wizard-step-connection')).toBeInTheDocument();
    expect(screen.getByText('Connection Details')).toBeInTheDocument();
  });

  it('navigates through wizard steps with Next/Back', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: 'GitHub' }));

    await waitFor(() => {
      expect(screen.getByText('Configure Sync')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Configure Sync'));

    await waitFor(() => {
      expect(screen.getByTestId('wizard-step-connection')).toBeInTheDocument();
    });

    // Go to step 2 (Entities)
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByTestId('wizard-step-entities')).toBeInTheDocument();
    expect(screen.getByText('Entity Selection')).toBeInTheDocument();

    // Go to step 3 (Schedule)
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByTestId('wizard-step-schedule')).toBeInTheDocument();
    expect(screen.getByText('Sync Schedule')).toBeInTheDocument();

    // Go to step 4 (Confirm)
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByTestId('wizard-step-confirm')).toBeInTheDocument();
    expect(screen.getByText('Review & Confirm')).toBeInTheDocument();

    // Go back
    await user.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.getByTestId('wizard-step-schedule')).toBeInTheDocument();
  });

  it('allows adding and removing orgs in entity step', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: 'GitHub' }));

    await waitFor(() => {
      expect(screen.getByText('Configure Sync')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Configure Sync'));

    await waitFor(() => {
      expect(screen.getByTestId('wizard-step-connection')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByTestId('wizard-step-entities')).toBeInTheDocument();

    // Add an org using fireEvent (portal inputs can have focus issues with userEvent)
    const orgInput = screen.getByPlaceholderText('Enter org slug and press Enter');
    fireEvent.change(orgInput, { target: { value: 'acme-corp' } });
    fireEvent.keyDown(orgInput, { key: 'Enter', code: 'Enter' });

    // Wait for the tag to appear
    await waitFor(() => {
      expect(screen.getByLabelText('Remove acme-corp')).toBeInTheDocument();
    });

    // Remove it
    await user.click(screen.getByRole('button', { name: 'Remove acme-corp' }));
    expect(screen.queryByRole('button', { name: 'Remove acme-corp' })).not.toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Enterprise PAT section                                           */
  /* ---------------------------------------------------------------- */

  it('shows Classic PAT section on GitHub tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: 'GitHub' }));

    await waitFor(() => {
      expect(screen.getByText('Classic PAT for Audit Log')).toBeInTheDocument();
    });

    expect(screen.getByText(/requires a classic Personal Access Token/)).toBeInTheDocument();
  });

  it('shows PAT input field on GitHub tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: 'GitHub' }));

    await waitFor(() => {
      expect(screen.getByTestId('enterprise-pat-section')).toBeInTheDocument();
    });

    const input = screen.getByLabelText('Classic Personal Access Token');
    expect(input).toBeInTheDocument();
  });

  it('shows Not configured status when no PAT is set', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: 'GitHub' }));

    await waitFor(() => {
      expect(screen.getByText('Not configured')).toBeInTheDocument();
    });
  });

  it('shows Save button disabled when input is empty', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: 'GitHub' }));

    await waitFor(() => {
      expect(screen.getByTestId('enterprise-pat-section')).toBeInTheDocument();
    });

    const saveBtn = screen.getByRole('button', { name: 'Save' });
    expect(saveBtn).toBeDisabled();
  });

  it('enables Save button when token is entered', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: 'GitHub' }));

    await waitFor(() => {
      expect(screen.getByTestId('enterprise-pat-section')).toBeInTheDocument();
    });

    const input = screen.getByLabelText('Classic Personal Access Token');
    await user.type(input, 'ghp_testtoken123');

    const saveBtn = screen.getByRole('button', { name: 'Save' });
    expect(saveBtn).toBeEnabled();
  });
});
