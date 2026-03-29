import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { IntegrationsPage } from './index';

vi.mock('../../api/integrations', () => ({
  listTicketingConfigs: vi.fn().mockResolvedValue([]),
  listNotificationConfigs: vi.fn().mockResolvedValue([]),
  createNotificationConfig: vi.fn().mockResolvedValue({ id: 1, channel_type: 'slack', display_name: 'Slack', target: 'https://hooks.slack.com/services/test', notify_severities: ['critical', 'high'], cooldown_seconds: 3600, enabled: true, created_by: 'admin', created_at: '2025-01-01T00:00:00Z' }),
  createTicketingConfig: vi.fn().mockResolvedValue({ id: 1, provider: 'jira', display_name: 'Jira', target: 'https://test.atlassian.net', project_key: 'SEC', default_issue_type: 'Bug', auto_create: false, auto_create_severities: ['critical', 'high'], enabled: true, created_by: 'admin', created_at: '2025-01-01T00:00:00Z' }),
}));

const mockUpdateSyncConfig = vi.fn().mockResolvedValue({
  app_id: null,
  enterprise_slug: null,
  installation_ids: [],
  sync_enabled: true,
  interval_days: 75,
  orgs: [],
});

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
    installation_ids: [{ org: 'acme', installation_id: 999 }],
    sync_enabled: false,
    interval_days: 60,
    orgs: ['acme'],
  }),
  updateSyncConfig: (...args: unknown[]) => mockUpdateSyncConfig(...args),
  listSyncRuns: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10, has_next: false }),
  getSyncRun: vi.fn().mockResolvedValue(null),
  getSyncSchedule: vi.fn().mockResolvedValue({
    enabled: false,
    interval_hours: 24,
    scope: 'full',
    next_run_at: null,
    last_completed_at: null,
  }),
  updateSyncSchedule: vi.fn().mockResolvedValue({
    enabled: false,
    interval_hours: 24,
    scope: 'full',
    next_run_at: null,
    last_completed_at: null,
  }),
}));

vi.mock('../../api/ingest', () => ({
  uploadFile: vi.fn().mockResolvedValue(null),
  getIngestJob: vi.fn().mockResolvedValue(null),
  listIngestJobs: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}));

