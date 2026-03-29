import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
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
    key: 'db.connection_string',
    value: '****',
    category: 'Storage',
    sensitivity: 'critical',
    description: 'Database connection string',
    updated_by: 'admin',
    updated_at: '2025-05-30T08:00:00Z',
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

const mockGetAuditTrail = vi.fn().mockResolvedValue([
  {
    setting_key: 'system.log_level',
    action: 'update',
    changed_by: 'admin',
    old_value_masked: 'info',
    new_value_masked: 'debug',
    created_at: '2025-06-03T10:00:00Z',
  },
  {
    setting_key: 'github.client_id',
    action: 'set',
    changed_by: 'admin',
    old_value_masked: null,
    new_value_masked: 'Ov23li****',
    created_at: '2025-06-01T10:00:00Z',
  },
]);

vi.mock('../../api/setup', () => ({
  listSettings: (...args: unknown[]) => mockListSettings(...args),
  updateSetting: (...args: unknown[]) => mockUpdateSetting(...args),
  deleteSetting: (...args: unknown[]) => mockDeleteSetting(...args),
  getSettingsAuditTrail: (...args: unknown[]) => mockGetAuditTrail(...args),
  getSetupStatus: vi.fn().mockResolvedValue({ setup_required: false }),
  setupLogin: vi.fn().mockResolvedValue(undefined),
  setupGitHubOAuth: vi.fn().mockResolvedValue(undefined),
  setupGitHubApp: vi.fn().mockResolvedValue(undefined),
  setupTLS: vi.fn().mockResolvedValue(undefined),
  completeSetup: vi.fn().mockResolvedValue(undefined),
  getSetupCurrentConfig: vi.fn().mockResolvedValue({}),
}));

function renderPage(initialTab = 'all') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/settings/${initialTab}`]}>
        <Routes>
          <Route path="/settings/:tab" element={<SettingsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SettingsPage', () => {
  beforeEach(() => {
    mockListSettings.mockClear();
    mockUpdateSetting.mockClear();
    mockDeleteSetting.mockClear();
    mockGetAuditTrail.mockClear();
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

    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'GitHub' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Security' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Storage' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'System' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Audit Trail' })).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Settings list                                                     */
  /* ---------------------------------------------------------------- */

  it('renders all settings in the All tab', async () => {
    renderPage();

    expect(await screen.findByText('github.client_id')).toBeInTheDocument();
    expect(screen.getByText('github.app_id')).toBeInTheDocument();
    expect(screen.getByText('tls.cert_path')).toBeInTheDocument();
    expect(screen.getByText('db.connection_string')).toBeInTheDocument();
    expect(screen.getByText('notifications.slack_webhook')).toBeInTheDocument();
    expect(screen.getByText('system.log_level')).toBeInTheDocument();
  });

  it('shows masked values for settings', async () => {
    renderPage();

    expect(await screen.findByText('Ov23li****')).toBeInTheDocument();
    expect(screen.getByText('****')).toBeInTheDocument();
  });

  it('shows sensitivity badges', async () => {
    renderPage();

    await screen.findByText('github.client_id');

    expect(screen.getByText('critical')).toBeInTheDocument();
    expect(screen.getAllByText('sensitive')).toHaveLength(2);
    expect(screen.getAllByText('normal')).toHaveLength(3);
  });

  /* ---------------------------------------------------------------- */
  /*  Category filtering                                                */
  /* ---------------------------------------------------------------- */

  it('filters settings by category when tab is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('github.client_id');

    // Click GitHub tab
    await user.click(screen.getByRole('button', { name: 'GitHub' }));

    // GitHub settings should be visible
    expect(screen.getByText('github.client_id')).toBeInTheDocument();
    expect(screen.getByText('github.app_id')).toBeInTheDocument();

    // Non-GitHub settings should not be visible
    expect(screen.queryByText('tls.cert_path')).not.toBeInTheDocument();
    expect(screen.queryByText('db.connection_string')).not.toBeInTheDocument();
    expect(screen.queryByText('system.log_level')).not.toBeInTheDocument();
  });

  it('shows empty state when category has no settings', async () => {
    mockListSettings.mockResolvedValueOnce([]);
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(mockListSettings).toHaveBeenCalled();
    });

    await user.click(screen.getByRole('button', { name: 'GitHub' }));

    expect(screen.getByText(/no settings in the github category/i)).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Edit setting                                                      */
  /* ---------------------------------------------------------------- */

  it('opens edit modal when Edit is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('system.log_level');

    // Find the row with system.log_level and click its Edit button
    const rows = screen.getAllByRole('row');
    const logLevelRow = rows.find((r) => within(r).queryByText('system.log_level'));
    expect(logLevelRow).toBeDefined();

    const editBtn = within(logLevelRow!).getByRole('button', { name: /edit/i });
    await user.click(editBtn);

    await waitFor(() => {
      expect(screen.getByText(/edit: system\.log_level/i)).toBeInTheDocument();
    });
  });

  it('calls updateSetting when form is submitted', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('system.log_level');

    const rows = screen.getAllByRole('row');
    const logLevelRow = rows.find((r) => within(r).queryByText('system.log_level'));
    const editBtn = within(logLevelRow!).getByRole('button', { name: /edit/i });
    await user.click(editBtn);

    await waitFor(() => {
      expect(screen.getByLabelText(/new value/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/new value/i), 'debug');
    await user.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => {
      expect(mockUpdateSetting).toHaveBeenCalledWith('system.log_level', 'debug', 'Application log level');
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Delete (reset) setting                                            */
  /* ---------------------------------------------------------------- */

  it('opens confirm dialog when Reset is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('system.log_level');

    const rows = screen.getAllByRole('row');
    const logLevelRow = rows.find((r) => within(r).queryByText('system.log_level'));
    const resetBtn = within(logLevelRow!).getByRole('button', { name: /reset/i });
    await user.click(resetBtn);

    await waitFor(() => {
      expect(screen.getByText(/reset "system\.log_level" to its default/i)).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Audit trail                                                       */
  /* ---------------------------------------------------------------- */

  it('renders audit trail when Audit Trail tab is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('github.client_id');

    await user.click(screen.getByRole('button', { name: 'Audit Trail' }));

    // Should show the audit entries
    await waitFor(() => {
      expect(screen.getByText('update')).toBeInTheDocument();
    });

    expect(screen.getByText('set')).toBeInTheDocument();
  });
});
