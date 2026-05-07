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

  it('shows empty state when no reports in catalog', async () => {
    renderWithProviders(<ReportsPage />);
    expect(await screen.findByText(/No reports available yet/)).toBeInTheDocument();
  });

  it('renders report cards from catalog API data', async () => {
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

  it('renders PDF and CSV buttons for catalog report cards', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'security_posture',
        title: 'Custom Posture Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);

    renderWithProviders(<ReportsPage />);

    await screen.findByText('Custom Posture Report');
    const pdfButtons = screen.getAllByRole('button', { name: 'PDF' });
    const csvButtons = screen.getAllByRole('button', { name: 'CSV' });
    expect(pdfButtons.length).toBeGreaterThanOrEqual(1);
    expect(csvButtons.length).toBeGreaterThanOrEqual(1);
  });

  it('renders window selector with 30d, 60d, 90d buttons', () => {
    renderWithProviders(<ReportsPage />);
    expect(screen.getByText('Window:')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '30d' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '60d' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '90d' })).toBeInTheDocument();
  });

  it('calls exportReport with pdf format when PDF button is clicked', async () => {
    const { exportReport, getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'security_posture',
        title: 'Custom Posture Export',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    await screen.findByText('Custom Posture Export');
    const pdfButtons = screen.getAllByRole('button', { name: 'PDF' });
    await user.click(pdfButtons[0]);
    expect(exportReport).toHaveBeenCalledWith('security_posture', 'pdf');
  });

  it('calls exportReport with csv format when CSV button is clicked', async () => {
    const { exportReport, getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'security_posture',
        title: 'Custom Posture CSV',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    await screen.findByText('Custom Posture CSV');
    const csvButtons = screen.getAllByRole('button', { name: 'CSV' });
    await user.click(csvButtons[0]);
    expect(exportReport).toHaveBeenCalledWith('security_posture', 'csv');
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

  it('renders org-scoped tags showing "All orgs" when no org is selected and catalog has items', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'security_posture',
        title: 'Test Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    renderWithProviders(<ReportsPage />);
    await screen.findByText('Test Report');
    const allOrgLabels = screen.getAllByText('All orgs');
    expect(allOrgLabels).toHaveLength(1);
  });

  it('renders org-scoped tags showing selected org name when catalog has items', async () => {
    mockUseOrg.mockReturnValue({ selectedOrg: 'my-org', setSelectedOrg: vi.fn() });
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'security_posture',
        title: 'Test Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    renderWithProviders(<ReportsPage />);
    await screen.findByText('Test Report');
    const orgLabels = screen.getAllByText('my-org');
    expect(orgLabels).toHaveLength(1);
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

  it('clicking bucket value opens modal', async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(container.querySelector('.clickableValue')).not.toBeNull();
    });
    const clickable = container.querySelector('.clickableValue')!;
    await user.click(clickable);
    // Modal renders a table with bucket data columns
    expect(screen.getByRole('table')).toBeInTheDocument();
  });

  it('report titles have clickable styling when catalog has items', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'security_posture',
        title: 'Test Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    const { container } = renderWithProviders(<ReportsPage />);
    await screen.findByText('Test Report');
    const clickableTitles = container.querySelectorAll('.reportTitleClickable');
    expect(clickableTitles).toHaveLength(1);
    clickableTitles.forEach((el) => {
      expect(el.getAttribute('role')).toBe('button');
    });
  });

  it('clicking a report title does not call exportReport', async () => {
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

  it('clicking a report title opens a modal with report data', async () => {
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

    expect(screen.getByText('Monthly Active Users')).toBeInTheDocument();
    const tables = screen.getAllByRole('table');
    expect(tables.length).toBeGreaterThanOrEqual(1);
  });

  it('report view modal shows "no data" message for unknown report types', async () => {
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
    expect(screen.getByText('All orgs')).toBeInTheDocument();
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
    expect(screen.getByText('available')).toBeInTheDocument();
    expect(screen.getByText('custom-tag-unique')).toBeInTheDocument();
  });

  it('renders tag labels from catalog entry tags', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-with-tags',
        type: 'mau',
        title: 'Tagged Report',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: ['unique-tag-alpha', 'unique-tag-beta'],
      },
    ]);
    renderWithProviders(<ReportsPage />);
    await screen.findByText('Tagged Report');
    expect(screen.getByText('unique-tag-alpha')).toBeInTheDocument();
    expect(screen.getByText('unique-tag-beta')).toBeInTheDocument();
  });

  it('renders data source labels on summary cards', async () => {
    renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      const sources = screen.getAllByText(/Source: Audit Events/);
      expect(sources.length).toBeGreaterThanOrEqual(3);
    });
  });

  it('renders data source label on catalog items when data_source is present', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-ds',
        type: 'mau',
        title: 'MAU With Source',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
        data_source: 'Audit Events',
      },
    ]);
    renderWithProviders(<ReportsPage />);
    await screen.findByText('MAU With Source');
    expect(screen.getByText('Audit Events')).toBeInTheDocument();
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

  it('renders data source in bucket modal when opened', async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(container.querySelector('.clickableValue')).not.toBeNull();
    });
    const clickable = container.querySelector('.clickableValue')!;
    await user.click(clickable);
    // Modal may render in a portal; check at document level
    const modalSources = document.querySelectorAll('.modalDataSource');
    expect(modalSources.length).toBeGreaterThanOrEqual(1);
  });

  it('renders data source in report view modal', async () => {
    const { getReportCatalog } = await import('../../api/reports');
    vi.mocked(getReportCatalog).mockResolvedValueOnce([
      {
        id: 'report-1',
        type: 'mau',
        title: 'MAU Report View',
        generated_at: '2024-06-15T10:00:00Z',
        status: 'completed',
        tags: [],
      },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);

    const title = await screen.findByText('MAU Report View');
    await user.click(title);

    expect(screen.getByText('Monthly Active Users')).toBeInTheDocument();
    // Modal may render in a portal; check at document level
    const modalSources = document.querySelectorAll('.modalDataSource');
    expect(modalSources.length).toBeGreaterThanOrEqual(1);
  });

  it('shows Platform seat util instead of Seat util for seat-utilization summary', () => {
    renderWithProviders(<ReportsPage />);
    expect(screen.getByText('Platform seat util buckets')).toBeInTheDocument();
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

  it('clicking repo-creation-rate report title opens modal with report data', async () => {
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
    const tables = screen.getAllByRole('table');
    expect(tables.length).toBeGreaterThanOrEqual(1);
  });

  it('clicking pat-counts report title opens modal with report data', async () => {
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
    const tables = screen.getAllByRole('table');
    expect(tables.length).toBeGreaterThanOrEqual(1);
  });

  it('clicking webhook-counts report title opens modal with report data', async () => {
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
    const tables = screen.getAllByRole('table');
    expect(tables.length).toBeGreaterThanOrEqual(1);
  });

  it('clicking codespace-hours report title opens modal with report data', async () => {
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
    const tables = screen.getAllByRole('table');
    expect(tables.length).toBeGreaterThanOrEqual(1);
  });

  // ── New tab-based tests ──────────────────────────────────────────────

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

  it('renders 8 pre-built report template cards in Templates tab', async () => {
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

  it('template cards show category tags', async () => {
    renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByText('Security Posture Report')).toBeInTheDocument();
    });
    // Categories like Security, Compliance, Usage, DevOps
    expect(screen.getAllByText('Security').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Usage').length).toBeGreaterThanOrEqual(1);
  });

  it('clicking a template card opens the config panel in a drawer', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByText('User Activity Report')).toBeInTheDocument();
    });

    const templateCard = screen.getByText('User Activity Report');
    await user.click(templateCard);

    // Drawer should be open with the config panel - look for the config panel
    expect(screen.getByTestId('report-config-panel')).toBeInTheDocument();
  });

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

    // The builder should render inside a modal
    expect(screen.getByTestId('report-builder')).toBeInTheDocument();
    expect(screen.getByText('Step 1: Choose Data Sources')).toBeInTheDocument();
  });

  it('My Reports tab renders custom report cards', async () => {
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
    expect(screen.getByText('events')).toBeInTheDocument();
  });

  it('My Reports tab shows Share and Delete buttons on custom reports', async () => {
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

    expect(screen.getByRole('button', { name: 'Share' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
  });

  it('Shared reports tab shows "Shared by" badge', async () => {
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

    expect(screen.getByText('Shared by otheruser')).toBeInTheDocument();
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
      // The My Reports tab should show count "2"
      const myReportsTab = screen.getByRole('tab', { name: /My Reports/i });
      expect(myReportsTab.textContent).toContain('2');
    });
  });
});