describe('IntegrationsPage', () => {
  beforeEach(() => {
    mockUpdateSyncConfig.mockClear();
  });

  /* ---------------------------------------------------------------- */
  /*  Page structure                                                    */
  /* ---------------------------------------------------------------- */

  it('renders the page title and subtitle', () => {
    renderWithProviders(<IntegrationsPage />);

    expect(screen.getByRole('heading', { level: 1, name: /integrations/i })).toBeInTheDocument();
    expect(screen.getByText(/connect external services, import data/i)).toBeInTheDocument();
  });

  it('renders the Marketplace section heading', () => {
    renderWithProviders(<IntegrationsPage />);

    expect(screen.getByRole('heading', { level: 2, name: /marketplace/i })).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Marketplace cards                                                 */
  /* ---------------------------------------------------------------- */

  it('renders all 6 marketplace integration cards', () => {
    renderWithProviders(<IntegrationsPage />);

    expect(screen.getByText('GitHub Enterprise')).toBeInTheDocument();
    expect(screen.getByText('Slack')).toBeInTheDocument();
    expect(screen.getByText('Microsoft Sentinel')).toBeInTheDocument();
    expect(screen.getByText('Splunk')).toBeInTheDocument();
    expect(screen.getByText('PagerDuty')).toBeInTheDocument();
    expect(screen.getByText('Jira')).toBeInTheDocument();
  });

  it('shows Connected status for GitHub Enterprise when app_id is set', async () => {
    renderWithProviders(<IntegrationsPage />);

    const ghCard = screen.getByTestId('mkt-card-github-enterprise');
    await waitFor(() => {
      expect(within(ghCard).getByText('Connected')).toBeInTheDocument();
    });
    expect(within(ghCard).getByRole('button', { name: /configure/i })).toBeInTheDocument();
  });

  it('renders card descriptions for all integrations', () => {
    renderWithProviders(<IntegrationsPage />);

    expect(screen.getByText(/connect your github enterprise instance/i)).toBeInTheDocument();
    expect(screen.getByText(/send real-time alerts and weekly digest/i)).toBeInTheDocument();
    expect(screen.getByText(/forward normalized security events/i)).toBeInTheDocument();
    expect(screen.getByText(/stream audit events and copilot metrics to splunk/i)).toBeInTheDocument();
    expect(screen.getByText(/trigger pagerduty incidents/i)).toBeInTheDocument();
    expect(screen.getByText(/automatically create jira issues/i)).toBeInTheDocument();
  });

  it('shows Configure buttons for all integrations', () => {
    renderWithProviders(<IntegrationsPage />);

    const slackCard = screen.getByTestId('mkt-card-slack');
    expect(within(slackCard).getByRole('button', { name: /configure/i })).toBeEnabled();

    const sentinelCard = screen.getByTestId('mkt-card-microsoft-sentinel');
    expect(within(sentinelCard).getByRole('button', { name: /configure/i })).toBeEnabled();

    const splunkCard = screen.getByTestId('mkt-card-splunk');
    expect(within(splunkCard).getByRole('button', { name: /configure/i })).toBeEnabled();

    const pdCard = screen.getByTestId('mkt-card-pagerduty');
    expect(within(pdCard).getByRole('button', { name: /configure/i })).toBeEnabled();

    const jiraCard = screen.getByTestId('mkt-card-jira');
    expect(within(jiraCard).getByRole('button', { name: /configure/i })).toBeEnabled();
  });

  it('shows Not installed status for unimplemented integrations', () => {
    renderWithProviders(<IntegrationsPage />);

    const sentinelCard = screen.getByTestId('mkt-card-microsoft-sentinel');
    expect(within(sentinelCard).getByText('Not installed')).toBeInTheDocument();

    const splunkCard = screen.getByTestId('mkt-card-splunk');
    expect(within(splunkCard).getByText('Not installed')).toBeInTheDocument();

    const jiraCard = screen.getByTestId('mkt-card-jira');
    expect(within(jiraCard).getByText('Not installed')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  GitHub Enterprise config form                                     */
  /* ---------------------------------------------------------------- */

  it('opens config form when Configure is clicked on GitHub Enterprise', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IntegrationsPage />);

    const ghCard = screen.getByTestId('mkt-card-github-enterprise');
    const configureBtn = within(ghCard).getByRole('button', { name: /configure/i });
    await user.click(configureBtn);

    await waitFor(() => {
      expect(screen.getByText('Configure GitHub Enterprise')).toBeInTheDocument();
    });
  });

  it('renders config form with data from getSyncConfig', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IntegrationsPage />);

    const ghCard = screen.getByTestId('mkt-card-github-enterprise');
    await user.click(within(ghCard).getByRole('button', { name: /configure/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/enable scheduled sync/i)).toBeInTheDocument();
    });

    const enabledCheckbox = screen.getByLabelText(/enable scheduled sync/i) as HTMLInputElement;
    expect(enabledCheckbox.checked).toBe(false);

    const intervalInput = screen.getByLabelText(/sync interval/i) as HTMLInputElement;
    expect(intervalInput.value).toBe('60');

    const orgsInput = screen.getByLabelText(/organizations to sync/i) as HTMLInputElement;
    expect(orgsInput.value).toBe('acme');

    expect(screen.getByText('12345')).toBeInTheDocument();
    expect(screen.getByText('my-corp')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('Save button calls updateSyncConfig with form values', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IntegrationsPage />);

    const ghCard = screen.getByTestId('mkt-card-github-enterprise');
    await user.click(within(ghCard).getByRole('button', { name: /configure/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/enable scheduled sync/i)).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText(/enable scheduled sync/i));

    const intervalInput = screen.getByLabelText(/sync interval/i);
    await user.clear(intervalInput);
    await user.type(intervalInput, '75');

    await user.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => {
      expect(mockUpdateSyncConfig).toHaveBeenCalledWith({
        sync_enabled: true,
        interval_days: 75,
        orgs: ['acme'],
      });
    });
  });

  it('shows success message after saving', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IntegrationsPage />);

    const ghCard = screen.getByTestId('mkt-card-github-enterprise');
    await user.click(within(ghCard).getByRole('button', { name: /configure/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/enable scheduled sync/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => {
      expect(screen.getByText(/configuration saved successfully/i)).toBeInTheDocument();
    });
  });

  it('Cancel closes modal and resets form', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IntegrationsPage />);

    const ghCard = screen.getByTestId('mkt-card-github-enterprise');
    await user.click(within(ghCard).getByRole('button', { name: /configure/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/enable scheduled sync/i)).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText(/enable scheduled sync/i));

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(screen.queryByText('Configure GitHub Enterprise')).not.toBeInTheDocument();
  });

  it('shows validation error for invalid interval_days', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IntegrationsPage />);

    const ghCard = screen.getByTestId('mkt-card-github-enterprise');
    await user.click(within(ghCard).getByRole('button', { name: /configure/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/sync interval/i)).toBeInTheDocument();
    });

    const intervalInput = screen.getByLabelText(/sync interval/i);
    await user.clear(intervalInput);
    await user.type(intervalInput, '30');

    expect(screen.getByText(/must be between 60 and 90 days/i)).toBeInTheDocument();

    const saveBtn = screen.getByRole('button', { name: /^save$/i });
    expect(saveBtn).toBeDisabled();
  });

  it('shows read-only info about credentials in config form', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IntegrationsPage />);

    const ghCard = screen.getByTestId('mkt-card-github-enterprise');
    await user.click(within(ghCard).getByRole('button', { name: /configure/i }));

    await waitFor(() => {
      expect(screen.getByText(/github app credentials are configured via environment variables/i)).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Clickable features                                                */
  /* ---------------------------------------------------------------- */

  it('all integration status badges are clickable', () => {
    const { container } = renderWithProviders(<IntegrationsPage />);
    const clickableStatuses = container.querySelectorAll('.clickableStatus');
    // All 6 integration cards have clickable status
    expect(clickableStatuses.length).toBe(6);
    clickableStatuses.forEach((el) => {
      expect(el.getAttribute('tabindex')).toBe('0');
    });
  });
});
