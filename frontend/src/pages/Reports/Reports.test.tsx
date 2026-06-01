import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { ReportsPage } from './index';

vi.mock('../../hooks/useOrg');

import { useOrg } from '../../hooks/useOrg';

const mockUseOrg = vi.mocked(useOrg);

vi.mock('../../api/reports', () => ({
  getMauReport: vi.fn().mockResolvedValue({
    report_type: 'mau',
    org: null,
    granularity: 'daily',
    window_days: 30,
    data_source: 'Audit Events',
    generated_at: '2024-01-15T00:00:00Z',
    data: [{ bucket: '2024-01-01', unique_actors: 42, total_events: 150 }],
  }),
  getSeatUtilizationReport: vi.fn().mockResolvedValue({
    report_type: 'seat_utilization',
    org: null,
    granularity: 'daily',
    window_days: 30,
    data_source: 'Audit Events',
    generated_at: '2024-01-15T00:00:00Z',
    data: [
      {
        bucket: '2024-01-01',
        active_seat_count: 10,
        provisioned_seat_count: 20,
        utilization_pct: 50.0,
      },
    ],
  }),
  getActionsVolumeReport: vi.fn().mockResolvedValue({
    report_type: 'actions_volume',
    org: null,
    granularity: 'daily',
    window_days: 30,
    data_source: 'Audit Events',
    generated_at: '2024-01-15T00:00:00Z',
    data: [
      { bucket: '2024-01-01', org: 'acme', workflow_runs: 100, unique_actors: 5, unique_repos: 3 },
      { bucket: '2024-01-02', org: 'acme', workflow_runs: 120, unique_actors: 6, unique_repos: 4 },
    ],
  }),
  getCopilotSeatsReport: vi.fn().mockResolvedValue({
    report_type: 'copilot_seats',
    org: null,
    granularity: 'daily',
    window_days: 30,
    data_source: 'Audit Events (Copilot)',
    generated_at: '2024-01-15T00:00:00Z',
    data: [
      {
        bucket: '2024-01-01',
        seats_assigned: 5,
        seats_revoked: 1,
        seats_net: 4,
        policy_change_count: 0,
      },
    ],
  }),
  getRepoCreationRateReport: vi.fn().mockResolvedValue({
    report_type: 'repo-creation-rate',
    org: null,
    granularity: 'daily',
    window_days: 30,
    data_source: 'Audit Events',
    generated_at: '2024-01-15T00:00:00Z',
    data: [
      {
        bucket: '2024-01-01',
        org: 'acme',
        repos_created: 12,
        unique_creators: 7,
      },
    ],
  }),
  getPatCountsReport: vi.fn().mockResolvedValue({
    report_type: 'pat-counts',
    org: null,
    granularity: 'daily',
    window_days: 30,
    data_source: 'Audit Events',
    generated_at: '2024-01-15T00:00:00Z',
    data: [
      {
        bucket: '2024-01-01',
        org: 'acme',
        actions: { 'personal_access_token.create': 4, 'personal_access_token.revoke': 2 },
      },
    ],
  }),
  getWebhookCountsReport: vi.fn().mockResolvedValue({
    report_type: 'webhook-counts',
    org: null,
    granularity: 'daily',
    window_days: 30,
    data_source: 'Audit Events',
    generated_at: '2024-01-15T00:00:00Z',
    data: [
      {
        bucket: '2024-01-01',
        org: 'acme',
        actions: { 'hook.create': 3, 'hook.destroy': 1 },
      },
    ],
  }),
  getCodespaceHoursReport: vi.fn().mockResolvedValue({
    report_type: 'codespace-hours',
    org: null,
    granularity: 'daily',
    window_days: 30,
    data_source: 'Audit Events',
    generated_at: '2024-01-15T00:00:00Z',
    data: [
      {
        bucket: '2024-01-01',
        org: 'acme',
        codespace_events: 18,
        unique_users: 6,
        total_billable_hours: 42.5,
      },
    ],
  }),
  exportReport: vi.fn(),
  getReportCatalog: vi.fn().mockResolvedValue([]),
  listCustomReports: vi.fn().mockResolvedValue([]),
  listSharedReports: vi.fn().mockResolvedValue([]),
  deleteCustomReport: vi.fn().mockResolvedValue(undefined),
  shareCustomReport: vi.fn().mockResolvedValue({}),
  runCustomReport: vi.fn().mockResolvedValue({ data: [], row_count: 0 }),
  getCustomReport: vi.fn().mockResolvedValue(null),
  createCustomReport: vi.fn().mockResolvedValue({}),
  updateCustomReport: vi.fn().mockResolvedValue({}),
  exportCustomReport: vi.fn(),
}));

