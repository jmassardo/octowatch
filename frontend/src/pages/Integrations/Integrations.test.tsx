import { describe, it, expect, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { IntegrationsPage } from './index';

vi.mock('../../api/integrations', () => ({
  listTicketingConfigs: vi.fn().mockResolvedValue([]),
  listNotificationConfigs: vi.fn().mockResolvedValue([]),
}));

describe('IntegrationsPage', () => {
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

  it('renders the Data Import section heading and description', () => {
    renderWithProviders(<IntegrationsPage />);

    expect(screen.getByRole('heading', { level: 2, name: /data import/i })).toBeInTheDocument();
    expect(screen.getByText(/import exported data files to analyze/i)).toBeInTheDocument();
  });

  it('renders the Recent imports section heading', () => {
    renderWithProviders(<IntegrationsPage />);

    expect(screen.getByRole('heading', { level: 2, name: /recent imports/i })).toBeInTheDocument();
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

  it('shows Connected status for GitHub Enterprise and Slack', () => {
    renderWithProviders(<IntegrationsPage />);

    const ghCard = screen.getByTestId('mkt-card-github-enterprise');
    expect(within(ghCard).getByText('Connected')).toBeInTheDocument();
    expect(within(ghCard).getByRole('button', { name: /configure/i })).toBeInTheDocument();

    const slackCard = screen.getByTestId('mkt-card-slack');
    expect(within(slackCard).getByText('Connected')).toBeInTheDocument();
    expect(within(slackCard).getByRole('button', { name: /configure/i })).toBeInTheDocument();
  });

  it('shows Configured status for PagerDuty', () => {
    renderWithProviders(<IntegrationsPage />);

    const pdCard = screen.getByTestId('mkt-card-pagerduty');
    expect(within(pdCard).getByText('Configured')).toBeInTheDocument();
    expect(within(pdCard).getByRole('button', { name: /configure/i })).toBeInTheDocument();
  });

  it('shows Not installed status with Install button for uninstalled integrations', () => {
    renderWithProviders(<IntegrationsPage />);

    const sentinelCard = screen.getByTestId('mkt-card-microsoft-sentinel');
    expect(within(sentinelCard).getByText('Not installed')).toBeInTheDocument();
    expect(within(sentinelCard).getByRole('button', { name: /install/i })).toBeInTheDocument();

    const splunkCard = screen.getByTestId('mkt-card-splunk');
    expect(within(splunkCard).getByText('Not installed')).toBeInTheDocument();
    expect(within(splunkCard).getByRole('button', { name: /install/i })).toBeInTheDocument();

    const jiraCard = screen.getByTestId('mkt-card-jira');
    expect(within(jiraCard).getByText('Not installed')).toBeInTheDocument();
    expect(within(jiraCard).getByRole('button', { name: /install/i })).toBeInTheDocument();
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

  /* ---------------------------------------------------------------- */
  /*  Data Import cards                                                 */
  /* ---------------------------------------------------------------- */

  it('renders the Audit Log Import card with correct hints', () => {
    renderWithProviders(<IntegrationsPage />);

    expect(screen.getByText('Audit Log Import')).toBeInTheDocument();
    expect(screen.getByText(/accepts \.csv or \.json · max 500 mb/i)).toBeInTheDocument();
  });

  it('renders the Copilot Metrics Import card with correct hints', () => {
    renderWithProviders(<IntegrationsPage />);

    expect(screen.getByText('Copilot Metrics Import')).toBeInTheDocument();
    expect(screen.getByText(/accepts \.json · github copilot metrics api format/i)).toBeInTheDocument();
  });

  it('renders "Drop file here or browse" text for both import cards', () => {
    renderWithProviders(<IntegrationsPage />);

    const dropTexts = screen.getAllByText(/drop file here or browse/i);
    expect(dropTexts).toHaveLength(2);
  });

  it('renders hidden file inputs with correct accept attributes', () => {
    renderWithProviders(<IntegrationsPage />);

    const fileInputs = document.querySelectorAll<HTMLInputElement>('input[type="file"]');
    expect(fileInputs).toHaveLength(2);

    const accepts = Array.from(fileInputs).map((input) => input.accept);
    expect(accepts).toContain('.csv,.json');
    expect(accepts).toContain('.json');
  });

  it('triggers file input click when drop zone is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IntegrationsPage />);

    const dropZones = screen.getAllByRole('button', { name: /upload/i });
    expect(dropZones.length).toBeGreaterThanOrEqual(2);

    const fileInputs = document.querySelectorAll<HTMLInputElement>('input[type="file"]');
    const clickSpy = vi.spyOn(fileInputs[0], 'click');

    await user.click(dropZones[0]);
    expect(clickSpy).toHaveBeenCalled();

    clickSpy.mockRestore();
  });

  it('triggers file input click when drop zone receives Enter keypress', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IntegrationsPage />);

    const dropZones = screen.getAllByRole('button', { name: /upload/i });
    const fileInputs = document.querySelectorAll<HTMLInputElement>('input[type="file"]');
    const clickSpy = vi.spyOn(fileInputs[0], 'click');

    dropZones[0].focus();
    await user.keyboard('{Enter}');
    expect(clickSpy).toHaveBeenCalled();

    clickSpy.mockRestore();
  });

  /* ---------------------------------------------------------------- */
  /*  Recent imports table                                              */
  /* ---------------------------------------------------------------- */

  it('renders the recent imports table with correct column headers', () => {
    renderWithProviders(<IntegrationsPage />);

    const table = screen.getByRole('table');
    const headers = within(table).getAllByRole('columnheader');
    const headerTexts = headers.map((h) => h.textContent);

    expect(headerTexts).toEqual(['File', 'Type', 'Size', 'Imported at', 'Records', 'Status']);
  });

  it('renders 3 rows of import data', () => {
    renderWithProviders(<IntegrationsPage />);

    const table = screen.getByRole('table');
    const rows = within(table).getAllByRole('row');
    // 1 header row + 3 data rows
    expect(rows).toHaveLength(4);
  });

  it('renders correct file names in the recent imports table', () => {
    renderWithProviders(<IntegrationsPage />);

    expect(screen.getByText('audit-log-2025-06-01.csv')).toBeInTheDocument();
    expect(screen.getByText('copilot-metrics-may.json')).toBeInTheDocument();
    expect(screen.getByText('audit-log-2025-05-15.json')).toBeInTheDocument();
  });

  it('renders correct types in the recent imports table', () => {
    renderWithProviders(<IntegrationsPage />);

    const auditLogCells = screen.getAllByText('Audit Log');
    expect(auditLogCells).toHaveLength(2);
    expect(screen.getByText('Copilot Metrics')).toBeInTheDocument();
  });

  it('shows Completed status badges for all imports', () => {
    renderWithProviders(<IntegrationsPage />);

    const completedBadges = screen.getAllByText('Completed');
    expect(completedBadges).toHaveLength(3);
  });

  it('renders formatted record counts', () => {
    renderWithProviders(<IntegrationsPage />);

    // toLocaleString formatting — accept either comma or period as separator
    expect(screen.getByText(/48.?210/)).toBeInTheDocument();
    expect(screen.getByText(/1.?340/)).toBeInTheDocument();
    expect(screen.getByText(/125.?800/)).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Helper text                                                       */
  /* ---------------------------------------------------------------- */

  it('renders export helper text for audit log import', () => {
    renderWithProviders(<IntegrationsPage />);

    expect(screen.getByText(/export from github enterprise/i)).toBeInTheDocument();
    expect(screen.getByText(/settings → audit log → export csv/i)).toBeInTheDocument();
  });

  it('renders API helper text for copilot metrics import', () => {
    renderWithProviders(<IntegrationsPage />);

    expect(screen.getByText(/fetch via/i)).toBeInTheDocument();
  });
});