describe('ReportsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseOrg.mockReturnValue({ selectedOrg: '', setSelectedOrg: vi.fn() });
  });

  it('renders page title and subtitle', () => {
    renderWithProviders(<ReportsPage />);
    expect(screen.getByText('Reports')).toBeInTheDocument();
    expect(screen.getByText('Organization activity and usage analytics')).toBeInTheDocument();
  });

  it('renders window selector with 30d, 60d, 90d buttons', () => {
    renderWithProviders(<ReportsPage />);
    expect(screen.getByText('Window:')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '30d' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '60d' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '90d' })).toBeInTheDocument();
  });

  it('updates window days when selector buttons are clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    expect(screen.getByText(/last 30 days/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '60d' }));
    expect(screen.getByText(/last 60 days/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '90d' }));
    expect(screen.getByText(/last 90 days/)).toBeInTheDocument();
  });

  it('renders summary card with data bucket counts', async () => {
    renderWithProviders(<ReportsPage />);
    expect(screen.getByText(/Data summary/)).toBeInTheDocument();
    expect(screen.getByText('Total MAU buckets')).toBeInTheDocument();
    expect(screen.getByText('Actions buckets')).toBeInTheDocument();
    expect(screen.getByText('Platform seat util buckets')).toBeInTheDocument();
    expect(screen.getByText('Copilot seat buckets')).toBeInTheDocument();
  });

  it('renders summary cards for all 8 report types', async () => {
    renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByText('Repo creation buckets')).toBeInTheDocument();
    });
    expect(screen.getByText('Total MAU buckets')).toBeInTheDocument();
    expect(screen.getByText('Actions buckets')).toBeInTheDocument();
    expect(screen.getByText('Platform seat util buckets')).toBeInTheDocument();
    expect(screen.getByText('Copilot seat buckets')).toBeInTheDocument();
    expect(screen.getByText('Repo creation buckets')).toBeInTheDocument();
    expect(screen.getByText('PAT event buckets')).toBeInTheDocument();
    expect(screen.getByText('Webhook event buckets')).toBeInTheDocument();
    expect(screen.getByText('Codespace hours buckets')).toBeInTheDocument();
  });

  it('shows Platform seat util instead of Seat util for seat-utilization summary', () => {
    renderWithProviders(<ReportsPage />);
    expect(screen.getByText('Platform seat util buckets')).toBeInTheDocument();
  });

  it('summary values are clickable when numeric', async () => {
    const { container } = renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      const grid = container.querySelector('.summaryGrid')!;
      const clickableValues = grid.querySelectorAll('.clickableValue');
      expect(clickableValues.length).toBeGreaterThan(0);
    });
    const grid = container.querySelector('.summaryGrid')!;
    const clickableValues = grid.querySelectorAll('.clickableValue');
    clickableValues.forEach((el) => {
      expect(el.getAttribute('role')).toBe('button');
    });
  });

  it('clicking bucket value opens the detail drawer', async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(container.querySelector('.clickableValue')).not.toBeNull();
    });
    const clickable = container.querySelector('.clickableValue')!;
    await user.click(clickable);
    // Drawer opens with report-detail-tray content
    expect(screen.getByTestId('report-detail-tray')).toBeInTheDocument();
  });

  it('renders data source labels on summary cards', async () => {
    renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      const sources = screen.getAllByText(/Source: Audit Events/);
      expect(sources.length).toBeGreaterThanOrEqual(3);
    });
  });

  it('renders data source in drawer when report is opened', async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(container.querySelector('.clickableValue')).not.toBeNull();
    });
    const clickable = container.querySelector('.clickableValue')!;
    await user.click(clickable);
    const modalSources = document.querySelectorAll('.modalDataSource');
    expect(modalSources.length).toBeGreaterThanOrEqual(1);
  });

  // ── Tab navigation tests ──────────────────────────────────────────────

  it('renders tab navigation with Templates, My Reports, Shared with Me, and Recent tabs', () => {
    renderWithProviders(<ReportsPage />);
    expect(screen.getByRole('tab', { name: /Templates/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /My Reports/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Shared with Me/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Recent/i })).toBeInTheDocument();
  });

  it('Templates tab is active by default', () => {
    renderWithProviders(<ReportsPage />);
    const templatesTab = screen.getByRole('tab', { name: /Templates/i });
    expect(templatesTab.getAttribute('aria-selected')).toBe('true');
  });

  it('renders 8 pre-built report template rows in Templates tab table', async () => {
    renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByText('Security Posture Report')).toBeInTheDocument();
    });
    expect(screen.getByText('Compliance Report')).toBeInTheDocument();
    expect(screen.getByText('Detection Summary Report')).toBeInTheDocument();
    expect(screen.getByText('User Activity Report')).toBeInTheDocument();
    expect(screen.getByText('Copilot Usage Report')).toBeInTheDocument();
    expect(screen.getByText('Workflow Health Report')).toBeInTheDocument();
    expect(screen.getByText('Access Review Report')).toBeInTheDocument();
    expect(screen.getByText('Org Comparison Report')).toBeInTheDocument();
  });

  it('templates are displayed in a DataTable', async () => {
    renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByText('Security Posture Report')).toBeInTheDocument();
    });
    // Table should be rendered with proper column headers
    expect(screen.getByText('Report Name')).toBeInTheDocument();
    expect(screen.getByText('Description')).toBeInTheDocument();
    expect(screen.getByText('Type')).toBeInTheDocument();
    expect(screen.getByText('Last Run')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
  });

  it('clicking a template row opens the detail drawer with config panel', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByText('User Activity Report')).toBeInTheDocument();
    });

    const row = screen.getByText('User Activity Report');
    await user.click(row);

    // Drawer should be open with the config panel
    expect(screen.getByTestId('report-config-panel')).toBeInTheDocument();
  });

  it('clicking a template row opens drawer with export buttons', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByText('Security Posture Report')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Security Posture Report'));

    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export PDF' })).toBeInTheDocument();
  });

  it('calls exportReport when Export CSV is clicked in drawer', async () => {
    const { exportReport } = await import('../../api/reports');
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByText('Security Posture Report')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Security Posture Report'));
    await user.click(screen.getByRole('button', { name: 'Export CSV' }));

    expect(exportReport).toHaveBeenCalledWith('soc2', 'csv');
  });

  it('calls exportReport when Export PDF is clicked in drawer', async () => {
    const { exportReport } = await import('../../api/reports');
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByText('Security Posture Report')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Security Posture Report'));
    await user.click(screen.getByRole('button', { name: 'Export PDF' }));

    expect(exportReport).toHaveBeenCalledWith('soc2', 'pdf');
  });

  it('renders catalog items in the templates table', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'security_posture',
        title: 'Custom Security Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: ['security', 'automated'],
      },
      {
        id: 'report-2',
        type: 'dora_metrics',
        title: 'DORA Metrics Report',
        generated_at: '2024-06-14T08:00:00Z',
        status: 'completed',
        tags: ['dora'],
      },
    ]);

    renderWithProviders(<ReportsPage />);

    expect(await screen.findByText('Custom Security Report')).toBeInTheDocument();
    expect(screen.getByText('DORA Metrics Report')).toBeInTheDocument();
  });

  it('renders without crashing when catalog entries have no tags field', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-no-tags',
        type: 'mau',
        title: 'Report Without Tags',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'available',
      } as import('../../types/reports').ReportCatalogEntry,
    ]);
    renderWithProviders(<ReportsPage />);
    expect(await screen.findByText('Report Without Tags')).toBeInTheDocument();
  });

  it('renders without crashing when generated_at is null', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-null-date',
        type: 'mau',
        title: 'Report With Null Date',
        generated_at: null,
        status: 'available',
        tags: ['custom-tag-unique'],
      },
    ]);
    renderWithProviders(<ReportsPage />);
    expect(await screen.findByText('Report With Null Date')).toBeInTheDocument();
  });

  it('renders description on catalog items when description is present', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-desc',
        type: 'mau',
        title: 'MAU With Description',
        description: 'Unique actors per time bucket.',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    renderWithProviders(<ReportsPage />);
    await screen.findByText('MAU With Description');
    expect(screen.getByText('Unique actors per time bucket.')).toBeInTheDocument();
  });

  it('clicking a catalog report row opens drawer with report data', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'mau',
        title: 'MAU Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    const title = await screen.findByText('MAU Report');
    await user.click(title);

    // Drawer opens with data section showing the reportDataMap title
    expect(screen.getByTestId('report-detail-tray')).toBeInTheDocument();
    // The report data section title comes from reportDataMap
    const tables = screen.getAllByRole('table');
    expect(tables.length).toBeGreaterThanOrEqual(1);
  });

  it('clicking a report row does not call exportReport directly', async () => {
    const { exportReport, getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'mau',
        title: 'MAU Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    const title = await screen.findByText('MAU Report');
    await user.click(title);
    expect(exportReport).not.toHaveBeenCalled();
  });

  it('drawer shows "no data" for unknown report types', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'unknown_type',
        title: 'Unknown Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    const title = await screen.findByText('Unknown Report');
    await user.click(title);

    expect(screen.getByText('No data available for this report type.')).toBeInTheDocument();
  });

  it('clicking repo-creation-rate report opens drawer with data', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-repo',
        type: 'repo-creation-rate',
        title: 'Repo Creation Rate Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    const title = await screen.findByText('Repo Creation Rate Report');
    await user.click(title);

    expect(screen.getByText('Repo Creation Rate')).toBeInTheDocument();
  });

  it('clicking pat-counts report opens drawer with data', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-pat',
        type: 'pat-counts',
        title: 'PAT Counts Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    const title = await screen.findByText('PAT Counts Report');
    await user.click(title);

    expect(screen.getByText('Personal Access Token Counts')).toBeInTheDocument();
  });

  it('clicking webhook-counts report opens drawer with data', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-webhook',
        type: 'webhook-counts',
        title: 'Webhook Counts Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    const title = await screen.findByText('Webhook Counts Report');
    await user.click(title);

    expect(screen.getByText('Webhook Counts')).toBeInTheDocument();
  });

  it('clicking codespace-hours report opens drawer with data', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-codespace',
        type: 'codespace-hours',
        title: 'Codespace Hours Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    const title = await screen.findByText('Codespace Hours Report');
    await user.click(title);

    expect(screen.getByText('Codespace Hours')).toBeInTheDocument();
  });

  // ── Tab switching tests ──────────────────────────────────────────────

  it('switching to My Reports tab shows empty state when no custom reports', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    await user.click(screen.getByRole('tab', { name: /My Reports/i }));

    expect(await screen.findByText(/No custom reports yet/)).toBeInTheDocument();
  });

  it('switching to Shared tab shows empty state when no shared reports', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    await user.click(screen.getByRole('tab', { name: /Shared with Me/i }));

    expect(await screen.findByText(/No reports have been shared with you yet/)).toBeInTheDocument();
  });

  it('switching to Recent tab shows empty state when no recent reports', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    await user.click(screen.getByRole('tab', { name: /Recent/i }));

    expect(await screen.findByText(/No recently run reports/)).toBeInTheDocument();
  });

  it('renders "New Custom Report" button', () => {
    renderWithProviders(<ReportsPage />);
    expect(screen.getByRole('button', { name: /New Custom Report/i })).toBeInTheDocument();
  });

  it('clicking "New Custom Report" opens the report builder modal', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    await user.click(screen.getByRole('button', { name: /New Custom Report/i }));

    expect(screen.getByTestId('report-builder')).toBeInTheDocument();
    expect(screen.getByText('Step 1: Choose Data Sources')).toBeInTheDocument();
  });

  it('My Reports tab renders custom report rows in table', async () => {
    const { listCustomReports } = await import('../../api/reports');
    vi.mocked(listCustomReports).mockResolvedValueOnce([
      {
        id: 1,
        name: 'My Custom Events Report',
        description: 'Custom event analysis',
        owner_login: 'testuser',
        data_sources: ['events'],
        columns: [],
        filters: [],
        grouping: { group_by: null, time_bucket: null },
        visualization: 'table',
        is_shared: false,
        shared_with: [],
        last_run_at: null,
        created_at: '2024-06-15T10:00:00Z',
        updated_at: '2024-06-15T10:00:00Z',
      },
    ]);

    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    await user.click(screen.getByRole('tab', { name: /My Reports/i }));

    expect(await screen.findByText('My Custom Events Report')).toBeInTheDocument();
    expect(screen.getByText('Custom event analysis')).toBeInTheDocument();
  });

  it('My Reports tab shows Share and Delete buttons in drawer when row is clicked', async () => {
    const { listCustomReports } = await import('../../api/reports');
    vi.mocked(listCustomReports).mockResolvedValueOnce([
      {
        id: 1,
        name: 'My Report',
        description: null,
        owner_login: 'testuser',
        data_sources: ['events'],
        columns: [],
        filters: [],
        grouping: { group_by: null, time_bucket: null },
        visualization: 'table',
        is_shared: false,
        shared_with: [],
        last_run_at: null,
        created_at: '2024-06-15T10:00:00Z',
        updated_at: '2024-06-15T10:00:00Z',
      },
    ]);

    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    await user.click(screen.getByRole('tab', { name: /My Reports/i }));
    await screen.findByText('My Report');

    // Click the row to open drawer
    await user.click(screen.getByText('My Report'));

    expect(screen.getByRole('button', { name: 'Share' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
  });

  it('Shared reports tab shows "shared by" status in table', async () => {
    const { listSharedReports } = await import('../../api/reports');
    vi.mocked(listSharedReports).mockResolvedValueOnce([
      {
        id: 2,
        name: 'Shared Detection Report',
        description: null,
        owner_login: 'otheruser',
        data_sources: ['detections'],
        columns: [],
        filters: [],
        grouping: { group_by: null, time_bucket: null },
        visualization: 'table',
        is_shared: true,
        shared_with: ['testuser'],
        last_run_at: null,
        created_at: '2024-06-15T10:00:00Z',
        updated_at: '2024-06-15T10:00:00Z',
      },
    ]);

    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    await user.click(screen.getByRole('tab', { name: /Shared with Me/i }));
    await screen.findByText('Shared Detection Report');

    expect(screen.getByText('shared by otheruser')).toBeInTheDocument();
  });

  it('tab badge shows custom report count', async () => {
    const { listCustomReports } = await import('../../api/reports');
    vi.mocked(listCustomReports).mockResolvedValueOnce([
      {
        id: 1,
        name: 'Report 1',
        description: null,
        owner_login: 'testuser',
        data_sources: ['events'],
        columns: [],
        filters: [],
        grouping: { group_by: null, time_bucket: null },
        visualization: 'table',
        is_shared: false,
        shared_with: [],
        last_run_at: null,
        created_at: '2024-06-15T10:00:00Z',
        updated_at: '2024-06-15T10:00:00Z',
      },
      {
        id: 2,
        name: 'Report 2',
        description: null,
        owner_login: 'testuser',
        data_sources: ['detections'],
        columns: [],
        filters: [],
        grouping: { group_by: null, time_bucket: null },
        visualization: 'table',
        is_shared: false,
        shared_with: [],
        last_run_at: null,
        created_at: '2024-06-15T10:00:00Z',
        updated_at: '2024-06-15T10:00:00Z',
      },
    ]);

    renderWithProviders(<ReportsPage />);

    await waitFor(() => {
      const myReportsTab = screen.getByRole('tab', { name: /My Reports/i });
      expect(myReportsTab.textContent).toContain('2');
    });
  });

  // ── Deep-linking tests ──────────────────────────────────────────────

  it('opening page with report query param auto-opens the drawer', async () => {
    renderWithProviders(<ReportsPage />, { route: '/?report=tmpl-user-activity' });

    await waitFor(() => {
      expect(screen.getByTestId('report-detail-tray')).toBeInTheDocument();
    });
    // Drawer title and table both show the name; verify drawer is rendered
    expect(screen.getByTestId('report-detail-tray')).toBeInTheDocument();
  });

  it('drawer shows organization when selectedOrg is set', async () => {
    mockUseOrg.mockReturnValue({ selectedOrg: 'my-org', setSelectedOrg: vi.fn() });
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByText('Security Posture Report')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Security Posture Report'));

    expect(screen.getByText('my-org')).toBeInTheDocument();
  });

  it('table has clickable row styling on report names', async () => {
    const { container } = renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByText('Security Posture Report')).toBeInTheDocument();
    });
    const clickableTitles = container.querySelectorAll('.reportTitleClickable');
    expect(clickableTitles.length).toBeGreaterThan(0);
  });
});
